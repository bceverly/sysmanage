# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Resolving, dispatching and ingesting file watches (ROADMAP 21.1 S7).

A file watch is DISPATCHED AS A ONE-QUERY PACK, exactly the trick S5 used for
live queries. The agent needs no new command, the result correlation is the
one S4 already proved in production, and grading -- including "this host could
not answer" -- is inherited rather than reimplemented.

What a watch adds over an ordinary pack is the ``table_params`` channel: the
watched paths are POLICY the server holds, not something the host can know, so
they travel with the dispatch and the agent materializes
``sysmanage_file_state`` from them.

WHY INGESTION WRITES A SECOND TIME
-----------------------------------
Results already land in ``query_pack_result_row`` like any pack's. They are
ALSO upserted into ``host_file_state``, which is what the differ reads. That
is not redundancy for its own sake: the result rows are an append-only history
of runs, while the differ needs "the current state of every watched path on
this host" -- a different question, and one that would otherwise be a
correlated-subquery-per-path over the whole run history.

PLATFORM FILTERING HAPPENS HERE, NOT ON THE AGENT
--------------------------------------------------
A path declared for linux must never be sent to a Windows host. If it were,
the agent would dutifully report it ``absent`` -- and absent means "this
should be here and is not", which is drift. A curated list naming
/etc/ssh/sshd_config would then show every Windows box as having deleted it.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.persistence import models
from backend.persistence.partitions import PARTITION_SHARED, partition_session
from backend.services import host_facts

logger = logging.getLogger(__name__)

# The one query a watch dispatch carries. Selecting explicit columns rather
# than * so a contract that grows a column does not silently change the shape
# of what ingestion receives.
WATCH_QUERY_NAME = "sysmanage_file_watch"
WATCH_TABLE = "sysmanage_file_state"
WATCH_COLUMNS = (
    "path",
    "state",
    "sha256",
    "size",
    "mode",
    "uid",
    "gid",
    "owner",
    "group_name",
    "mtime",
    "type",
    "target",
)
# B608 (hardcoded_sql_expressions) does not apply here on two counts, and the
# suppression is narrow because of them. First, both operands are module
# constants above -- no caller, request or database value reaches this string.
# Second, and more to the point, the SERVER NEVER EXECUTES IT: the text is
# shipped to the agent as a query pack's ``sql`` (see build_dispatch below) and
# runs against the agent's in-memory SQLite fact database. There is no server
# statement here to inject into. ``test_watch_sql_is_built_from_bare_identifiers``
# keeps the first claim true if the column tuple is ever edited.
WATCH_SQL = f"SELECT {', '.join(WATCH_COLUMNS)} FROM {WATCH_TABLE}"  # nosec B608


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _platform_allows(platforms: Optional[Iterable[str]], host_platform: str) -> bool:
    """Is this path declared for the host's platform?

    An empty or absent list means "every platform" -- the same convention
    ``SharedQueryPackQuery.platforms`` uses.
    """
    if not platforms:
        return True
    wanted = {str(p).strip().lower() for p in platforms if str(p).strip()}
    return not wanted or (host_platform or "").lower() in wanted


def _paths_from(rows, host_platform: str) -> List[str]:
    return [
        row.path
        for row in rows
        if row.path and _platform_allows(row.platforms, host_platform)
    ]


def list_shared_watches(include_deprecated: bool = False) -> List[Dict[str, Any]]:
    """The curated catalog, as plain DICTS.

    Dicts rather than ORM objects because these rows come from a different
    session on a different partition; handing a caller a detached instance is
    how ``DetachedInstanceError`` surfaces three layers from its cause.
    """
    with partition_session(partition=PARTITION_SHARED) as session:
        query = session.query(models.SharedFileWatch)
        if not include_deprecated:
            query = query.filter(models.SharedFileWatch.deprecated.is_(False))
        return [
            {
                "id": str(w.id),
                "slug": w.slug,
                "name": w.name,
                "description": w.description,
                "version": w.version,
                "category": w.category,
                "deprecated": w.deprecated,
                "path_count": len(w.paths or []),
            }
            for w in query.order_by(models.SharedFileWatch.name).all()
        ]


def shared_watch_paths(shared_watch_id) -> Optional[List[Dict[str, Any]]]:
    """A curated list's paths, or None when the catalog has no such entry.

    ``None`` and ``[]`` are different answers and the caller must keep them
    apart: an empty list is a curated list with nothing in it, while None is a
    SOFT reference whose target is gone -- which must be reported, not treated
    as "watch nothing".
    """
    with partition_session(partition=PARTITION_SHARED) as session:
        watch = (
            session.query(models.SharedFileWatch)
            .filter(models.SharedFileWatch.id == shared_watch_id)
            .one_or_none()
        )
        if watch is None:
            return None
        return [_PathView(p.path, p.platforms) for p in watch.paths or []]


class _PathView:
    """A detached (path, platforms) pair.

    The resolver reads ``.path`` and ``.platforms`` off whatever it is given,
    so the shared rows are copied into this rather than returned as ORM
    objects bound to a session that is about to close.
    """

    __slots__ = ("path", "platforms")

    def __init__(self, path, platforms):
        self.path = path
        self.platforms = platforms


def host_tag_ids(db: Session, host_id) -> List[Any]:
    """The tag ids attached to one host."""
    return [
        row.tag_id
        for row in db.query(models.HostTag).filter(models.HostTag.host_id == host_id)
    ]


def assignments_for(db: Session, host) -> List[Any]:
    """Enabled assignments targeting this host, by id, tag or site.

    All three targets are unioned rather than ranked: a watch list is additive
    -- watching a path twice is watching it once -- so unlike a query pack
    there is no "which assignment wins" question to answer, and therefore no
    need for the licensed resolver.
    """
    host_id = getattr(host, "id", None)
    tag_ids = host_tag_ids(db, host_id)
    site_id = getattr(host, "site_id", None)

    query = db.query(models.FileWatchAssignment).filter(
        models.FileWatchAssignment.enabled.is_(True)
    )
    targets = [models.FileWatchAssignment.host_id == host_id]
    if tag_ids:
        targets.append(models.FileWatchAssignment.tag_id.in_(tag_ids))
    if site_id is not None:
        targets.append(models.FileWatchAssignment.site_id == site_id)
    return query.filter(or_(*targets)).all()


def resolve_paths(db: Session, host, shared_lookup=None) -> List[str]:
    """Every path this host should watch, de-duplicated, order stable.

    ``shared_lookup(shared_watch_id) -> [SharedFileWatchPath]`` reads the
    SHARED partition, which may be a different database; it is injected rather
    than queried here so this function stays usable in a plain unit test and
    so the cross-partition read is explicit at the call site.
    """
    host_platform = (getattr(host, "platform", None) or "").lower()
    host_id = getattr(host, "id", None)
    assignments = assignments_for(db, host)

    paths: List[str] = []
    seen = set()
    for assignment in assignments:
        if assignment.watch_id is not None:
            rows = (
                db.query(models.FileWatchPath)
                .filter(models.FileWatchPath.watch_id == assignment.watch_id)
                .all()
            )
        elif assignment.shared_watch_id is not None and shared_lookup is not None:
            rows = shared_lookup(assignment.shared_watch_id)
            if rows is None:
                # A SOFT reference whose catalog entry is gone. Loud, with
                # context: silently contributing no paths would let a host
                # report an empty watch list that an operator believes is
                # populated -- and an empty list compares as "nothing to
                # check", not as an error.
                logger.warning(
                    "file watch assignment %s names shared watch %s, "
                    "which is not in the catalog; host %s will not watch its "
                    "paths",
                    assignment.id,
                    assignment.shared_watch_id,
                    host_id,
                )
                continue
        else:
            continue
        for path in _paths_from(rows, host_platform):
            if path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


def build_dispatch(paths: List[str], run_id=None) -> Dict[str, Any]:
    """The ``run_query_pack`` parameters for a file watch.

    Shaped as a one-query pack so the agent command, the result envelope and
    the grading are the ones S4 and S5 already use.
    """
    return {
        "run_id": str(run_id) if run_id else None,
        "pack_name": WATCH_QUERY_NAME,
        "pack_id": None,
        "shared_pack_id": None,
        "version": 1,
        # The channel that makes this table answerable at all.
        "table_params": {WATCH_TABLE: {"paths": list(paths)}},
        "queries": [
            {
                "name": WATCH_QUERY_NAME,
                "sql": WATCH_SQL,
                "required_tables": [WATCH_TABLE],
            }
        ],
    }


def should_dispatch(host) -> bool:
    """Only dispatch to a host that ADVERTISES the table.

    ``host_facts.serves``, not ``answerable``: an agent too old to know the
    table would answer the query with an error rather than rows, and the run
    would grade as a failure rather than as "this host is not equipped yet".
    """
    return host_facts.serves(host, WATCH_TABLE)


# Handled explicitly by the caller: ``path`` identifies the row and ``state``
# is validated before anything is written, so neither may also arrive through
# the generic value mapping.
_EXPLICIT_COLUMNS = frozenset({"path", "state"})


def _row_values(row: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce one agent row into column values, dropping anything unexpected.

    A newer agent may report a column this server does not model; ignoring it
    keeps ingestion of the columns we DO model working.
    """
    return {
        column: row.get(column)
        for column in WATCH_COLUMNS
        if column not in _EXPLICIT_COLUMNS
    }


def ingest_rows(db: Session, host_id, rows: Iterable[Dict[str, Any]]) -> int:
    """Upsert what a host reported into ``host_file_state``.

    Returns the number of paths recorded. Rows with no ``path`` or no
    ``state`` are DROPPED rather than stored with nulls: a state column that
    can be null reintroduces exactly the ambiguity it exists to remove.
    """
    now = _utcnow()
    existing = {
        row.path: row
        for row in db.query(models.HostFileState)
        .filter(models.HostFileState.host_id == host_id)
        .all()
    }

    seen = set()
    for row in rows or ():
        path = row.get("path")
        state = row.get("state")
        if not path or not state:
            logger.warning(
                "file watch row from host %s has no path/state; dropped: %r",
                host_id,
                row,
            )
            continue
        seen.add(path)
        values = _row_values(row)
        current = existing.get(path)
        if current is None:
            db.add(
                models.HostFileState(
                    id=uuid.uuid4(),
                    host_id=host_id,
                    path=path,
                    state=state,
                    collected_at=now,
                    **values,
                )
            )
            continue
        current.state = state
        for column, value in values.items():
            setattr(current, column, value)
        current.collected_at = now

    # A path no longer in the watch list stops being state we can vouch for.
    # Leaving it would let the differ compare a stale hash from weeks ago
    # against a live one and report drift that nobody can reproduce.
    for path, row in existing.items():
        if path not in seen:
            db.delete(row)

    db.flush()
    return len(seen)

# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Replace a host's inventory rows by writing only what changed (Phase 22.2).

WHY
---
The software inventory was replaced by deleting the host's rows and inserting
them all again: ~600 rows deleted and ~600 inserted for every report, changed
or not.  The 10,000-agent profile (2026-10-02) found PostgreSQL the saturated
resource (~3.4 cores) and that write the inbound drain's largest handler cost;
every rewritten row is index maintenance, WAL and a dead tuple for autovacuum.
Most reports change nothing (the agent's 24-hour resend) or a few packages.

HOW
---
One SELECT of the host's rows; compare them with the report as multisets of
the written columns; delete the rows no longer reported and insert the new
ones.  An unchanged report writes nothing.  A changed field is a delete plus an
insert -- rows are compared whole, there is no update -- and an unchanged row
keeps its id and ``created_at``.  Nothing references these rows' ids.
"""

from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

from sqlalchemy import delete, insert, select

DELETE_CHUNK = 1000  # keep IN lists well inside every database's limits


def replace_host_rows(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db,
    model,
    host_id,
    rows: Iterable[Dict],
    columns: Sequence[str],
    stamp: Dict,
) -> Tuple[int, int]:
    """Make ``host_id``'s rows of ``model`` equal ``rows``, compared on
    ``columns``; new rows also get ``stamp`` (timestamps).  Returns
    ``(inserted, deleted)``.  Does not commit."""
    wanted = Counter(tuple(row.get(c) for c in columns) for row in rows)
    existing: Dict[tuple, List] = defaultdict(list)
    query = select(model.id, *(getattr(model, c) for c in columns)).where(
        model.host_id == host_id
    )
    for found in db.execute(query):
        existing[tuple(found[1:])].append(found[0])

    stale = []
    for key, ids in existing.items():
        keep = wanted.get(key, 0)
        stale.extend(ids[keep:])
        if keep:
            wanted[key] = max(0, keep - len(ids))
    for start in range(0, len(stale), DELETE_CHUNK):
        db.execute(
            delete(model).where(model.id.in_(stale[start : start + DELETE_CHUNK]))
        )

    fresh = [
        {"host_id": host_id, **dict(zip(columns, key)), **stamp}
        for key, count in wanted.items()
        for _ in range(count)
    ]
    if fresh:
        db.execute(insert(model), fresh)
    return len(fresh), len(stale)

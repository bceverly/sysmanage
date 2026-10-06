# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Large deletes in chunks, each its own short transaction (Phase 22.2).

The daily queue purge and the custom-metric retention prune each ran ONE
DELETE over everything past its cutoff.  At fleet scale that is a day's
completed queue messages (millions of rows at 20,000 agents) in a single
statement and transaction: long row locks, a WAL burst, and the processor
that called it waiting the whole time.  ``delete_in_chunks`` removes the
same rows ``chunk_size`` at a time and commits after each chunk, so no
transaction holds more than one chunk.  Portable: a SELECT of ids with a
LIMIT, then ``DELETE ... WHERE id IN (...)`` -- the same on SQLite and
PostgreSQL.
"""

from typing import Any

DEFAULT_CHUNK_SIZE = 5000


def delete_in_chunks(
    session, model: Any, *criteria, chunk_size: int = DEFAULT_CHUNK_SIZE
) -> int:
    """Delete every ``model`` row matching ``criteria``, ``chunk_size`` at a
    time, committing ``session`` after each chunk.  Returns the rows
    deleted.  The caller's pending changes are committed with the first
    chunk."""
    total = 0
    while True:
        ids = [
            row[0]
            for row in session.query(model.id).filter(*criteria).limit(chunk_size).all()
        ]
        if not ids:
            return total
        session.query(model).filter(model.id.in_(ids)).delete(synchronize_session=False)
        session.commit()
        total += len(ids)
        if len(ids) < chunk_size:
            return total

# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: large deletes go in chunks, each its own transaction."""

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.persistence.chunked_delete import delete_in_chunks

Base = declarative_base()


class Row(Base):  # pylint: disable=too-few-public-methods
    __tablename__ = "chunked_delete_row"
    id = sa.Column(sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    age = sa.Column(sa.Integer, nullable=False)


def _session(rows):
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all(Row(age=a) for a in rows)
    session.commit()
    return session


def test_deletes_every_match_in_chunks_committing_each():
    session = _session([10] * 23 + [1] * 5)
    commits = []
    original = session.commit

    def counting_commit():
        commits.append(1)
        original()

    session.commit = counting_commit
    assert delete_in_chunks(session, Row, Row.age > 5, chunk_size=10) == 23
    assert len(commits) == 3  # 10 + 10 + 3
    assert session.query(Row).count() == 5  # the young rows stay


def test_exact_multiple_of_the_chunk_ends_on_an_empty_select():
    session = _session([10] * 20)
    assert delete_in_chunks(session, Row, Row.age > 5, chunk_size=10) == 20
    assert session.query(Row).count() == 0


def test_nothing_to_delete():
    session = _session([1, 2, 3])
    assert delete_in_chunks(session, Row, Row.age > 5) == 0
    assert session.query(Row).count() == 3


def test_several_criteria_are_all_applied():
    session = _session([10, 10, 1])
    assert delete_in_chunks(session, Row, Row.age > 5, Row.age < 20) == 2

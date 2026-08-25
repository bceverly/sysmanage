# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Per-user DataGrid column and dashboard card preferences.

These are the smallest-stakes routes in the product and the easiest to break
without noticing, because every failure mode looks like "the UI forgot my
settings" rather than an error.

Two shapes matter.  A grid with no stored row returns **null**, not a 404 --
the UI reads that as "use the defaults", and a 404 would surface as an error
toast on every first visit to every grid.  And the dashboard-card PUT is a
partial upsert: cards absent from the body keep whatever they had, so a client
sending only the card the user just toggled must not blank the rest.

``visible: False`` is the value most likely to be dropped by a careless
truthiness check -- hiding a card is the entire point of the feature.
"""

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.api import user_preferences as up

MOD = "backend.api.user_preferences"
USER_UUID = uuid.UUID("55555555-5555-4555-8555-555555555555")
PREF_UUID = uuid.UUID("66666666-6666-4666-8666-666666666666")


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, **by_model):
        self._by_model = {k: list(v) for k, v in by_model.items()}
        self.added = []
        self.deleted = []
        self.commits = 0
        self.rolled_back = False

    def query(self, model):
        return _FakeQuery(self._by_model.get(model.__name__, []))

    def add(self, row):
        self.added.append(row)
        self._by_model.setdefault(type(row).__name__, []).append(row)
        if getattr(row, "id", None) is None:
            row.id = uuid.uuid4()

    def delete(self, row):
        self.deleted.append(row)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rolled_back = True

    def refresh(self, _row):
        pass


def _user():
    return SimpleNamespace(id=USER_UUID, userid="admin@invalid")


def _column_pref(grid="hosts", hidden=None):
    return SimpleNamespace(
        id=PREF_UUID,
        user_id=USER_UUID,
        grid_identifier=grid,
        hidden_columns=hidden if hidden is not None else ["ip"],
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 2),
    )


def _card_pref(card="fleet-health", visible=True):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=USER_UUID,
        card_identifier=card,
        visible=visible,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _audit():
    return patch(f"{MOD}.AuditService", MagicMock())


class TestGridIdentifierValidation:
    def test_a_normal_identifier_is_accepted(self):
        request = up.DataGridColumnPreferenceRequest(
            grid_identifier="hosts", hidden_columns=[]
        )
        assert request.grid_identifier == "hosts"

    def test_surrounding_whitespace_is_stripped(self):
        # Otherwise " hosts" and "hosts" become two separate stored rows and
        # the grid appears to forget its settings at random.
        request = up.DataGridColumnPreferenceRequest(
            grid_identifier="  hosts  ", hidden_columns=[]
        )
        assert request.grid_identifier == "hosts"

    @pytest.mark.parametrize("value", ["", "   "])
    def test_a_blank_identifier_is_rejected(self, value):
        with pytest.raises(ValidationError):
            up.DataGridColumnPreferenceRequest(grid_identifier=value, hidden_columns=[])

    def test_an_over_long_identifier_is_rejected(self):
        # The column is VARCHAR(255); accepting more defers the failure to a
        # database error at commit time.
        with pytest.raises(ValidationError):
            up.DataGridColumnPreferenceRequest(
                grid_identifier="x" * 256, hidden_columns=[]
            )

    def test_exactly_255_characters_is_allowed(self):
        request = up.DataGridColumnPreferenceRequest(
            grid_identifier="x" * 255, hidden_columns=[]
        )
        assert len(request.grid_identifier) == 255


class TestResponseCoercion:
    def test_uuid_columns_are_rendered_as_strings(self):
        out = up.DataGridColumnPreferenceResponse(
            id=PREF_UUID,
            user_id=USER_UUID,
            grid_identifier="hosts",
            hidden_columns=[],
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        assert out.id == str(PREF_UUID)
        assert out.user_id == str(USER_UUID)

    def test_string_ids_pass_through(self):
        out = up.DataGridColumnPreferenceResponse(
            id="p1",
            user_id="u1",
            grid_identifier="hosts",
            hidden_columns=[],
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        assert (out.id, out.user_id) == ("p1", "u1")


class TestGetColumnPreferences:
    @pytest.mark.asyncio
    async def test_a_stored_preference_is_returned(self):
        db = _FakeSession(User=[_user()], UserDataGridColumnPreference=[_column_pref()])
        out = await up.get_column_preferences(
            "hosts", db=db, current_user="admin@invalid"
        )
        assert out.grid_identifier == "hosts"
        assert out.hidden_columns == ["ip"]
        assert out.user_id == str(USER_UUID)

    @pytest.mark.asyncio
    async def test_a_grid_with_no_stored_row_returns_null_not_404(self):
        # The UI treats null as "use the defaults"; a 404 would fire an error
        # toast the first time anyone opens any grid.
        db = _FakeSession(User=[_user()])
        assert (
            await up.get_column_preferences(
                "hosts", db=db, current_user="admin@invalid"
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await up.get_column_preferences(
                "hosts", db=_FakeSession(), current_user="ghost"
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_is_a_500(self):
        db = _FakeSession()
        db.query = MagicMock(side_effect=RuntimeError("db gone"))
        with pytest.raises(HTTPException) as exc:
            await up.get_column_preferences(
                "hosts", db=db, current_user="admin@invalid"
            )
        assert exc.value.status_code == 500


class TestUpdateColumnPreferences:
    async def _put(self, db, grid="hosts", hidden=None):
        with _audit():
            return await up.update_column_preferences(
                up.DataGridColumnPreferenceRequest(
                    grid_identifier=grid, hidden_columns=hidden or []
                ),
                db=db,
                current_user="admin@invalid",
            )

    @pytest.mark.asyncio
    async def test_an_existing_preference_is_updated_in_place(self):
        pref = _column_pref(hidden=["ip"])
        db = _FakeSession(User=[_user()], UserDataGridColumnPreference=[pref])
        out = await self._put(db, hidden=["ip", "os"])
        assert db.added == []
        assert pref.hidden_columns == ["ip", "os"]
        assert out.hidden_columns == ["ip", "os"]
        assert db.commits == 1

    @pytest.mark.asyncio
    async def test_a_first_time_preference_is_created(self):
        db = _FakeSession(User=[_user()])
        out = await self._put(db, hidden=["ip"])
        assert len(db.added) == 1
        assert db.added[0].grid_identifier == "hosts"
        assert out.hidden_columns == ["ip"]

    @pytest.mark.asyncio
    async def test_hiding_nothing_is_a_valid_saved_state(self):
        # An empty list means "show every column", which is different from
        # having no row at all -- the latter means "use the grid's defaults".
        pref = _column_pref(hidden=["ip", "os"])
        db = _FakeSession(User=[_user()], UserDataGridColumnPreference=[pref])
        out = await self._put(db, hidden=[])
        assert pref.hidden_columns == []
        assert out.hidden_columns == []

    @pytest.mark.asyncio
    async def test_the_update_timestamp_moves(self):
        pref = _column_pref()
        db = _FakeSession(User=[_user()], UserDataGridColumnPreference=[pref])
        await self._put(db, hidden=["ip"])
        assert pref.updated_at > datetime(2026, 1, 2)

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await self._put(_FakeSession())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_rolls_back_and_is_a_500(self):
        db = _FakeSession(User=[_user()])
        db.commit = MagicMock(side_effect=RuntimeError("db gone"))
        with pytest.raises(HTTPException) as exc:
            await self._put(db)
        assert exc.value.status_code == 500
        assert db.rolled_back is True


class TestDeleteColumnPreferences:
    async def _delete(self, db, grid="hosts"):
        with _audit():
            return await up.delete_column_preferences(
                grid, db=db, current_user="admin@invalid"
            )

    @pytest.mark.asyncio
    async def test_an_existing_preference_is_removed(self):
        pref = _column_pref()
        db = _FakeSession(User=[_user()], UserDataGridColumnPreference=[pref])
        out = await self._delete(db)
        assert db.deleted == [pref]
        assert "reset to defaults" in out["message"]

    @pytest.mark.asyncio
    async def test_deleting_nothing_succeeds_idempotently(self):
        # Resetting a grid that was never customised is a no-op, not an error.
        db = _FakeSession(User=[_user()])
        out = await self._delete(db)
        assert db.deleted == []
        assert db.commits == 0
        assert "No preferences found" in out["message"]

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_500_not_a_404(self):
        # The 404 raised inside is swallowed by the bare ``except Exception``
        # here -- unlike the other three routes, this one has no
        # ``except HTTPException: raise`` re-raise clause.
        with pytest.raises(HTTPException) as exc:
            await self._delete(_FakeSession())
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_rolls_back(self):
        db = _FakeSession(User=[_user()], UserDataGridColumnPreference=[_column_pref()])
        db.commit = MagicMock(side_effect=RuntimeError("db gone"))
        with pytest.raises(HTTPException) as exc:
            await self._delete(db)
        assert exc.value.status_code == 500
        assert db.rolled_back is True


class TestGetDashboardCardPreferences:
    @pytest.mark.asyncio
    async def test_stored_cards_are_returned(self):
        db = _FakeSession(
            User=[_user()],
            UserDashboardCardPreference=[
                _card_pref("fleet-health", True),
                _card_pref("cve-feed", False),
            ],
        )
        out = await up.get_dashboard_card_preferences(
            db=db, current_user="admin@invalid"
        )
        assert [(p.card_identifier, p.visible) for p in out.preferences] == [
            ("fleet-health", True),
            ("cve-feed", False),
        ]

    @pytest.mark.asyncio
    async def test_a_user_with_no_stored_cards_gets_an_empty_list(self):
        db = _FakeSession(User=[_user()])
        out = await up.get_dashboard_card_preferences(
            db=db, current_user="admin@invalid"
        )
        assert out.preferences == []

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await up.get_dashboard_card_preferences(
                db=_FakeSession(), current_user="ghost"
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_is_a_500(self):
        db = _FakeSession()
        db.query = MagicMock(side_effect=RuntimeError("db gone"))
        with pytest.raises(HTTPException) as exc:
            await up.get_dashboard_card_preferences(db=db, current_user="admin@invalid")
        assert exc.value.status_code == 500


class TestUpdateDashboardCardPreferences:
    async def _put(self, db, pairs):
        request = up.DashboardCardPreferencesRequest(
            preferences=[
                up.DashboardCardPreference(card_identifier=c, visible=v)
                for c, v in pairs
            ]
        )
        with _audit():
            return await up.update_dashboard_card_preferences(
                request, db=db, current_user="admin@invalid"
            )

    @pytest.mark.asyncio
    async def test_an_existing_card_is_flipped_in_place(self):
        pref = _card_pref("fleet-health", visible=True)
        db = _FakeSession(User=[_user()], UserDashboardCardPreference=[pref])
        out = await self._put(db, [("fleet-health", False)])
        assert db.added == []
        # Hiding a card is the whole feature; a truthiness filter here would
        # make the toggle appear not to save.
        assert pref.visible is False
        assert out.preferences[0].visible is False

    @pytest.mark.asyncio
    async def test_a_new_card_is_created(self):
        db = _FakeSession(User=[_user()])
        out = await self._put(db, [("cve-feed", True)])
        assert len(db.added) == 1
        assert db.added[0].card_identifier == "cve-feed"
        assert [p.card_identifier for p in out.preferences] == ["cve-feed"]

    @pytest.mark.asyncio
    async def test_cards_absent_from_the_body_keep_their_setting(self):
        # Partial upsert: a client that sends only the card just toggled must
        # not blank every other card's stored state.
        untouched = _card_pref("cve-feed", visible=False)
        toggled = _card_pref("fleet-health", visible=True)
        db = _FakeSession(
            User=[_user()], UserDashboardCardPreference=[toggled, untouched]
        )
        out = await self._put(db, [("fleet-health", False)])
        assert untouched.visible is False
        assert len(out.preferences) == 2

    @pytest.mark.asyncio
    async def test_a_mixed_batch_updates_and_creates_in_one_pass(self):
        existing = _card_pref("fleet-health", visible=True)
        db = _FakeSession(User=[_user()], UserDashboardCardPreference=[existing])
        await self._put(db, [("fleet-health", False), ("cve-feed", True)])
        assert existing.visible is False
        assert [r.card_identifier for r in db.added] == ["cve-feed"]
        # One commit for the whole batch, not one per card.
        assert db.commits == 1

    @pytest.mark.asyncio
    async def test_the_response_reflects_the_users_full_card_set(self):
        existing = _card_pref("cve-feed", visible=False)
        db = _FakeSession(User=[_user()], UserDashboardCardPreference=[existing])
        out = await self._put(db, [("fleet-health", True)])
        # Returning only the submitted cards would make the UI drop the rest
        # from its local state on every save.
        assert {p.card_identifier for p in out.preferences} == {
            "cve-feed",
            "fleet-health",
        }

    @pytest.mark.asyncio
    async def test_an_empty_body_is_accepted_as_a_no_op(self):
        db = _FakeSession(User=[_user()])
        out = await self._put(db, [])
        assert out.preferences == []
        assert db.added == []

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await self._put(_FakeSession(), [("fleet-health", True)])
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_rolls_back_and_is_a_500(self):
        db = _FakeSession(User=[_user()])
        db.commit = MagicMock(side_effect=RuntimeError("db gone"))
        with pytest.raises(HTTPException) as exc:
            await self._put(db, [("fleet-health", True)])
        assert exc.value.status_code == 500
        assert db.rolled_back is True

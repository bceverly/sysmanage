# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Audit-log listing, retrieval, and export.

Two things here are easy to break invisibly.

The default date range: `/list` with no dates silently narrows to the last
FOUR HOURS.  An operator investigating something from yesterday sees an empty
table and concludes the events were never recorded.  Export deliberately does
NOT apply that default -- it exports exactly what was asked for -- and the two
routes must not drift into agreeing.

The export authorization: `/export` streams the *entire* filtered log with no
limit or offset.  Its VIEW_AUDIT_LOG check is the only thing between an
ordinary session and a dump of every administrative action on the server, and
it has to fire before any query runs.

reportlab is exercised for real on the PDF path -- it is the only way to know
the column widths and the flowables actually build.
"""

import csv
import io
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.api import audit_log as al

MOD = "backend.api.audit_log"
AUDIT_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
USER_UUID = uuid.UUID("22222222-2222-4222-8222-222222222222")


class _FakeQuery:
    """Records the filters applied to it; slicing is done in Python."""

    def __init__(self, rows, applied=None):
        self._rows = rows
        self.applied = applied if applied is not None else []

    def filter(self, *args, **_kwargs):
        self.applied.extend(args)
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def offset(self, n):
        return _FakeQuery(self._rows[n:], self.applied)

    def limit(self, n):
        return _FakeQuery(self._rows[:n], self.applied)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def count(self):
        return len(self._rows)


class _FakeSession:
    def __init__(self, **by_model):
        self._by_model = {k: list(v) for k, v in by_model.items()}
        self.last_query = None

    def query(self, model):
        self.last_query = _FakeQuery(self._by_model.get(model.__name__, []))
        return self.last_query

    def get_bind(self):
        return "engine"

    def __call__(self, *_a, **_k):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


_UNSET = object()


def _user(has_role=True, role_cache=_UNSET):
    user = SimpleNamespace(
        id=USER_UUID,
        userid="admin@invalid",
        _role_cache={} if role_cache is _UNSET else role_cache,
    )
    user.load_role_cache = lambda s: setattr(user, "_role_cache", {})
    user.has_role = lambda role: has_role
    return user


def _entry(**overrides):
    entry = SimpleNamespace(
        id=AUDIT_ID,
        timestamp=datetime(2026, 1, 1, 12, 0),
        user_id=USER_UUID,
        username="admin@invalid",
        action_type="UPDATE",
        entity_type="HOST",
        # String(255) in the model -- callers pass str(host.id), which is
        # why the response validator coerces only id/user_id.
        entity_id="host-1",
        entity_name="host.invalid",
        description="Changed something",
        details={"k": "v"},
        ip_address="10.0.0.9",
        user_agent="curl/8",
        result="SUCCESS",
        error_message=None,
        category="admin",
        entry_type="action",
    )
    for key, value in overrides.items():
        setattr(entry, key, value)
    return entry


def _filters(**overrides):
    filters = al.AuditLogFilters(
        user_id=None,
        action_type=None,
        entity_type=None,
        result=None,
        category=None,
        entry_type=None,
        search=None,
        start_date=None,
        end_date=None,
    )
    for key, value in overrides.items():
        setattr(filters, key, value)
    return filters


def _authorized(user=None):
    """Bind the authorization helper's own sessionmaker."""
    auth_session = _FakeSession(User=[user or _user()])
    return patch(f"{MOD}.sessionmaker", return_value=auth_session), auth_session


class TestAuthorizeViewAuditLog:
    def test_a_user_with_the_role_passes(self):
        maker, _ = _authorized()
        with maker:
            assert al._authorize_view_audit_log(_FakeSession(), "admin@invalid") is None

    def test_an_unknown_user_is_a_401(self):
        with patch(f"{MOD}.sessionmaker", return_value=_FakeSession()):
            with pytest.raises(HTTPException) as exc:
                al._authorize_view_audit_log(_FakeSession(), "ghost")
        assert exc.value.status_code == 401

    def test_a_user_without_the_role_is_a_403(self):
        maker, _ = _authorized(_user(has_role=False))
        with maker:
            with pytest.raises(HTTPException) as exc:
                al._authorize_view_audit_log(_FakeSession(), "admin@invalid")
        assert exc.value.status_code == 403

    def test_a_cold_role_cache_is_loaded_before_the_check(self):
        user = _user(role_cache=None)
        loaded = []
        user.load_role_cache = loaded.append
        maker, _ = _authorized(user)
        with maker:
            al._authorize_view_audit_log(_FakeSession(), "admin@invalid")
        # Without the load a cold cache denies every caller.
        assert loaded


class TestDefaultDateRange:
    def test_no_dates_narrows_to_the_last_four_hours(self):
        out = al._default_date_range(_filters())
        span = out.end_date - out.start_date
        # This is the one that makes yesterday's events look absent.
        assert timedelta(hours=3, minutes=59) < span < timedelta(hours=4, minutes=1)

    def test_a_start_with_no_end_runs_to_now(self):
        start = datetime(2026, 1, 1)
        out = al._default_date_range(_filters(start_date=start))
        assert out.start_date == start
        assert out.end_date > datetime(2026, 1, 1)

    def test_an_end_with_no_start_is_left_open(self):
        end = datetime(2026, 1, 1)
        out = al._default_date_range(_filters(end_date=end))
        # Deliberately unbounded below: "everything up to X" is a real query.
        assert out.start_date is None
        assert out.end_date == end

    def test_both_dates_are_left_untouched(self):
        start, end = datetime(2026, 1, 1), datetime(2026, 2, 1)
        out = al._default_date_range(_filters(start_date=start, end_date=end))
        assert (out.start_date, out.end_date) == (start, end)


class TestApplyAuditFilters:
    def _apply(self, **kwargs):
        session = _FakeSession(AuditLog=[_entry()])
        query = al._apply_audit_filters(
            session.query(al.models.AuditLog), _filters(**kwargs)
        )
        return query.applied

    def test_no_filters_narrows_nothing(self):
        assert self._apply() == []

    @pytest.mark.parametrize(
        "field,value",
        [
            ("action_type", "DELETE"),
            ("entity_type", "HOST"),
            ("result", "FAILURE"),
            ("category", "security"),
            ("entry_type", "action"),
            ("start_date", datetime(2026, 1, 1)),
            ("end_date", datetime(2026, 2, 1)),
        ],
    )
    def test_each_scalar_filter_adds_one_clause(self, field, value):
        assert len(self._apply(**{field: value})) == 1

    def test_a_search_term_matches_description_or_entity_name(self):
        applied = self._apply(search="nginx")
        assert len(applied) == 1
        # One OR clause, not two ANDed clauses -- ANDing them would only ever
        # match rows where BOTH contain the term.
        assert "OR" in str(applied[0])

    def test_a_valid_user_id_is_coerced_to_a_uuid(self):
        assert len(self._apply(user_id=str(USER_UUID))) == 1

    def test_a_malformed_user_id_is_a_400(self):
        with pytest.raises(HTTPException) as exc:
            self._apply(user_id="not-a-uuid")
        assert exc.value.status_code == 400

    def test_filters_compose(self):
        applied = self._apply(action_type="DELETE", result="FAILURE", search="nginx")
        assert len(applied) == 3


class TestListAuditLogs:
    async def _list(self, session, filters=None, limit=100, offset=0, user=None):
        maker, _ = _authorized(user)
        with maker:
            return await al.list_audit_logs(
                filters=filters or _filters(),
                limit=limit,
                offset=offset,
                db_session=session,
                current_user="admin@invalid",
            )

    @pytest.mark.asyncio
    async def test_entries_are_returned_with_paging_metadata(self):
        session = _FakeSession(AuditLog=[_entry(), _entry()])
        out = await self._list(session, limit=50, offset=0)
        assert out.total == 2
        assert out.limit == 50
        assert out.offset == 0
        assert len(out.entries) == 2

    @pytest.mark.asyncio
    async def test_the_total_counts_matches_not_the_page(self):
        session = _FakeSession(AuditLog=[_entry() for _ in range(5)])
        out = await self._list(session, limit=2, offset=0)
        # total drives the pager; reporting the page size would show one page.
        assert out.total == 5
        assert len(out.entries) == 2

    @pytest.mark.asyncio
    async def test_paging_slices_the_result_set(self):
        entries = [_entry(description=f"d{i}") for i in range(5)]
        session = _FakeSession(AuditLog=entries)
        out = await self._list(session, limit=2, offset=2)
        assert [e.description for e in out.entries] == ["d2", "d3"]

    @pytest.mark.asyncio
    async def test_the_four_hour_default_is_applied_to_the_query(self):
        session = _FakeSession(AuditLog=[_entry()])
        await self._list(session)
        # Two clauses: >= start and <= end.
        assert len(session.last_query.applied) == 2

    @pytest.mark.asyncio
    async def test_an_unauthorized_caller_never_reaches_the_query(self):
        session = _FakeSession(AuditLog=[_entry()])
        with pytest.raises(HTTPException) as exc:
            await self._list(session, user=_user(has_role=False))
        assert exc.value.status_code == 403
        assert session.last_query is None

    @pytest.mark.asyncio
    async def test_a_bad_filter_keeps_its_400(self):
        session = _FakeSession(AuditLog=[])
        with pytest.raises(HTTPException) as exc:
            await self._list(session, _filters(user_id="not-a-uuid"))
        # Wrapping this in a 500 would make a typo look like a server fault.
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_is_a_500(self):
        session = _FakeSession()
        session.query = MagicMock(side_effect=RuntimeError("db gone"))
        with pytest.raises(HTTPException) as exc:
            await self._list(session)
        assert exc.value.status_code == 500


class TestGetAuditLogEntry:
    async def _get(self, session, audit_id=str(AUDIT_ID), user=None):
        maker, _ = _authorized(user)
        with maker:
            return await al.get_audit_log_entry(
                audit_id, db_session=session, current_user="admin@invalid"
            )

    @pytest.mark.asyncio
    async def test_a_known_entry_is_returned(self):
        entry = _entry()
        assert await self._get(_FakeSession(AuditLog=[entry])) is entry

    @pytest.mark.asyncio
    async def test_an_unknown_entry_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await self._get(_FakeSession())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_malformed_id_is_a_400(self):
        with pytest.raises(HTTPException) as exc:
            await self._get(_FakeSession(), audit_id="not-a-uuid")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_an_unauthorized_caller_is_a_403(self):
        session = _FakeSession(AuditLog=[_entry()])
        with pytest.raises(HTTPException) as exc:
            await self._get(session, user=_user(has_role=False))
        assert exc.value.status_code == 403
        assert session.last_query is None

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_is_a_500(self):
        session = _FakeSession()
        session.query = MagicMock(side_effect=RuntimeError("db gone"))
        with pytest.raises(HTTPException) as exc:
            await self._get(session)
        assert exc.value.status_code == 500


class TestEntryResponseCoercion:
    def test_uuid_columns_are_rendered_as_strings(self):
        out = al.AuditLogEntryResponse(
            id=AUDIT_ID,
            timestamp=datetime(2026, 1, 1),
            user_id=USER_UUID,
            action_type="UPDATE",
            entity_type="HOST",
            description="x",
            result="SUCCESS",
        )
        assert out.id == str(AUDIT_ID)
        assert out.user_id == str(USER_UUID)

    def test_a_system_entry_with_no_user_stays_null(self):
        out = al.AuditLogEntryResponse(
            id="a1",
            timestamp=datetime(2026, 1, 1),
            user_id=None,
            action_type="EXECUTE",
            entity_type="HOST",
            description="x",
            result="SUCCESS",
        )
        assert out.user_id is None


class TestProPlusExportRouting:
    def test_an_unlicensed_server_gets_a_402_naming_the_format(self):
        with patch(f"{MOD}.module_loader.get_module", return_value=None):
            with pytest.raises(HTTPException) as exc:
                al._route_pro_plus_export("cef")
        assert exc.value.status_code == 402
        assert "CEF" in exc.value.detail
        # OSS callers must be told CSV exists rather than just refused.
        assert "CSV" in exc.value.detail

    def test_a_licensed_server_redirects_to_the_engine_route(self):
        with patch(f"{MOD}.module_loader.get_module", return_value=object()):
            with pytest.raises(HTTPException) as exc:
                al._route_pro_plus_export("json")
        assert exc.value.status_code == 307
        assert exc.value.headers["Location"] == "/api/v1/audit/export"


class TestExportAuditLogs:
    async def _export(self, fmt, user=None, filters=None):
        maker, _ = _authorized(user)
        with maker:
            with patch(f"{MOD}._build_audit_export", return_value="rendered") as build:
                out = await al.export_audit_logs(
                    filters=filters or _filters(),
                    fmt=fmt,
                    db_session=_FakeSession(),
                    current_user="admin@invalid",
                )
        return out, build

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fmt", ["csv", "CSV", "pdf", "PDF"])
    async def test_the_oss_formats_are_accepted_case_insensitively(self, fmt):
        out, build = await self._export(fmt)
        assert out == "rendered"
        assert build.call_args[0][1] == fmt.lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fmt", ["json", "cef", "leef"])
    async def test_the_pro_plus_formats_route_to_the_engine_check(self, fmt):
        maker, _ = _authorized()
        with maker:
            with patch(f"{MOD}.module_loader.get_module", return_value=None):
                with pytest.raises(HTTPException) as exc:
                    await al.export_audit_logs(
                        filters=_filters(),
                        fmt=fmt,
                        db_session=_FakeSession(),
                        current_user="admin@invalid",
                    )
        assert exc.value.status_code == 402

    @pytest.mark.asyncio
    async def test_an_unknown_format_is_a_400(self):
        with pytest.raises(HTTPException) as exc:
            await self._export("xlsx")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_an_unauthorized_caller_cannot_dump_the_log(self):
        # This route streams the WHOLE filtered log with no limit; the role
        # check is the only thing between a session and every admin action.
        with pytest.raises(HTTPException) as exc:
            await self._export("csv", user=_user(has_role=False))
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_export_does_not_inherit_the_four_hour_default(self):
        _, build = await self._export("csv")
        filters = build.call_args[0][0]
        # Silently truncating an export to four hours would produce a file
        # that looks complete and is not.
        assert filters.start_date is None
        assert filters.end_date is None


class TestBuildAuditExport:
    def _build(self, entries, fmt):
        session = _FakeSession(AuditLog=entries)
        with patch(f"{MOD}.sessionmaker", return_value=session):
            with patch(f"{MOD}.db_module.get_engine"):
                return al._build_audit_export(_filters(), fmt, "admin@invalid")

    def test_csv_is_the_default_render(self):
        out = self._build([_entry()], "csv")
        assert out.media_type == "text/csv"

    def test_pdf_routes_to_the_pdf_render(self):
        out = self._build([_entry()], "pdf")
        assert out.media_type == "application/pdf"

    def test_it_opens_its_own_session_because_it_runs_off_thread(self):
        # The request session can't cross the thread-pool boundary, so this
        # must bind the main engine itself.
        with patch(f"{MOD}.sessionmaker", return_value=_FakeSession()) as maker:
            with patch(f"{MOD}.db_module.get_engine", return_value="main"):
                al._build_audit_export(_filters(), "csv", "u")
        assert maker.call_args.kwargs["bind"] == "main"


class TestCsvExport:
    @staticmethod
    async def _read(response):
        # Starlette wraps a sync generator in iterate_in_threadpool, so the
        # body_iterator is async even though the streamer is not.
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return "".join(chunks)

    async def _rows(self, entries):
        response = al._stream_audit_csv(entries)
        body = await self._read(response)
        return list(csv.reader(io.StringIO(body))), response

    @pytest.mark.asyncio
    async def test_the_header_matches_the_declared_column_order(self):
        rows, _ = await self._rows([])
        assert rows[0] == al._CSV_COLUMNS

    @pytest.mark.asyncio
    async def test_an_entry_renders_one_row_in_column_order(self):
        rows, _ = await self._rows([_entry()])
        row = dict(zip(al._CSV_COLUMNS, rows[1]))
        assert row["timestamp"] == "2026-01-01T12:00:00"
        assert row["username"] == "admin@invalid"
        assert row["action_type"] == "UPDATE"
        assert row["description"] == "Changed something"
        assert row["user_id"] == str(USER_UUID)

    @pytest.mark.asyncio
    async def test_null_columns_render_as_empty_strings(self):
        entry = _entry(
            user_id=None,
            username=None,
            entity_id=None,
            entity_name=None,
            ip_address=None,
            user_agent=None,
            category=None,
            entry_type=None,
            error_message=None,
            timestamp=None,
        )
        rows, _ = await self._rows([entry])
        # A literal "None" in a CSV cell is indistinguishable from a real
        # value once the file leaves the product.
        assert "None" not in rows[1]

    @pytest.mark.asyncio
    async def test_a_description_containing_a_comma_is_quoted(self):
        rows, _ = await self._rows([_entry(description='Deleted host "a", then "b"')])
        # Round-tripping through csv.reader proves the quoting is correct.
        assert rows[1][al._CSV_COLUMNS.index("description")] == (
            'Deleted host "a", then "b"'
        )

    @pytest.mark.asyncio
    async def test_the_filename_carries_a_timestamp(self):
        _, response = await self._rows([])
        disposition = response.headers["content-disposition"]
        assert disposition.startswith('attachment; filename="audit-log-')
        assert disposition.endswith('.csv"')


class TestPdfExport:
    def test_a_populated_export_builds_a_real_pdf(self):
        response = al._stream_audit_pdf([_entry(), _entry()])
        assert response.media_type == "application/pdf"
        assert response.body.startswith(b"%PDF")

    def test_an_empty_export_still_builds_rather_than_erroring(self):
        # reportlab refuses a zero-row Table, so the empty case takes its own
        # branch; an operator whose filter matched nothing should get a PDF
        # that says so, not a 500.
        response = al._stream_audit_pdf([])
        assert response.body.startswith(b"%PDF")

    def test_a_null_heavy_entry_does_not_break_the_render(self):
        entry = _entry(
            username=None,
            action_type=None,
            entity_type=None,
            entity_name=None,
            result=None,
            description=None,
            timestamp=None,
        )
        assert al._stream_audit_pdf([entry]).body.startswith(b"%PDF")

    def test_the_column_widths_still_match_the_column_list(self):
        # The widths are a positional list; adding a PDF column without a
        # width raises inside reportlab at build time.
        assert len(al._PDF_COLUMNS) == 7

    def test_the_filename_carries_a_timestamp(self):
        response = al._stream_audit_pdf([])
        disposition = response.headers["content-disposition"]
        assert disposition.startswith('attachment; filename="audit-log-')
        assert disposition.endswith('.pdf"')


class TestFormatHelpers:
    @pytest.mark.parametrize(
        "value,expected",
        [(datetime(2026, 1, 1), "2026-01-01T00:00:00"), (None, "")],
    )
    def test_iso_formatting(self, value, expected):
        assert al._fmt_iso(value) == expected

    @pytest.mark.parametrize(
        "value,expected", [(USER_UUID, str(USER_UUID)), (None, ""), ("", "")]
    )
    def test_string_formatting(self, value, expected):
        assert al._fmt_str(value) == expected

    def test_a_row_has_one_cell_per_declared_column(self):
        assert len(al._audit_log_row(_entry())) == len(al._CSV_COLUMNS)

"""
Tests for the expand-contract migration guard (Phase 13.1).
"""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_migrations.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_migrations", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(tmp_path, body: str) -> Path:
    p = tmp_path / "m.py"
    p.write_text("from alembic import op\nimport sqlalchemy as sa\n\n" + body)
    return p


def test_flags_drop_table_in_upgrade(tmp_path):
    mod = _load()
    p = _write(tmp_path, "def upgrade():\n    op.drop_table('widget')\n")
    findings = mod._check_file(p)
    assert findings and "drop_table" in findings[0][1]


def test_flags_column_rename(tmp_path):
    mod = _load()
    p = _write(
        tmp_path,
        "def upgrade():\n    op.alter_column('t', 'a', new_column_name='b')\n",
    )
    findings = mod._check_file(p)
    assert any("rename" in w for _ln, w in findings)


def test_flags_destructive_raw_sql(tmp_path):
    mod = _load()
    p = _write(tmp_path, "def upgrade():\n    op.execute('DROP TABLE widget')\n")
    findings = mod._check_file(p)
    assert any("SQL" in w for _ln, w in findings)


def test_downgrade_is_exempt(tmp_path):
    mod = _load()
    p = _write(tmp_path, "def downgrade():\n    op.drop_table('widget')\n")
    assert mod._check_file(p) == []


def test_allowlist_marker_suppresses(tmp_path):
    mod = _load()
    p = _write(
        tmp_path,
        "def upgrade():\n"
        "    # expand-contract-ok: contract step\n"
        "    op.drop_table('widget')\n",
    )
    assert mod._check_file(p) == []


def test_additive_upgrade_is_clean(tmp_path):
    mod = _load()
    p = _write(
        tmp_path,
        "def upgrade():\n    op.add_column('t', sa.Column('c', sa.String()))\n",
    )
    assert mod._check_file(p) == []

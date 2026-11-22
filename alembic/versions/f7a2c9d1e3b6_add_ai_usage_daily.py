"""Add ai_usage_daily (daily AI request and token counters), ownership-aware.

Same strategy as e5f1a7c92b04 (and d82a61f4b903): whether the table pre-existed cannot
be derived from the schema (a create_all()-built database already has it), so upgrade()
records what IT creates, as one entry in the JSON comment on the alembic_version table
(key = this revision id, value = {"tables": ["ai_usage_daily"]}). Records belonging to
other revisions in that shared comment are carried over unchanged.

upgrade()
- Table absent: create it and record ownership.
- Table present: validate it against the model (columns, types, nullability, primary
  key, the unique key on (scope, usage_date), and the server defaults the quota code
  relies on: id generated, requests/tokens 0, updated_at now()). Compatible: leave it
  untouched and do NOT claim ownership. Incompatible: raise "Incompatible existing
  schema" and change nothing. Extra columns are tolerated only when nullable or when
  they have a default/identity/generated value, because the quota INSERT does not
  supply them; an extra NOT NULL column without one is rejected.
- A malformed shared comment, or a malformed record for this revision, is refused
  before anything is changed.

downgrade()
- Valid record + empty table: drop the table, remove ONLY this revision's key.
- Valid record + rows present: refuse (nothing changes; the usage data is kept).
- No record, malformed comment or malformed record: preserve the table and comment.

Online mode only (it inspects the live database); --sql is not supported.

Revision ID: f7a2c9d1e3b6
Revises: e5f1a7c92b04
"""

import json

from alembic import op
import sqlalchemy as sa

revision = "f7a2c9d1e3b6"
down_revision = "e5f1a7c92b04"
branch_labels = None
depends_on = None

_REV = "f7a2c9d1e3b6"
TABLE = "ai_usage_daily"
UNIQUE_NAME = "uq_ai_usage_daily_scope_date"


# ---- shared ownership comment (same mechanism and format as e5f1a7c92b04) ----------
def _own_load(strict=True):
    """Whole shared record dict. Malformed: raise (strict, upgrade) or return None."""
    raw = op.get_bind().execute(
        sa.text("SELECT obj_description(to_regclass('alembic_version'), 'pg_class')")).scalar()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except Exception as exc:  # noqa: BLE001
        if strict:
            raise RuntimeError("alembic_version has an unexpected comment; refusing to overwrite it") from exc
        return None


def _own_save(data):
    if data:
        text_ = json.dumps(data, sort_keys=True).replace("'", "''")
        op.execute(f"COMMENT ON TABLE alembic_version IS '{text_}'")
    else:
        op.execute("COMMENT ON TABLE alembic_version IS NULL")


def _record_valid(rec):
    """True only for {"tables": [<only this revision's table>]} (no other keys)."""
    return (
        isinstance(rec, dict)
        and set(rec) <= {"tables"}
        and isinstance(rec.get("tables", []), list)
        and all(isinstance(t, str) and t == TABLE for t in rec.get("tables", []))
    )


def _owns_table(data):
    rec = (data or {}).get(_REV)
    return _record_valid(rec) and TABLE in rec.get("tables", [])


# ---- validation of a pre-existing table --------------------------------------------
# Server defaults the model declares (src/models/ai_usage.py) and the quota code relies on:
# requests/tokens server_default="0", updated_at server_default=func.now(). A test compares
# these constants with the model so they cannot drift apart silently.
EXPECTED_DEFAULTS = {"requests": "0", "tokens": "0", "updated_at": "now()"}
_NOW_FORMS = {"now()", "current_timestamp", "transaction_timestamp()"}  # equivalent in PostgreSQL


def _norm_default(raw):
    """Canonical text of a reflected server default: no cast, quotes or outer parentheses."""
    if raw is None:
        return None
    text_ = str(raw).strip().lower()
    while text_.startswith("(") and text_.endswith(")"):
        text_ = text_[1:-1].strip()
    text_ = text_.split("::")[0].strip()
    return text_.strip("'")


def _default_ok(column, raw):
    value = _norm_default(raw)
    if value is None:
        return False
    if column == "updated_at":
        return value in _NOW_FORMS
    return value == EXPECTED_DEFAULTS[column]


def _check_existing():
    insp = sa.inspect(op.get_bind())
    cols = {c["name"]: c for c in insp.get_columns(TABLE)}
    problems = []

    def need(name, kind, nullable, length=None, tz=None):
        c = cols.get(name)
        if c is None:
            problems.append(f"{TABLE}.{name}: column missing")
            return
        t = c["type"]
        if not isinstance(t, kind):
            problems.append(f"{TABLE}.{name}: type {t!r} is not {kind.__name__}")
        elif length is not None and getattr(t, "length", None) != length:
            problems.append(f"{TABLE}.{name}: length {getattr(t, 'length', None)} is not {length}")
        elif tz is not None and bool(getattr(t, "timezone", False)) != tz:
            problems.append(f"{TABLE}.{name}: timezone flag differs")
        if bool(c["nullable"]) != nullable:
            problems.append(f"{TABLE}.{name}: nullable={c['nullable']} but expected {nullable}")
        if name in EXPECTED_DEFAULTS and not _default_ok(name, c.get("default")):
            problems.append(
                f"{TABLE}.{name}: server default {c.get('default')!r} is not the expected "
                f"{EXPECTED_DEFAULTS[name]!r}")

    need("id", sa.Integer, False)
    need("scope", sa.String, False, length=64)
    need("usage_date", sa.Date, False)
    need("requests", sa.Integer, False)
    need("tokens", sa.Integer, False)
    need("updated_at", sa.DateTime, True, tz=True)

    # id must generate its own value (the quota INSERT never supplies it).
    ident = cols.get("id")
    if ident is not None:
        generated = ident.get("identity") or str(ident.get("default") or "").lower().startswith("nextval(")
        if not generated:
            problems.append(f"{TABLE}.id: no generated value (serial/identity); inserts would fail")

    # Columns the model does not know are tolerated only if the INSERT can omit them.
    known = {"id", "scope", "usage_date", "requests", "tokens", "updated_at"}
    for name, c in cols.items():
        if name in known or c["nullable"]:
            continue
        if c.get("default") is None and not c.get("identity") and not c.get("computed"):
            problems.append(
                f"{TABLE}.{name}: extra NOT NULL column without a default; the quota INSERT would fail")

    if insp.get_pk_constraint(TABLE).get("constrained_columns") != ["id"]:
        problems.append(f"{TABLE}: primary key must be exactly (id)")
    wanted = ["scope", "usage_date"]
    unique = [u["column_names"] for u in insp.get_unique_constraints(TABLE)]
    unique += [i["column_names"] for i in insp.get_indexes(TABLE) if i.get("unique")]
    if wanted not in unique:
        problems.append(f"{TABLE}: unique key on (scope, usage_date) missing (needed by the quota upsert)")
    return problems


def upgrade() -> None:
    # Before ANY change: the shared comment and this revision's record must be sound.
    data = _own_load()
    if _REV in data and not _record_valid(data[_REV]):
        raise RuntimeError(
            f"The {_REV} ownership record in alembic_version is malformed; "
            "refusing to modify it. Nothing was changed.")

    if sa.inspect(op.get_bind()).has_table(TABLE):
        problems = _check_existing()
        if problems:
            raise RuntimeError(
                "Incompatible existing schema; nothing was changed. Fix manually, then retry:\n  - "
                + "\n  - ".join(problems))
        return  # compatible and pre-existing: left untouched, ownership NOT claimed

    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("scope", "usage_date", name=UNIQUE_NAME),
    )
    data[_REV] = {"tables": [TABLE]}  # other revisions' records are carried over unchanged
    _own_save(data)


def downgrade() -> None:
    data = _own_load(strict=False)
    if data is None:
        return  # malformed shared record: preserve everything, leave it untouched
    if not _owns_table(data):
        return  # no valid ownership record: preserve the table and the comment untouched

    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE):
        rows = bind.execute(sa.text(f"SELECT count(*) FROM {TABLE}")).scalar()
        if rows:
            raise RuntimeError(f"Refusing to drop non-empty table '{TABLE}' during downgrade.")
        op.drop_table(TABLE)

    del data[_REV]  # only this revision's key; every other record is kept as it was
    _own_save(data)

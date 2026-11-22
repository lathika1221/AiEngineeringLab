"""Add persistent conversations and link chats.

Every step is guarded by an inspection check, and every pre-existing object this
revision would otherwise accept is VALIDATED first (before any DDL):
  * conversations: columns, types, nullability, primary key, foreign keys (target
    table, referenced column, ON DELETE), index columns and uniqueness, required
    now() defaults, and unknown NOT NULL columns without a default;
  * chats.conversation_id: type, nullability, FK (target, referenced column,
    ON DELETE) and index definition.
An incompatible existing object raises "Incompatible existing schema" and the whole
upgrade rolls back; nothing existing is altered and no data is touched. A missing
FK/index is added additively. A missing conversations.project_id FK is tolerated
here because e5f1a7c92b04 adds and validates it.

Ownership: upgrade() records exactly the objects IT created in one JSON comment on
the alembic_version table (key = this revision id), after validating any existing
record for this revision against the complete schema and name whitelist. A
malformed or unknown record is never overwritten or deleted (upgrade refuses); a
valid one is merged, never replaced. downgrade() removes ONLY recorded objects,
refuses to drop an owned table or column that holds data, and is a safe no-op when
the record is missing, malformed or establishes nothing. Other revisions' records
in the same comment are preserved.

Online mode only (it inspects the live database); --sql is not supported.
"""

import json

from alembic import op
import sqlalchemy as sa

revision = "d82a61f4b903"
down_revision = "c30d77670cf2"
branch_labels = None
depends_on = None

_REV = "d82a61f4b903"
_created = {"tables": [], "columns": [], "indexes": [], "constraints": []}

# Everything a record may legitimately name. Anything else => record is malformed.
_ALLOWED = {
    "tables": {"projects", "conversations"},
    "columns": {"chats.conversation_id"},
    "indexes": {"ix_conversations_id", "ix_conversations_user_id", "ix_conversations_project_id",
                "ix_chats_conversation_id"},
    "constraints": {"chats.fk_chats_conversation_id_conversations"},
}
_FK_NAME = "fk_chats_conversation_id_conversations"

# type specs: "int" | "text" | ("str", length) | ("ts", with_timezone)
# fks: (column, referred_table, ondelete, required)  -- a missing non-required FK is repaired/tolerated
_CONV_SPEC = {
    "columns": {"id": ("int", False), "user_id": ("int", False), "project_id": ("int", True),
                "title": (("str", 200), False), "category": (("str", 50), False),
                "created_at": (("ts", True), False), "updated_at": (("ts", True), False)},
    "pk": ["id"],
    "fks": [("user_id", "users", "CASCADE", True), ("project_id", "projects", "SET NULL", False)],
    "indexes": [("ix_conversations_id", ["id"], False), ("ix_conversations_user_id", ["user_id"], False),
                ("ix_conversations_project_id", ["project_id"], False)],
    "server_defaults": ["created_at", "updated_at"],
    "known": (),
}
_CHATS_SPEC = {
    "columns": {"conversation_id": ("int", True)},
    "pk": None,
    "fks": [("conversation_id", "conversations", "SET NULL", False)],
    "indexes": [("ix_chats_conversation_id", ["conversation_id"], False)],
    "server_defaults": [],
    "known": ("id", "user_id", "project_id", "user_message", "ai_response", "created_at"),
}


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return _insp().has_table(name)


# ---- ownership record ------------------------------------------------------------

def _own_load():
    """Return the whole ownership dict; raise if the shared comment is malformed."""
    data = _own_load_tolerant()
    if data is None:
        raise RuntimeError("alembic_version has an unexpected comment; refusing to overwrite it")
    return data


def _own_load_tolerant():
    raw = op.get_bind().execute(
        sa.text("SELECT obj_description(to_regclass('alembic_version'), 'pg_class')")).scalar()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def _own_save(data):
    if data:
        text_ = json.dumps(data, sort_keys=True).replace("'", "''")
        op.execute(f"COMMENT ON TABLE alembic_version IS '{text_}'")
    else:
        op.execute("COMMENT ON TABLE alembic_version IS NULL")


def _record_valid(rec):
    """True only for a dict with known keys whose values are lists of whitelisted names."""
    if not isinstance(rec, dict) or set(rec) - set(_ALLOWED):
        return False
    return all(isinstance(rec.get(k, []), list)
               and all(isinstance(i, str) and i in names for i in rec.get(k, []))
               for k, names in _ALLOWED.items())


def _owned_record(data):
    """This revision's VALIDATED record, or {} (owns nothing) if absent/malformed/unknown names."""
    rec = (data or {}).get(_REV)
    if not _record_valid(rec):
        return {}
    return {k: list(rec.get(k, [])) for k in _ALLOWED}


# ---- validation of pre-existing objects ------------------------------------------

def _type_ok(t, expected):
    if expected == "int":
        return isinstance(t, sa.Integer) and not isinstance(t, (sa.BigInteger, sa.SmallInteger))
    if expected == "text":
        return isinstance(t, sa.Text)
    kind, arg = expected
    if kind == "str":
        return isinstance(t, sa.String) and not isinstance(t, sa.Text) and t.length == arg
    if kind == "ts":
        return isinstance(t, sa.DateTime) and bool(getattr(t, "timezone", False)) == arg
    raise AssertionError(expected)


def _ondelete(fk):
    v = ((fk.get("options") or {}).get("ondelete") or "").upper()
    return None if v in ("", "NO ACTION") else v


def _fk_state(table, column, referred, ondelete):
    """'ok' | 'missing' | 'wrong: <what exists>'.

    ok requires: constrained column, referred table, referred column (id) and ON DELETE.
    """
    on_col = [fk for fk in _insp().get_foreign_keys(table) if fk["constrained_columns"] == [column]]
    if not on_col:
        return "missing"
    if any(fk["referred_table"] == referred and fk["referred_columns"] == ["id"]
           and _ondelete(fk) == ondelete for fk in on_col):
        return "ok"
    found = [(fk["referred_table"], fk["referred_columns"], _ondelete(fk)) for fk in on_col]
    return f"wrong: {found}"


def _has_fk(table, column, referred, ondelete):
    return _fk_state(table, column, referred, ondelete) == "ok"


def _index_state(table, name, columns, unique):
    """'ok' | 'missing' | 'wrong: <what exists>'. ok requires name, columns AND uniqueness."""
    ix = next((i for i in _insp().get_indexes(table) if i["name"] == name), None)
    if ix is None:
        return "missing"
    if list(ix["column_names"]) == columns and bool(ix.get("unique")) == unique:
        return "ok"
    return f"wrong: on {list(ix['column_names'])} unique={bool(ix.get('unique'))}"


def _check(table, spec, optional=()):
    """Inspect an EXISTING table. Returns (problems, missing_fks, missing_indexes)."""
    insp = _insp()
    problems, missing_fks, missing_indexes = [], [], []
    cols = {c["name"]: c for c in insp.get_columns(table)}
    for name, (typ, nullable) in spec["columns"].items():
        c = cols.get(name)
        if c is None:
            if name not in optional:
                problems.append(f"{table}.{name}: column is missing")
            continue
        if not _type_ok(c["type"], typ):
            problems.append(f"{table}.{name}: type is {c['type']}, expected {typ}")
        if bool(c["nullable"]) != nullable:
            problems.append(f"{table}.{name}: nullable is {bool(c['nullable'])}, expected {nullable}")
    known = set(spec["columns"]) | set(spec["known"])
    for name, c in cols.items():
        if name not in known and not c["nullable"] and c.get("default") is None \
                and not c.get("identity") and not c.get("computed"):
            problems.append(f"{table}.{name}: unknown NOT NULL column without a server default "
                            f"(inserts by the application would fail)")
    if spec["pk"] is not None:
        pk = list(insp.get_pk_constraint(table).get("constrained_columns") or [])
        if pk != spec["pk"]:
            problems.append(f"{table}: primary key is {pk}, expected {spec['pk']}")
    for name in spec["server_defaults"]:
        c = cols.get(name)
        if c is not None:
            d = str(c.get("default") or "").lower()
            if "now()" not in d and "current_timestamp" not in d:
                problems.append(f"{table}.{name}: server default is {c.get('default')!r}, expected now()")
    for col, ref, ondelete, required in spec["fks"]:
        if col not in cols:
            continue
        state = _fk_state(table, col, ref, ondelete)
        if state.startswith("wrong"):
            problems.append(f"{table}.{col}: foreign key is {state[7:]}, expected ({ref}, ['id'], {ondelete})")
        elif state == "missing":
            if required:
                problems.append(f"{table}.{col}: required foreign key to {ref} is missing")
            else:
                missing_fks.append((col, ref, ondelete))
    for name, icols, unique in spec["indexes"]:
        if any(c not in cols for c in icols):
            continue
        state = _index_state(table, name, icols, unique)
        if state.startswith("wrong"):
            problems.append(f"{table}: index {name} is {state[7:]}, expected on {icols} unique={unique}")
        elif state == "missing":
            missing_indexes.append((name, icols, unique))
    return problems, missing_fks, missing_indexes


def _incompatible(problems):
    return RuntimeError(
        "Incompatible existing schema; nothing was changed. Fix manually, then retry:\n  - "
        + "\n  - ".join(problems))


def _validate_existing():
    problems = []
    if _table_exists("conversations"):
        problems += _check("conversations", _CONV_SPEC)[0]
    problems += _check("chats", _CHATS_SPEC, optional=("conversation_id",))[0]
    return problems


def _ensure_index(name, table, columns):
    state = _index_state(table, name, columns, False)
    if state == "missing":
        op.create_index(name, table, columns)
        _created["indexes"].append(name)
    elif state != "ok":  # validated earlier; defensive
        raise _incompatible([f"{table}: index {name} is {state}"])


# ---- upgrade / downgrade -----------------------------------------------------------

def upgrade() -> None:
    for v in _created.values():
        v.clear()

    # Before ANY change: the shared comment and this revision's record must be sound.
    data = _own_load()
    if _REV in data and not _record_valid(data[_REV]):
        raise RuntimeError(
            f"The {_REV} ownership record in alembic_version is malformed or names unknown "
            f"objects; refusing to modify it. Nothing was changed.")
    problems = _validate_existing()
    if problems:
        raise _incompatible(problems)

    # "projects" is created by no earlier migration, but "conversations" references it.
    if not _table_exists("projects"):
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("engine", sa.String(length=50), nullable=True),
            sa.Column("tech_stack", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        )
        op.create_index("ix_projects_id", "projects", ["id"])
        op.create_index("ix_projects_user_id", "projects", ["user_id"])
        _created["tables"].append("projects")

    if not _table_exists("conversations"):
        op.create_table(
            "conversations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
            sa.Column("title", sa.String(length=200), nullable=False, server_default="New Chat"),
            sa.Column("category", sa.String(length=50), nullable=False, server_default="general"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        op.create_index("ix_conversations_id", "conversations", ["id"])
        op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
        op.create_index("ix_conversations_project_id", "conversations", ["project_id"])
        _created["tables"].append("conversations")
    else:
        for name, cols, _unique in _CONV_SPEC["indexes"]:
            _ensure_index(name, "conversations", cols)

    if "conversation_id" not in {c["name"] for c in _insp().get_columns("chats")}:
        op.add_column("chats", sa.Column("conversation_id", sa.Integer(), nullable=True))
        _created["columns"].append("chats.conversation_id")
    if not _has_fk("chats", "conversation_id", "conversations", "SET NULL"):
        op.create_foreign_key(_FK_NAME, "chats", "conversations", ["conversation_id"], ["id"],
                              ondelete="SET NULL")
        _created["constraints"].append(f"chats.{_FK_NAME}")
    _ensure_index("ix_chats_conversation_id", "chats", ["conversation_id"])

    # The end state must now be valid.
    leftover = _validate_existing()
    for table, spec, optional in (("conversations", _CONV_SPEC, ()), ("chats", _CHATS_SPEC, ())):
        _, mf, mi = _check(table, spec, optional)
        leftover += [f"{table}: foreign key still missing: {x}" for x in mf if table == "chats"] \
            + [f"{table}: index still missing: {x[0]}" for x in mi]
    if leftover:
        raise _incompatible(leftover)

    # Record what was actually created here, merged into any existing (validated) record.
    existing = _owned_record(data)
    merged = {k: list(existing.get(k, [])) for k in _ALLOWED}
    for kind, items in _created.items():
        merged[kind] += [i for i in items if i not in merged[kind]]
    if any(_created.values()):
        data[_REV] = merged
        _own_save(data)  # other revisions' records are carried over unchanged


def _count(table, where=""):
    return op.get_bind().execute(sa.text(f"SELECT count(*) FROM {table} {where}")).scalar()


def downgrade() -> None:
    data = _own_load_tolerant()
    if data is None:
        return  # malformed shared record: preserve everything, leave the record untouched
    owned = _owned_record(data)
    if not owned:
        return  # no (valid) ownership of anything: preserve everything, leave record untouched

    drop_tables = [t for t in ("conversations", "projects") if t in owned["tables"]]
    # Refuse to destroy data. Nothing is changed unless every check passes.
    for table in drop_tables:
        if _table_exists(table) and _count(table):
            raise RuntimeError(f"Refusing to drop non-empty table '{table}' during downgrade.")
    chat_cols = {c["name"] for c in _insp().get_columns("chats")}
    if "chats.conversation_id" in owned["columns"] and "conversation_id" in chat_cols \
            and _count("chats", "WHERE conversation_id IS NOT NULL"):
        raise RuntimeError("Refusing to drop chats.conversation_id: it contains data.")

    # Remove ONLY recorded objects.
    for item in owned["constraints"]:
        table, name = item.split(".", 1)
        if any(fk.get("name") == name for fk in _insp().get_foreign_keys(table)):
            op.drop_constraint(name, table, type_="foreignkey")
    for name in owned["indexes"]:
        op.execute(f'DROP INDEX IF EXISTS "{name}"')
    if "chats.conversation_id" in owned["columns"] and "conversation_id" in chat_cols:
        op.drop_column("chats", "conversation_id")
    for table in drop_tables:
        if _table_exists(table):
            op.drop_table(table)

    data.pop(_REV, None)
    _own_save(data)

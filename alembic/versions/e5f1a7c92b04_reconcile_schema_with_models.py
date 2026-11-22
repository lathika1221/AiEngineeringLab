"""Reconcile schema with ORM models (additive, idempotent).

Adds everything the ORM models define that earlier migrations never created:
the projects, memories, user_profiles, life_roles and goals tables, and
chats.project_id (+ index + FK). Every step is guarded by an inspection check,
so the revision is safe on a fresh database, on a database stamped at
d82a61f4b903, and on a database that was built from the models directly.
Existing objects are never altered or dropped by upgrade().

Existing tables are VALIDATED against the models before anything is changed
(columns, types, nullability, primary key, foreign keys incl. ON DELETE, index
columns and uniqueness, required server defaults). A missing foreign key or
index is added; anything else that is wrong (missing column, wrong type or
nullability, wrong ON DELETE, wrong index definition, missing primary key or
default) raises "Incompatible existing schema" and the whole upgrade is rolled
back. Nothing existing is altered and no data is touched. Extra columns that
the models do not know about are tolerated.

Ownership and downgrade: whether an object pre-existed cannot be derived from the
schema (a create_all()-built database already has all of it, even when empty). So
upgrade() records what IT creates, as one JSON comment on the alembic_version table
(key = this revision id). That table is never compared with the models, so the
record cannot disturb autogenerate. downgrade() removes ONLY recorded objects, and
still refuses if an owned table has rows or an owned column holds data. If the
record is missing, downgrade() drops nothing (the safe direction). Objects that
pre-existed are never dropped, even when empty; on such a database downgrade()
is therefore a (deliberate) no-op for them. Consequence: a database built outside
Alembic cannot be downgraded to base through these migrations; it fails safely.

Online mode only: it inspects the live database, so --sql is not supported.

Revision ID: e5f1a7c92b04
Revises: d82a61f4b903
"""

import json

from alembic import op
import sqlalchemy as sa

revision = "e5f1a7c92b04"
down_revision = "d82a61f4b903"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(name):
    return _insp().has_table(name)


def _index_names(table):
    return {i["name"] for i in _insp().get_indexes(table)}


def _utc_naive():
    return sa.DateTime()


def _create_projects():
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


def _create_memories():
    op.create_table(
        "memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("memory_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", _utc_naive(), nullable=False),
        sa.Column("updated_at", _utc_naive(), nullable=False),
    )


def _create_user_profiles():
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("timezone", sa.String(length=100), nullable=True),
        sa.Column("onboarding_completed", sa.String(length=10), nullable=False),
        sa.Column("created_at", _utc_naive(), nullable=False),
        sa.Column("updated_at", _utc_naive(), nullable=False),
    )


def _create_life_roles():
    op.create_table(
        "life_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("created_at", _utc_naive(), nullable=False),
    )


def _create_goals():
    op.create_table(
        "goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("target_date", _utc_naive(), nullable=True),
        sa.Column("created_at", _utc_naive(), nullable=False),
        sa.Column("updated_at", _utc_naive(), nullable=False),
    )


_REV = "e5f1a7c92b04"
_created = {"tables": [], "columns": [], "indexes": [], "constraints": []}


def _own_load(strict=True):
    """Return the whole ownership dict. Malformed: raise (strict, used by upgrade) or None."""
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


def _spec(columns, fks, indexes, pk=("id",), server_defaults=(), known=()):
    return {"columns": columns, "fks": fks, "indexes": indexes, "known": list(known),
            "pk": list(pk) if pk else None, "server_defaults": list(server_defaults)}


_ID = {"id": ("int", False)}
_IDX_ID = lambda t: (f"ix_{t}_id", ["id"], False)  # noqa: E731
_IDX_UID = lambda t, u=False: (f"ix_{t}_user_id", ["user_id"], u)  # noqa: E731

# type specs: "int" | "text" | ("str", length) | ("ts", with_timezone)
_SPECS = {
    "projects": _spec(
        {**_ID, "user_id": ("int", False), "name": (("str", 200), False), "description": ("text", True),
         "status": (("str", 50), False), "engine": (("str", 50), True), "tech_stack": ("text", True),
         "created_at": (("ts", True), True), "updated_at": (("ts", True), True)},
        [("user_id", "users", "CASCADE")],
        [_IDX_ID("projects"), _IDX_UID("projects")],
        server_defaults=("created_at", "updated_at")),
    "memories": _spec(
        {**_ID, "user_id": ("int", False), "memory_type": (("str", 50), False), "content": ("text", False),
         "created_at": (("ts", False), False), "updated_at": (("ts", False), False)},
        [("user_id", "users", None)],
        [_IDX_ID("memories"), _IDX_UID("memories")]),
    "user_profiles": _spec(
        {**_ID, "user_id": ("int", False), "display_name": (("str", 100), True), "bio": ("text", True),
         "timezone": (("str", 100), True), "onboarding_completed": (("str", 10), False),
         "created_at": (("ts", False), False), "updated_at": (("ts", False), False)},
        [("user_id", "users", None)],
        [_IDX_ID("user_profiles"), _IDX_UID("user_profiles", True)]),
    "life_roles": _spec(
        {**_ID, "user_id": ("int", False), "role": (("str", 100), False),
         "description": (("str", 500), True), "priority": ("int", False),
         "created_at": (("ts", False), False)},
        [("user_id", "users", None)],
        [_IDX_ID("life_roles"), _IDX_UID("life_roles")]),
    "goals": _spec(
        {**_ID, "user_id": ("int", False), "title": (("str", 200), False), "description": ("text", True),
         "category": (("str", 100), True), "priority": ("int", False), "status": (("str", 50), False),
         "target_date": (("ts", False), True), "created_at": (("ts", False), False),
         "updated_at": (("ts", False), False)},
        [("user_id", "users", None)],
        [_IDX_ID("goals"), _IDX_UID("goals")]),
}
_CREATORS = {"projects": _create_projects, "memories": _create_memories,
             "user_profiles": _create_user_profiles, "life_roles": _create_life_roles,
             "goals": _create_goals}

# Partial specs for the one column this revision adds / links on existing tables.
_CHATS_SPEC = _spec({"project_id": ("int", True)}, [("project_id", "projects", "SET NULL")],
                    [("ix_chats_project_id", ["project_id"], False)], pk=None,
                    known=("id", "user_id", "user_message", "ai_response", "created_at", "conversation_id"))
_CONV_SPEC = _spec({"project_id": ("int", True)}, [("project_id", "projects", "SET NULL")],
                   [("ix_conversations_project_id", ["project_id"], False)], pk=None,
                   known=("id", "user_id", "title", "category", "created_at", "updated_at"))

_DROP_ORDER = ["goals", "life_roles", "user_profiles", "memories", "projects"]  # reverse creation order


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


def _check(table, spec, optional=()):
    """Inspect an EXISTING table. Returns (problems, missing_fks, missing_indexes).

    problems are unrepairable incompatibilities; missing fks/indexes are additive repairs.
    """
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
    fks = insp.get_foreign_keys(table)
    for col, ref, ondelete in spec["fks"]:
        if col not in cols:
            continue
        on_col = [fk for fk in fks if fk["constrained_columns"] == [col]]
        if not on_col:
            missing_fks.append((col, ref, ondelete))
        elif not any(fk["referred_table"] == ref and fk["referred_columns"] == ["id"]
                     and _ondelete(fk) == ondelete for fk in on_col):
            found = [(fk["referred_table"], fk["referred_columns"], _ondelete(fk)) for fk in on_col]
            problems.append(f"{table}.{col}: foreign key is {found}, expected ({ref}, ['id'], {ondelete})")
    indexes = {i["name"]: i for i in insp.get_indexes(table)}
    for name, icols, unique in spec["indexes"]:
        if any(c not in cols for c in icols):
            continue
        ix = indexes.get(name)
        if ix is None:
            missing_indexes.append((name, icols, unique))
        elif list(ix["column_names"]) != icols or bool(ix.get("unique")) != unique:
            problems.append(
                f"{table}: index {name} is on {list(ix['column_names'])} unique={bool(ix.get('unique'))}, "
                f"expected on {icols} unique={unique}")
    return problems, missing_fks, missing_indexes


def _targets():
    t = [(name, spec, ()) for name, spec in _SPECS.items() if _has_table(name)]
    t.append(("chats", _CHATS_SPEC, ("project_id",)))
    if _has_table("conversations"):
        t.append(("conversations", _CONV_SPEC, ()))
    return t


def _incompatible(problems):
    return RuntimeError(
        "Incompatible existing schema; nothing was changed. Fix manually, then retry:\n  - "
        + "\n  - ".join(problems))


def upgrade() -> None:
    for v in _created.values():
        v.clear()
    # Before ANY change: the shared comment and this revision's record must be sound.
    data = _own_load()
    if _REV in data and not _record_valid(data[_REV]):
        raise RuntimeError(
            f"The {_REV} ownership record in alembic_version is malformed or names unknown "
            f"objects; refusing to modify it. Nothing was changed.")
    # Phase 1: validate everything that already exists before changing anything.
    problems = []
    for table, spec, optional in _targets():
        problems += _check(table, spec, optional)[0]
    if problems:
        raise _incompatible(problems)

    # Phase 2: additive changes only.
    for table, creator in _CREATORS.items():
        if not _has_table(table):
            creator()
            _created["tables"].append(table)
    if "project_id" not in {c["name"] for c in _insp().get_columns("chats")}:
        op.add_column("chats", sa.Column("project_id", sa.Integer(), nullable=True))
        _created["columns"].append("chats.project_id")
    for table, spec, optional in _targets():
        _, missing_fks, missing_indexes = _check(table, spec, optional)
        for col, ref, ondelete in missing_fks:
            fk_name = f"fk_{table}_{col}_{ref}"
            op.create_foreign_key(fk_name, table, ref, [col], ["id"], ondelete=ondelete)
            _created["constraints"].append(f"{table}.{fk_name}")
        for name, cols, unique in missing_indexes:
            op.create_index(name, table, cols, unique=unique)
            _created["indexes"].append(name)

    # Phase 3: the end state must now match the models exactly.
    leftover = []
    for table, spec, optional in _targets():
        p, mf, mi = _check(table, spec, optional)
        leftover += p + [f"{table}: foreign key still missing: {x}" for x in mf] \
            + [f"{table}: index still missing: {x[0]}" for x in mi]
    if leftover:
        raise _incompatible(leftover)

    # Record what was actually created here, merged into any existing (validated) record.
    existing = _owned_record(data)
    merged = {k: list(existing.get(k, [])) for k in _created}
    for kind, items in _created.items():
        merged[kind] += [i for i in items if i not in merged[kind]]
    if any(_created.values()):
        data[_REV] = merged
        _own_save(data)  # other revisions' records are carried over unchanged


def _count(table, where=""):
    return op.get_bind().execute(sa.text(f"SELECT count(*) FROM {table} {where}")).scalar()


def _allowed():
    fks = {f"{t}.fk_{t}_{c}_{r}" for t, sp in [*_SPECS.items(), ("chats", _CHATS_SPEC),
                                                  ("conversations", _CONV_SPEC)] for c, r, _ in sp["fks"]}
    idx = {n for sp in [*_SPECS.values(), _CHATS_SPEC, _CONV_SPEC] for n, _, _ in sp["indexes"]}
    return {"tables": set(_SPECS), "columns": {"chats.project_id"}, "indexes": idx, "constraints": fks}


def _record_valid(rec):
    """True only for a dict with known keys whose values are lists of whitelisted names."""
    allowed = _allowed()
    if not isinstance(rec, dict) or set(rec) - set(allowed):
        return False
    return all(isinstance(rec.get(k, []), list) and all(isinstance(i, str) and i in names for i in rec.get(k, []))
               for k, names in allowed.items())


def _owned_record(data):
    """This revision's VALIDATED record, or {} (owns nothing) if absent/malformed/unknown names."""
    rec = (data or {}).get(_REV)
    if not _record_valid(rec):
        return {}
    return {k: list(rec.get(k, [])) for k in _allowed()}


def downgrade() -> None:
    data = _own_load(strict=False)
    if data is None:
        return  # malformed shared record: preserve everything, leave the record untouched
    owned = _owned_record(data)
    if not owned:
        return  # no (valid) ownership of anything: preserve everything, leave record untouched
    owned_tables = set(owned["tables"])
    owned_columns = [tuple(c.split(".", 1)) for c in owned["columns"]]
    drop_tables = [t for t in _DROP_ORDER if t in owned_tables]

    # Refuse to destroy data. Nothing is changed unless every check passes.
    for table in drop_tables:
        if _has_table(table) and _count(table):
            raise RuntimeError(f"Refusing to drop non-empty table '{table}' during downgrade.")
    if ("chats", "project_id") in owned_columns and _count("chats", "WHERE project_id IS NOT NULL"):
        raise RuntimeError("Refusing to drop chats.project_id: it contains data.")

    # Remove ONLY what this revision recorded as created by it.
    for item in owned["constraints"]:
        table, name = item.split(".", 1)
        if any(fk.get("name") == name for fk in _insp().get_foreign_keys(table)):
            op.drop_constraint(name, table, type_="foreignkey")
    for name in owned["indexes"]:
        op.execute(f'DROP INDEX IF EXISTS "{name}"')
    for table, column in owned_columns:
        if column in {c["name"] for c in _insp().get_columns(table)}:
            op.drop_column(table, column)
    for table in drop_tables:
        if _has_table(table):
            op.drop_table(table)

    data.pop(_REV, None)
    _own_save(data)

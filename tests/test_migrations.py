"""Alembic migration tests against ISOLATED throwaway PostgreSQL databases.

DB-backed tests are skipped unless LATZ_TEST_PG_ADMIN_URL is set to an admin URL
of a disposable PostgreSQL server (e.g. postgresql://postgres@127.0.0.1:55433/postgres).

Safety: the admin URL must name an explicit loopback host (localhost, 127.0.0.1
or ::1); anything else (remote host, unix socket, no host) is rejected BEFORE any
connection is made. Each test creates its own database named
``latz_mig_<12 hex>`` and may only ever drop a database matching that exact
pattern which this fixture created. The application's DATABASE_URL is never used.
"""
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ADMIN_URL = os.environ.get("LATZ_TEST_PG_ADMIN_URL")
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
DB_NAME_RE = re.compile(r"^latz_mig_[0-9a-f]{12}$")

ROOT = Path(__file__).resolve().parents[1]
E5 = "e5f1a7c92b04"
HEAD = "f7a2c9d1e3b6"  # ai_usage_daily (ownership-aware; see the f7a2 tests at the end)
D82 = "d82a61f4b903"
NEW_TABLES = {"projects", "memories", "user_profiles", "life_roles", "goals"}


def validate_admin_url(url):
    """Reject anything but an explicit loopback PostgreSQL host. No connection is made."""
    try:
        parsed = make_url(url)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("LATZ_TEST_PG_ADMIN_URL is not a valid database URL") from exc
    if not parsed.get_backend_name() == "postgresql":
        raise ValueError("LATZ_TEST_PG_ADMIN_URL must be a PostgreSQL URL")
    host = (parsed.host or "").lower()
    if host not in LOOPBACK_HOSTS:
        raise ValueError(
            f"Refusing to run: host {parsed.host!r} is not an explicit loopback host "
            f"({', '.join(sorted(LOOPBACK_HOSTS))})")


def _create_throwaway_db(admin_url):
    validate_admin_url(admin_url)  # before any engine/connection exists
    name = f"latz_mig_{uuid.uuid4().hex[:12]}"
    assert DB_NAME_RE.match(name)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()
    return name, make_url(admin_url).set(database=name).render_as_string(hide_password=False)


def _drop_throwaway_db(admin_url, name):
    validate_admin_url(admin_url)
    if not DB_NAME_RE.match(name):
        raise ValueError(f"Refusing to drop {name!r}: not a fixture-created throwaway name")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        admin.dispose()


@pytest.fixture
def dburl():
    if not ADMIN_URL:
        pytest.skip("LATZ_TEST_PG_ADMIN_URL not set")
    try:
        validate_admin_url(ADMIN_URL)
    except ValueError as exc:
        pytest.fail(str(exc), pytrace=False)
    name, url = _create_throwaway_db(ADMIN_URL)
    try:
        yield url
    finally:
        _drop_throwaway_db(ADMIN_URL, name)  # only the name created above


def alembic(url, *args, check=True):
    env = {**os.environ, "DATABASE_URL": url, "PYTHONDONTWRITEBYTECODE": "1"}
    for k, v in {
        "PROJECT_NAME": "t", "VERSION": "1", "SECRET_KEY": "k" * 40,
        "AI_PROVIDER": "groq", "MODEL_NAME": "m", "GROQ_API_KEY": "dummy",
    }.items():
        env.setdefault(k, v)
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    if check:
        assert r.returncode == 0, r.stderr[-2000:]
    return r


def tables(url):
    e = create_engine(url)
    try:
        with e.connect() as c:
            return {r[0] for r in c.execute(text(
                "select tablename from pg_tables where schemaname='public'"))}
    finally:
        e.dispose()


def scalar(url, sql):
    e = create_engine(url)
    try:
        with e.begin() as c:
            return c.execute(text(sql)).scalar()
    finally:
        e.dispose()


def execute(url, sql):
    e = create_engine(url)
    try:
        with e.begin() as c:
            c.execute(text(sql))
    finally:
        e.dispose()


# Known, accepted drift: d82a61f4b903 (already applied in existing databases)
# gives conversations.title/category DB-side defaults that the models express
# only as Python-side defaults. Accepted ONLY when the stored default expression
# is EXACTLY the documented value (as PostgreSQL reflects it), never a superset.
ACCEPTED_DRIFT = {
    ("conversations", "title"): "'New Chat'::character varying",
    ("conversations", "category"): "'general'::character varying",
}


def _is_accepted(x):
    if x[0] != "modify_default":
        return False
    expected = ACCEPTED_DRIFT.get((x[2], x[3]))
    return expected is not None and str(getattr(x[5], "arg", x[5])).strip() == expected


def diff_vs_models(url):
    remaining = []
    for d in _raw_diff(url):
        flat = d if isinstance(d, list) else [d]
        remaining.extend(x for x in flat if not _is_accepted(x))
    return remaining


def _raw_diff(url):
    import src.models  # noqa: F401
    from src.database.base import Base
    e = create_engine(url)
    try:
        with e.connect() as c:
            ctx = MigrationContext.configure(
                c, opts={"compare_type": True, "compare_server_default": True})
            return compare_metadata(ctx, Base.metadata)
    finally:
        e.dispose()


def version(url):
    return scalar(url, "select version_num from alembic_version")


def test_fresh_database_upgrade_matches_models(dburl):
    alembic(dburl, "upgrade", "head")
    assert version(dburl) == HEAD
    assert NEW_TABLES | {"users", "chats", "conversations"} <= tables(dburl)
    assert diff_vs_models(dburl) == []


def test_single_head_and_ids_preserved():
    r = alembic("postgresql://x@127.0.0.1:1/none", "heads")
    assert HEAD in r.stdout and len(r.stdout.strip().splitlines()) == 1
    hist = alembic("postgresql://x@127.0.0.1:1/none", "history").stdout
    for a, b in [("51cb59b42641", "c30d77670cf2"), ("c30d77670cf2", D82), (D82, E5), (E5, HEAD)]:
        assert f"{a} -> {b}" in hist


def test_upgrade_twice_is_noop(dburl):
    alembic(dburl, "upgrade", "head")
    alembic(dburl, "upgrade", "head")
    assert diff_vs_models(dburl) == []


def test_stamped_d82_missing_projects_and_chat_project_id(dburl):
    """DB at d82 built the old way: no projects table, no chats.project_id."""
    alembic(dburl, "upgrade", "c30d77670cf2")
    execute(dburl, """
        CREATE TABLE conversations (
          id SERIAL PRIMARY KEY,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          project_id INTEGER,
          title VARCHAR(200) NOT NULL DEFAULT 'New Chat',
          category VARCHAR(50) NOT NULL DEFAULT 'general',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
        CREATE INDEX ix_conversations_id ON conversations(id);
        CREATE INDEX ix_conversations_user_id ON conversations(user_id);
        CREATE INDEX ix_conversations_project_id ON conversations(project_id);
        ALTER TABLE chats ADD COLUMN conversation_id INTEGER;
        ALTER TABLE chats ADD CONSTRAINT fk_chats_conversation_id_conversations
          FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL;
        CREATE INDEX ix_chats_conversation_id ON chats(conversation_id);
        INSERT INTO users(username,email,hashed_password) VALUES('u','u@x.io','h');
        INSERT INTO conversations(user_id,title,category) VALUES (1,'t','c');
        INSERT INTO chats(user_id,conversation_id,user_message,ai_response) VALUES (1,1,'q','a');
    """)
    alembic(dburl, "stamp", D82)
    alembic(dburl, "upgrade", "head")
    assert version(dburl) == HEAD
    assert diff_vs_models(dburl) == []
    assert scalar(dburl, "select count(*) from chats") == 1
    assert scalar(dburl, "select count(*) from conversations") == 1


def test_stamped_d82_missing_index_is_added(dburl):
    alembic(dburl, "upgrade", "head")
    execute(dburl, "DROP INDEX ix_chats_project_id; DROP INDEX ix_goals_user_id;")
    alembic(dburl, "stamp", D82)
    alembic(dburl, "upgrade", "head")
    assert diff_vs_models(dburl) == []


def test_full_downgrade_to_base_and_reupgrade(dburl):
    alembic(dburl, "upgrade", "head")
    alembic(dburl, "downgrade", "base")
    # f7a2 created ai_usage_daily (empty), so its downgrade removes it and its record.
    assert tables(dburl) == {"alembic_version"}
    assert _comment(dburl) is None
    alembic(dburl, "upgrade", "head")
    assert version(dburl) == HEAD
    assert diff_vs_models(dburl) == []


def test_head_downgrade_removes_only_its_own_objects(dburl):
    alembic(dburl, "upgrade", "head")
    alembic(dburl, "downgrade", D82)
    t = tables(dburl)
    assert {"memories", "user_profiles", "life_roles", "goals"}.isdisjoint(t)
    assert {"users", "chats", "conversations", "projects"} <= t
    cols = scalar(dburl, "select string_agg(column_name,',') from information_schema.columns "
                         "where table_name='chats'")
    assert "project_id" not in cols and "conversation_id" in cols


def snapshot(url):
    """Schema + data + revision fingerprint (columns, indexes, constraints, rows)."""
    e = create_engine(url)
    try:
        with e.connect() as c:
            def q(sql):
                return [tuple(r) for r in c.execute(text(sql))]
            names = [r[0] for r in q("select tablename from pg_tables where schemaname='public' order by 1")]
            return {
                "version": q("select version_num from alembic_version") if "alembic_version" in names else None,
                "columns": q("select table_name,column_name,data_type,udt_name,character_maximum_length,"
                             "is_nullable,column_default from information_schema.columns "
                             "where table_schema='public' order by 1,2"),
                "indexes": q("select tablename,indexname,indexdef from pg_indexes "
                             "where schemaname='public' order by 1,2"),
                "constraints": q("select conrelid::regclass::text,conname,contype,pg_get_constraintdef(oid) "
                                 "from pg_constraint where connamespace='public'::regnamespace order by 1,2"),
                "comments": q("select c.relname,d.objsubid,d.description from pg_description d join pg_class c "
                              "on c.oid=d.objoid and d.classoid='pg_class'::regclass "
                              "where c.relnamespace='public'::regnamespace "
                              "union all select cl.relname,0,d.description from pg_description d join pg_constraint con "
                              "on con.oid=d.objoid and d.classoid='pg_constraint'::regclass "
                              "join pg_class cl on cl.oid=con.conrelid "
                              "where cl.relnamespace='public'::regnamespace order by 1,2,3"),
                "data": {t: q(f'select to_jsonb(x)::text from "{t}" x order by 1') for t in names},
            }
    finally:
        e.dispose()


USER = "INSERT INTO users(username,email,hashed_password) VALUES('u','u@x.io','h');"
HEAD_ROWS = {
    "memories": "INSERT INTO memories(user_id,memory_type,content,created_at,updated_at) VALUES (1,'t','c',now(),now())",
    "user_profiles": "INSERT INTO user_profiles(user_id,onboarding_completed,created_at,updated_at) VALUES (1,'false',now(),now())",
    "life_roles": "INSERT INTO life_roles(user_id,role,priority,created_at) VALUES (1,'r',1,now())",
    "goals": "INSERT INTO goals(user_id,title,priority,status,created_at,updated_at) VALUES (1,'g',1,'active',now(),now())",
}


@pytest.mark.parametrize("table", sorted(HEAD_ROWS))
def test_head_downgrade_refusal_leaves_everything_unchanged(dburl, table):
    alembic(dburl, "upgrade", "head")
    execute(dburl, USER)
    execute(dburl, HEAD_ROWS[table])
    before = snapshot(dburl)
    r = alembic(dburl, "downgrade", D82, check=False)
    assert r.returncode != 0 and f"Refusing to drop non-empty table '{table}'" in r.stderr
    assert snapshot(dburl) == before
    assert before["version"] == [(HEAD,)]


def test_head_downgrade_refusal_for_chat_project_id_leaves_everything_unchanged(dburl):
    alembic(dburl, "upgrade", "head")
    execute(dburl, USER + """
        INSERT INTO projects(user_id,name,status) VALUES (1,'p','active');
        INSERT INTO chats(user_id,project_id,user_message,ai_response) VALUES (1,1,'q','a');""")
    before = snapshot(dburl)
    r = alembic(dburl, "downgrade", D82, check=False)
    assert r.returncode != 0 and "chats.project_id" in r.stderr
    assert snapshot(dburl) == before


def test_d82_downgrade_refusal_via_head_leaves_everything_unchanged(dburl):
    """head -> c30d: head step succeeds, d82 step refuses; the whole run must roll back."""
    alembic(dburl, "upgrade", "head")
    execute(dburl, USER + "INSERT INTO projects(user_id,name,status) VALUES (1,'p','active');")
    before = snapshot(dburl)
    r = alembic(dburl, "downgrade", "c30d77670cf2", check=False)
    assert r.returncode != 0 and "Refusing to drop non-empty table 'projects'" in r.stderr
    assert snapshot(dburl) == before
    assert before["version"] == [(HEAD,)]


def test_d82_downgrade_refusal_from_d82_leaves_everything_unchanged(dburl):
    alembic(dburl, "upgrade", "head")
    alembic(dburl, "downgrade", D82)
    execute(dburl, USER + "INSERT INTO projects(user_id,name,status) VALUES (1,'p','active');")
    before = snapshot(dburl)
    assert before["version"] == [(D82,)]
    r = alembic(dburl, "downgrade", "c30d77670cf2", check=False)
    assert r.returncode != 0 and "Refusing to drop non-empty table 'projects'" in r.stderr
    assert snapshot(dburl) == before


# ---- existing-schema validation -------------------------------------------------

def _fk_drop_sql(table, column):
    return (f"DO $$ DECLARE r record; BEGIN FOR r IN SELECT con.conname FROM pg_constraint con "
            f"JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=ANY(con.conkey) "
            f"WHERE con.contype='f' AND con.conrelid='{table}'::regclass AND a.attname='{column}' LOOP "
            f"EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I', r.conname); END LOOP; END $$;")


INCOMPATIBLE = {
    "missing_column": ("ALTER TABLE memories DROP COLUMN content", "memories.content: column is missing"),
    "wrong_type": ("ALTER TABLE goals ALTER COLUMN title TYPE TEXT", "goals.title: type is"),
    "wrong_length": ("ALTER TABLE goals ALTER COLUMN title TYPE VARCHAR(50)", "goals.title: type is"),
    "wrong_nullability": ("ALTER TABLE memories ALTER COLUMN content DROP NOT NULL", "memories.content: nullable"),
    "wrong_chat_project_id_type": (_fk_drop_sql("chats", "project_id")
                                   + "ALTER TABLE chats ALTER COLUMN project_id TYPE BIGINT",
                                   "chats.project_id: type is"),
    "no_primary_key": ("ALTER TABLE life_roles DROP CONSTRAINT life_roles_pkey", "life_roles: primary key"),
    "wrong_fk_ondelete_chats": (_fk_drop_sql("chats", "project_id")
                                + "ALTER TABLE chats ADD FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE",
                                "chats.project_id: foreign key"),
    "wrong_fk_ondelete_projects": (_fk_drop_sql("projects", "user_id")
                                   + "ALTER TABLE projects ADD FOREIGN KEY (user_id) REFERENCES users(id)",
                                   "projects.user_id: foreign key"),
    "wrong_fk_ondelete_conversations": (_fk_drop_sql("conversations", "project_id")
                                        + "ALTER TABLE conversations ADD FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE",
                                        "conversations.project_id: foreign key"),
    "index_not_unique": ("DROP INDEX ix_user_profiles_user_id; "
                         "CREATE INDEX ix_user_profiles_user_id ON user_profiles(user_id)",
                         "index ix_user_profiles_user_id"),
    "index_wrong_columns": ("DROP INDEX ix_goals_user_id; CREATE INDEX ix_goals_user_id ON goals(title)",
                            "index ix_goals_user_id"),
    "index_unexpectedly_unique": ("DROP INDEX ix_goals_user_id; CREATE UNIQUE INDEX ix_goals_user_id ON goals(user_id)",
                                  "index ix_goals_user_id"),
    "missing_default": ("ALTER TABLE projects ALTER COLUMN created_at DROP DEFAULT",
                        "projects.created_at: server default"),
}


@pytest.mark.parametrize("name", sorted(INCOMPATIBLE))
def test_incompatible_existing_schema_fails_safely(dburl, name):
    sql, fragment = INCOMPATIBLE[name]
    alembic(dburl, "upgrade", "head")
    execute(dburl, USER)
    execute(dburl, sql)
    alembic(dburl, "stamp", D82)
    before = snapshot(dburl)
    r = alembic(dburl, "upgrade", "head", check=False)
    assert r.returncode != 0, "incompatible schema was silently accepted"
    assert "Incompatible existing schema" in r.stderr and fragment in r.stderr, r.stderr[-1500:]
    assert snapshot(dburl) == before  # nothing altered, revision still d82, data intact


def test_incompatible_projects_present_before_d82_rolls_back_everything(dburl):
    alembic(dburl, "upgrade", "c30d77670cf2")
    execute(dburl, "CREATE TABLE projects (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id))")
    before = snapshot(dburl)
    r = alembic(dburl, "upgrade", "head", check=False)
    assert r.returncode != 0 and "Incompatible existing schema" in r.stderr
    assert "projects.name: column is missing" in r.stderr
    assert snapshot(dburl) == before
    assert before["version"] == [("c30d77670cf2",)]


@pytest.mark.parametrize("table,column", [("memories", "user_id"), ("goals", "user_id"),
                                          ("projects", "user_id"), ("chats", "project_id")])
def test_missing_foreign_key_on_existing_table_is_added(dburl, table, column):
    alembic(dburl, "upgrade", "head")
    execute(dburl, _fk_drop_sql(table, column))
    alembic(dburl, "stamp", D82)
    alembic(dburl, "upgrade", "head")
    assert diff_vs_models(dburl) == []


def test_extra_unknown_nullable_column_is_tolerated_and_data_kept(dburl):
    alembic(dburl, "upgrade", "head")
    execute(dburl, USER + HEAD_ROWS["memories"] + ";ALTER TABLE memories ADD COLUMN extra TEXT")
    alembic(dburl, "stamp", D82)
    alembic(dburl, "upgrade", "head")
    assert scalar(dburl, "select count(*) from memories") == 1


def test_extra_unknown_not_null_column_with_default_is_tolerated(dburl):
    alembic(dburl, "upgrade", "head")
    execute(dburl, "ALTER TABLE memories ADD COLUMN extra TEXT NOT NULL DEFAULT 'x'")
    alembic(dburl, "stamp", D82)
    alembic(dburl, "upgrade", "head")
    assert version(dburl) == HEAD


@pytest.mark.parametrize("table", ["memories", "goals", "projects", "chats", "conversations"])
def test_extra_unknown_not_null_column_without_default_is_rejected(dburl, table):
    alembic(dburl, "upgrade", "head")
    execute(dburl, USER)  # rows exist elsewhere; the altered table itself must be empty to add the column
    execute(dburl, f"ALTER TABLE {table} ADD COLUMN extra TEXT NOT NULL")
    alembic(dburl, "stamp", D82)
    before = snapshot(dburl)
    r = alembic(dburl, "upgrade", "head", check=False)
    assert r.returncode != 0, "unknown NOT NULL column without default was accepted"
    assert "Incompatible existing schema" in r.stderr
    assert f"{table}.extra: unknown NOT NULL column without a server default" in r.stderr
    assert snapshot(dburl) == before  # schema, comments, data and revision (d82) untouched
    assert before["version"] == [(D82,)]


# ---- schema comparison mutation tests ------------------------------------------

def _mutated_diff(dburl, sql):
    alembic(dburl, "upgrade", "head")
    assert diff_vs_models(dburl) == []  # control: clean before mutation
    execute(dburl, sql)
    return diff_vs_models(dburl)


def _has(diffs, kind, needle):
    return any(x[0] == kind and needle in repr(x) for x in diffs)


def test_mutation_column_type_detected(dburl):
    assert _has(_mutated_diff(dburl, "ALTER TABLE goals ALTER COLUMN title TYPE TEXT"), "modify_type", "title")


def test_mutation_column_length_detected(dburl):
    assert _has(_mutated_diff(dburl, "ALTER TABLE goals ALTER COLUMN title TYPE VARCHAR(50)"), "modify_type", "title")


def test_mutation_nullability_detected(dburl):
    assert _has(_mutated_diff(dburl, "ALTER TABLE memories ALTER COLUMN content DROP NOT NULL"),
                "modify_nullable", "content")


def test_mutation_fk_ondelete_detected(dburl):
    d = _mutated_diff(dburl, _fk_drop_sql("chats", "project_id")
                      + "ALTER TABLE chats ADD FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE")
    assert _has(d, "remove_fk", "project_id") or _has(d, "add_fk", "project_id")


def test_mutation_index_uniqueness_detected(dburl):
    d = _mutated_diff(dburl, "DROP INDEX ix_user_profiles_user_id; "
                             "CREATE INDEX ix_user_profiles_user_id ON user_profiles(user_id)")
    assert _has(d, "remove_index", "ix_user_profiles_user_id") or _has(d, "add_index", "ix_user_profiles_user_id")


def test_mutation_index_columns_detected(dburl):
    d = _mutated_diff(dburl, "DROP INDEX ix_goals_user_id; CREATE INDEX ix_goals_user_id ON goals(title)")
    assert _has(d, "remove_index", "ix_goals_user_id") or _has(d, "add_index", "ix_goals_user_id")


def test_mutation_unexpected_default_detected(dburl):
    assert _has(_mutated_diff(dburl, "ALTER TABLE goals ALTER COLUMN priority SET DEFAULT 5"),
                "modify_default", "priority")


def test_allow_list_is_limited_to_the_two_documented_defaults(dburl):
    alembic(dburl, "upgrade", "head")
    # the documented defaults are present in the DB yet not reported ...
    assert scalar(dburl, "select count(*) from information_schema.columns where table_name='conversations' "
                         "and column_name in ('title','category') and column_default is not null") == 2
    assert diff_vs_models(dburl) == []
    # ... but any change to them, or a new default elsewhere, is reported
    execute(dburl, "ALTER TABLE conversations ALTER COLUMN title SET DEFAULT 'Other'")
    assert _has(diff_vs_models(dburl), "modify_default", "title")


@pytest.mark.parametrize("expr", [
    "'x' || 'New Chat'",                 # contains the literal, different meaning
    "'New Chat' || ' (copy)'",
    "COALESCE(NULL, 'New Chat') || 'x'",
    "lower('New Chat')",
    "'new chat'",
    "'New Chat '",
    "'Other'",
])
def test_allow_list_rejects_expressions_that_merely_contain_the_literal(dburl, expr):
    alembic(dburl, "upgrade", "head")
    assert diff_vs_models(dburl) == []
    execute(dburl, f"ALTER TABLE conversations ALTER COLUMN title SET DEFAULT {expr}")
    assert _has(diff_vs_models(dburl), "modify_default", "title"), expr


def test_allow_list_rejects_category_default_changes_too(dburl):
    alembic(dburl, "upgrade", "head")
    execute(dburl, "ALTER TABLE conversations ALTER COLUMN category SET DEFAULT 'general' || 'x'")
    assert _has(diff_vs_models(dburl), "modify_default", "category")


# ---- ownership: objects that pre-existed must survive downgrade ----------------

def _create_all(url):
    import src.models  # noqa: F401
    from src.database.base import Base
    e = create_engine(url)
    try:
        Base.metadata.create_all(e)
    finally:
        e.dispose()


def _strip_version(snap):
    """Fingerprint minus the revision itself (version key and the alembic_version row)."""
    out = {k: v for k, v in snap.items() if k != "version"}
    out["data"] = {t: r for t, r in snap["data"].items() if t != "alembic_version"}
    return out


def test_create_all_db_stamped_d82_upgrade_is_noop_and_head_downgrade_keeps_everything(dburl):
    """Empty tables built by create_all must never be dropped by the e5 downgrade."""
    _create_all(dburl)
    alembic(dburl, "stamp", D82)
    stamped = snapshot(dburl)
    alembic(dburl, "upgrade", "head")
    upgraded = snapshot(dburl)
    assert version(dburl) == HEAD
    assert _strip_version(upgraded) == _strip_version(stamped)  # nothing created, nothing marked
    assert diff_vs_models(dburl) == []
    alembic(dburl, "downgrade", D82)
    assert snapshot(dburl) == stamped  # every pre-existing (empty) table, column, index kept
    assert {"memories", "user_profiles", "life_roles", "goals", "projects"} <= tables(dburl)
    cols = scalar(dburl, "select string_agg(column_name,',') from information_schema.columns where table_name='chats'")
    assert "project_id" in cols


def test_create_all_db_with_data_survives_upgrade_and_head_downgrade(dburl):
    _create_all(dburl)
    execute(dburl, USER + """
        INSERT INTO projects(user_id,name,status) VALUES (1,'p','active');
        INSERT INTO chats(user_id,project_id,user_message,ai_response) VALUES (1,1,'q','a');""")
    execute(dburl, HEAD_ROWS["memories"])
    alembic(dburl, "stamp", D82)
    stamped = snapshot(dburl)
    alembic(dburl, "upgrade", "head")
    assert _strip_version(snapshot(dburl)) == _strip_version(stamped)
    assert diff_vs_models(dburl) == []
    alembic(dburl, "downgrade", D82)
    assert snapshot(dburl) == stamped  # data and schema intact, revision back at d82


@pytest.mark.parametrize("name,sql", [
    ("missing_table_memories", "DROP TABLE memories"),
    ("missing_table_goals", "DROP TABLE goals"),
    ("missing_chat_project_id", "ALTER TABLE chats DROP COLUMN project_id"),
    ("missing_index", "DROP INDEX ix_goals_user_id"),
    ("missing_unique_index", "DROP INDEX ix_user_profiles_user_id"),
    ("missing_fk_memories", _fk_drop_sql("memories", "user_id")),
    ("missing_fk_chats_project", _fk_drop_sql("chats", "project_id")),
])
def test_downgrade_removes_only_what_e5_created_on_partial_preexisting_schema(dburl, name, sql):
    """create_all DB with ONE object missing: e5 adds it (owned); downgrade must remove exactly
    that object and restore the exact pre-upgrade state, leaving all other empty tables alone."""
    _create_all(dburl)
    execute(dburl, sql)
    alembic(dburl, "stamp", D82)
    stamped = snapshot(dburl)
    alembic(dburl, "upgrade", "head")
    assert version(dburl) == HEAD
    assert diff_vs_models(dburl) == []
    assert snapshot(dburl)["comments"] != stamped["comments"]  # e5 marked what it created
    alembic(dburl, "downgrade", D82)
    assert snapshot(dburl) == stamped


@pytest.mark.parametrize("with_rows", [False, True])
def test_projects_table_that_pre_existed_d82_survives_d82_downgrade(dburl, with_rows):
    """projects built outside Alembic before d82 ran: d82 records no ownership, so its
    downgrade runs to completion (drops conversations) yet must keep projects, even empty."""
    from src.models.project import Project
    alembic(dburl, "upgrade", "c30d77670cf2")
    e = create_engine(dburl)
    try:
        Project.__table__.create(e)
    finally:
        e.dispose()
    if with_rows:
        execute(dburl, USER + "INSERT INTO projects(user_id,name,status) VALUES (1,'p','active');")
    alembic(dburl, "upgrade", D82)
    assert "projects" not in _rec(dburl)[D82]["tables"]  # d82 did not create it => does not own it
    alembic(dburl, "downgrade", "c30d77670cf2")
    assert "projects" in tables(dburl) and "conversations" not in tables(dburl)
    assert scalar(dburl, "select count(*) from projects") == (1 if with_rows else 0)


def test_fresh_database_records_ownership_without_disturbing_model_comparison(dburl):
    import json
    alembic(dburl, "upgrade", "head")
    rec = json.loads(scalar(dburl, "select obj_description('alembic_version'::regclass,'pg_class')"))
    assert rec["d82a61f4b903"] == {
        "tables": ["projects", "conversations"], "columns": ["chats.conversation_id"],
        "indexes": ["ix_chats_conversation_id"],
        "constraints": ["chats.fk_chats_conversation_id_conversations"]}
    assert set(rec["e5f1a7c92b04"]["tables"]) == {"memories", "user_profiles", "life_roles", "goals"}
    assert rec["e5f1a7c92b04"]["columns"] == ["chats.project_id"]
    assert diff_vs_models(dburl) == []  # the record is not visible to the model comparison


def test_create_all_database_records_nothing(dburl):
    _create_all(dburl)
    alembic(dburl, "stamp", D82)
    alembic(dburl, "upgrade", "head")
    assert scalar(dburl, "select obj_description('alembic_version'::regclass,'pg_class')") is None


def test_missing_ownership_record_means_downgrade_drops_nothing(dburl):
    """Safe direction: if the record is lost, no table/column is removed."""
    alembic(dburl, "upgrade", "head")
    execute(dburl, "COMMENT ON TABLE alembic_version IS NULL")
    before = snapshot(dburl)
    alembic(dburl, "downgrade", D82)
    after = snapshot(dburl)
    assert _strip_version(after) == _strip_version(before)
    assert after["version"] == [(D82,)]


def test_unexpected_alembic_version_comment_is_not_overwritten(dburl):
    alembic(dburl, "upgrade", "c30d77670cf2")
    execute(dburl, "COMMENT ON TABLE alembic_version IS 'someone elses note'")
    before = snapshot(dburl)
    r = alembic(dburl, "upgrade", "head", check=False)
    assert r.returncode != 0 and "refusing to overwrite" in r.stderr
    assert snapshot(dburl) == before


def test_fresh_database_documented_downgrade_path_step_by_step(dburl):
    alembic(dburl, "upgrade", "head")
    alembic(dburl, "downgrade", D82)
    assert {"memories", "user_profiles", "life_roles", "goals"}.isdisjoint(tables(dburl))
    assert {"projects", "conversations"} <= tables(dburl)  # projects is owned by d82, not e5
    alembic(dburl, "downgrade", "c30d77670cf2")
    assert {"projects", "conversations"}.isdisjoint(tables(dburl))
    alembic(dburl, "downgrade", "base")
    assert tables(dburl) == {"alembic_version"}  # f7a2 owned (and emptied) ai_usage_daily
    alembic(dburl, "upgrade", "head")
    assert diff_vs_models(dburl) == []


def test_mixed_database_projects_owned_by_d82_dropped_only_when_empty_and_owned(dburl):
    """d82-created projects with rows => refuse (revision, schema, data unchanged)."""
    alembic(dburl, "upgrade", "head")
    alembic(dburl, "downgrade", D82)
    execute(dburl, USER + "INSERT INTO projects(user_id,name,status) VALUES (1,'p','active');")
    before = snapshot(dburl)
    r = alembic(dburl, "downgrade", "c30d77670cf2", check=False)
    assert r.returncode != 0 and "Refusing to drop non-empty table 'projects'" in r.stderr
    assert snapshot(dburl) == before


def _rows(url, sql):
    e = create_engine(url)
    try:
        with e.connect() as c:
            return [tuple(r) for r in c.execute(text(sql))]
    finally:
        e.dispose()


def _attnum(url, table, column):
    return scalar(url, f"select attnum from pg_attribute where attrelid='{table}'::regclass and attname='{column}'")



# ---- d82 ownership: every object it creates is recorded; nothing else is dropped ----

C30D = "c30d77670cf2"
EMPTY = {"tables": [], "columns": [], "indexes": [], "constraints": []}


def _rec(url):
    import json
    raw = scalar(url, "select obj_description('alembic_version'::regclass,'pg_class')")
    return json.loads(raw) if raw else {}


def _comment(url):
    return scalar(url, "select obj_description('alembic_version'::regclass,'pg_class')")


def _stamped_create_all_at(url, rev):
    _create_all(url)
    alembic(url, "stamp", rev)


D82_DATA = USER + """
    INSERT INTO projects(user_id,name,status) VALUES (1,'p','active');
    INSERT INTO conversations(user_id,project_id,title,category) VALUES (1,1,'t','c');
    INSERT INTO chats(user_id,project_id,conversation_id,user_message,ai_response) VALUES (1,1,1,'q','a');"""


@pytest.mark.parametrize("rename_fk", [True, False])
@pytest.mark.parametrize("via_head", [False, True])
def test_create_all_db_with_all_d82_objects_survives_d82_downgrade(dburl, rename_fk, via_head):
    """Every d82 object pre-exists (matching names when rename_fk): nothing may be dropped."""
    _create_all(dburl)
    if rename_fk:
        execute(dburl, "ALTER TABLE chats RENAME CONSTRAINT chats_conversation_id_fkey "
                       "TO fk_chats_conversation_id_conversations")
    execute(dburl, D82_DATA)
    alembic(dburl, "stamp", D82)
    stamped = snapshot(dburl)
    if via_head:
        alembic(dburl, "upgrade", "head")
    r = alembic(dburl, "downgrade", C30D)
    assert version(dburl) == C30D
    after = snapshot(dburl)
    assert _strip_version(after) == _strip_version(stamped)  # every object, row and comment kept
    assert _comment(dburl) is None
    assert scalar(dburl, "select count(*) from conversations") == 1
    assert scalar(dburl, "select count(*) from chats where conversation_id=1") == 1


def test_fresh_d82_creates_everything_and_downgrade_removes_exactly_that(dburl):
    alembic(dburl, "upgrade", C30D)
    before = snapshot(dburl)
    alembic(dburl, "upgrade", D82)
    assert _rec(dburl)[D82] == {
        "tables": ["projects", "conversations"], "columns": ["chats.conversation_id"],
        "indexes": ["ix_chats_conversation_id"],
        "constraints": ["chats.fk_chats_conversation_id_conversations"]}
    assert {"projects", "conversations"} <= tables(dburl)
    alembic(dburl, "downgrade", C30D)
    assert snapshot(dburl) == before  # schema, comments, data and revision exactly as before d82


PARTIAL = {
    "index_chats_conversation_id": ("DROP INDEX ix_chats_conversation_id",
                                    {"indexes": ["ix_chats_conversation_id"]}),
    "index_conversations_user_id": ("DROP INDEX ix_conversations_user_id",
                                    {"indexes": ["ix_conversations_user_id"]}),
    "fk_chats_conversation_id": (_fk_drop_sql("chats", "conversation_id"),
                                 {"constraints": ["chats.fk_chats_conversation_id_conversations"]}),
    "column_chats_conversation_id": ("ALTER TABLE chats DROP COLUMN conversation_id",
                                     {"columns": ["chats.conversation_id"],
                                      "indexes": ["ix_chats_conversation_id"],
                                      "constraints": ["chats.fk_chats_conversation_id_conversations"]}),
    "table_conversations": ("DROP TABLE conversations CASCADE",
                            {"tables": ["conversations"],
                             "constraints": ["chats.fk_chats_conversation_id_conversations"]}),
}


@pytest.mark.parametrize("name", sorted(PARTIAL))
def test_partially_preexisting_d82_schema_downgrade_removes_only_new_objects(dburl, name):
    sql, expected = PARTIAL[name]
    _stamped_create_all_at(dburl, C30D)   # full model schema present, revision says "before d82"
    execute(dburl, sql)
    execute(dburl, USER + "INSERT INTO chats(user_id,user_message,ai_response) VALUES (1,'q','a');")
    before = snapshot(dburl)
    alembic(dburl, "upgrade", D82)
    assert _rec(dburl)[D82] == {**EMPTY, **expected}, "ownership must cover exactly what d82 created"
    alembic(dburl, "downgrade", C30D)
    assert snapshot(dburl) == before  # only the newly created objects removed; all else untouched


def test_preexisting_conversations_with_rows_survive_while_owned_link_is_removed(dburl):
    """conversations (with data) pre-exists; d82 only adds the chats link, so only that goes."""
    from src.models.conversation import Conversation
    from src.models.project import Project
    from src.database.base import Base
    alembic(dburl, "upgrade", C30D)
    e = create_engine(dburl)
    try:
        Base.metadata.create_all(e, tables=[Project.__table__, Conversation.__table__])
    finally:
        e.dispose()
    execute(dburl, USER + "INSERT INTO conversations(user_id,title,category) VALUES (1,'t','c');"
                          "INSERT INTO chats(user_id,user_message,ai_response) VALUES (1,'q','a');")
    before = snapshot(dburl)
    alembic(dburl, "upgrade", D82)
    assert _rec(dburl)[D82] == {**EMPTY, "columns": ["chats.conversation_id"],
                                "indexes": ["ix_chats_conversation_id"],
                                "constraints": ["chats.fk_chats_conversation_id_conversations"]}
    alembic(dburl, "downgrade", C30D)
    assert snapshot(dburl) == before
    assert scalar(dburl, "select count(*) from conversations") == 1


def _fresh_d82(url):
    alembic(url, "upgrade", C30D)
    alembic(url, "upgrade", D82)


def test_missing_ownership_record_preserves_every_d82_object(dburl):
    _fresh_d82(dburl)
    execute(dburl, "COMMENT ON TABLE alembic_version IS NULL")
    before = snapshot(dburl)
    alembic(dburl, "downgrade", C30D)
    assert version(dburl) == C30D
    assert _strip_version(snapshot(dburl)) == _strip_version(before)
    assert {"projects", "conversations"} <= tables(dburl)


MALFORMED = [
    "not json at all",
    "[1, 2, 3]",
    '"just a string"',
    '{"d82a61f4b903": "x"}',
    '{"d82a61f4b903": []}',
    '{"d82a61f4b903": {"tables": "conversations"}}',
    '{"d82a61f4b903": {"tables": [1]}}',
    '{"d82a61f4b903": {"tables": ["users"]}}',                          # not something d82 can own
    '{"d82a61f4b903": {"tables": ["conversations"], "indexes": ["ix_users_id"]}}',
    '{"d82a61f4b903": {"tables": ["conversations"], "bogus": []}}',
    '{"d82a61f4b903": {"columns": ["chats.user_id"]}}',
    '{"d82a61f4b903": {"constraints": ["chats.users_pkey"]}}',
    '{"other": {"tables": ["conversations", "projects"]}}',             # someone else's key
]


@pytest.mark.parametrize("record", MALFORMED)
def test_malformed_or_non_establishing_d82_record_drops_nothing_and_is_left_untouched(dburl, record):
    _fresh_d82(dburl)
    execute(dburl, "COMMENT ON TABLE alembic_version IS '" + record.replace("'", "''") + "'")
    before = snapshot(dburl)
    r = alembic(dburl, "downgrade", C30D, check=False)
    assert r.returncode == 0, r.stderr[-800:]
    assert version(dburl) == C30D
    assert _strip_version(snapshot(dburl)) == _strip_version(before)  # incl. the comment, untouched
    assert _comment(dburl) == record
    assert {"projects", "conversations"} <= tables(dburl)


def test_record_owning_only_one_index_drops_only_that_index(dburl):
    _fresh_d82(dburl)
    import json
    execute(dburl, "COMMENT ON TABLE alembic_version IS '" + json.dumps(
        {D82: {"indexes": ["ix_chats_conversation_id"]}}) + "'")
    alembic(dburl, "downgrade", C30D)
    assert {"projects", "conversations"} <= tables(dburl)
    idx = scalar(dburl, "select string_agg(indexname,',') from pg_indexes where tablename='chats'")
    assert "ix_chats_conversation_id" not in idx
    cols = scalar(dburl, "select string_agg(column_name,',') from information_schema.columns where table_name='chats'")
    assert "conversation_id" in cols  # the column was not recorded as owned: kept


@pytest.mark.parametrize("record", [
    "not json", '{"e5f1a7c92b04": {"tables": ["users"]}}', '{"e5f1a7c92b04": {"tables": ["memories"], "x": []}}',
    '{"e5f1a7c92b04": "memories"}', '{"e5f1a7c92b04": {"columns": ["chats.id"]}}'])
def test_malformed_e5_record_drops_nothing_and_is_left_untouched(dburl, record):
    alembic(dburl, "upgrade", "head")
    execute(dburl, "COMMENT ON TABLE alembic_version IS '" + record.replace("'", "''") + "'")
    before = snapshot(dburl)
    r = alembic(dburl, "downgrade", D82, check=False)
    assert r.returncode == 0, r.stderr[-800:]
    assert _strip_version(snapshot(dburl)) == _strip_version(before)
    assert _comment(dburl) == record
    assert {"memories", "goals", "user_profiles", "life_roles"} <= tables(dburl)


def test_d82_preserves_other_revisions_records_in_the_shared_comment(dburl):
    import json
    alembic(dburl, "upgrade", C30D)
    foreign = {"e5f1a7c92b04": {"tables": ["goals"], "columns": [], "indexes": [], "constraints": []},
               "other": {"x": [1, 2]}}
    execute(dburl, "COMMENT ON TABLE alembic_version IS '" + json.dumps(foreign) + "'")
    alembic(dburl, "upgrade", D82)
    rec = _rec(dburl)
    assert rec["e5f1a7c92b04"] == foreign["e5f1a7c92b04"] and rec["other"] == foreign["other"]
    assert D82 in rec
    alembic(dburl, "downgrade", C30D)
    assert _rec(dburl) == foreign  # d82's key removed; everything else byte-for-byte preserved


def test_fresh_head_downgrade_chain_keeps_each_records_until_its_own_downgrade(dburl):
    alembic(dburl, "upgrade", "head")
    assert {D82, "e5f1a7c92b04"} <= set(_rec(dburl))
    alembic(dburl, "downgrade", D82)
    assert set(_rec(dburl)) == {D82}
    alembic(dburl, "downgrade", C30D)
    assert _comment(dburl) is None


# ---- d82 refusals preserve schema, data, comments and revision ----

def test_d82_refuses_owned_conversations_with_rows_and_changes_nothing(dburl):
    _fresh_d82(dburl)
    execute(dburl, USER + "INSERT INTO conversations(user_id,title,category) VALUES (1,'t','c');")
    before = snapshot(dburl)
    r = alembic(dburl, "downgrade", C30D, check=False)
    assert r.returncode != 0 and "Refusing to drop non-empty table 'conversations'" in r.stderr
    assert snapshot(dburl) == before
    assert before["version"] == [(D82,)]


def test_d82_refuses_owned_chat_conversation_id_with_data_and_changes_nothing(dburl):
    """conversations pre-exists (not owned); the owned chats.conversation_id column holds data."""
    from src.models.conversation import Conversation
    from src.models.project import Project
    from src.database.base import Base
    alembic(dburl, "upgrade", C30D)
    e = create_engine(dburl)
    try:
        Base.metadata.create_all(e, tables=[Project.__table__, Conversation.__table__])
    finally:
        e.dispose()
    execute(dburl, USER + "INSERT INTO conversations(user_id,title,category) VALUES (1,'t','c');"
                          "INSERT INTO chats(user_id,user_message,ai_response) VALUES (1,'q','a');")
    alembic(dburl, "upgrade", D82)
    execute(dburl, "UPDATE chats SET conversation_id = 1")
    before = snapshot(dburl)
    r = alembic(dburl, "downgrade", C30D, check=False)
    assert r.returncode != 0 and "Refusing to drop chats.conversation_id" in r.stderr
    assert snapshot(dburl) == before


def test_d82_refusal_through_head_rolls_back_the_e5_step_too(dburl):
    alembic(dburl, "upgrade", "head")
    execute(dburl, USER + "INSERT INTO conversations(user_id,title,category) VALUES (1,'t','c');")
    before = snapshot(dburl)
    r = alembic(dburl, "downgrade", C30D, check=False)
    assert r.returncode != 0 and "Refusing to drop non-empty table 'conversations'" in r.stderr
    assert snapshot(dburl) == before
    assert before["version"] == [(HEAD,)]



# ---- d82: validation of pre-existing objects (fail clearly, roll back completely) ----

def _c30d_with_conversation_tables(url):
    """DB at c30d whose projects + conversations tables were built outside Alembic (create_all)."""
    from src.models.conversation import Conversation
    from src.models.project import Project
    from src.database.base import Base
    alembic(url, "upgrade", C30D)
    e = create_engine(url)
    try:
        Base.metadata.create_all(e, tables=[Project.__table__, Conversation.__table__])
    finally:
        e.dispose()


def _fk_drop_any(table, column):
    return _fk_drop_sql(table, column)


D82_INCOMPATIBLE = {
    # --- existing conversations table
    "conv_missing_column": ("ALTER TABLE conversations DROP COLUMN title", "conversations.title: column is missing"),
    "conv_wrong_type": ("ALTER TABLE conversations ALTER COLUMN title TYPE TEXT", "conversations.title: type is"),
    "conv_wrong_length": ("ALTER TABLE conversations ALTER COLUMN category TYPE VARCHAR(10)",
                          "conversations.category: type is"),
    "conv_wrong_timestamp_type": ("ALTER TABLE conversations ALTER COLUMN created_at TYPE TIMESTAMP",
                                  "conversations.created_at: type is"),
    "conv_wrong_nullability": ("ALTER TABLE conversations ALTER COLUMN category DROP NOT NULL",
                               "conversations.category: nullable"),
    "conv_no_primary_key": ("ALTER TABLE conversations DROP CONSTRAINT conversations_pkey",
                            "conversations: primary key"),
    "conv_user_fk_wrong_ondelete": (_fk_drop_any("conversations", "user_id")
                                    + "ALTER TABLE conversations ADD FOREIGN KEY (user_id) REFERENCES users(id)",
                                    "conversations.user_id: foreign key"),
    "conv_user_fk_missing": (_fk_drop_any("conversations", "user_id"),
                             "conversations.user_id: required foreign key"),
    "conv_project_fk_wrong_ondelete": (_fk_drop_any("conversations", "project_id")
                                       + "ALTER TABLE conversations ADD FOREIGN KEY (project_id) "
                                         "REFERENCES projects(id) ON DELETE CASCADE",
                                       "conversations.project_id: foreign key"),
    "conv_index_wrong_columns": ("DROP INDEX ix_conversations_user_id; "
                                 "CREATE INDEX ix_conversations_user_id ON conversations(title)",
                                 "conversations: index ix_conversations_user_id"),
    "conv_index_wrong_uniqueness": ("DROP INDEX ix_conversations_user_id; "
                                    "CREATE UNIQUE INDEX ix_conversations_user_id ON conversations(user_id)",
                                    "conversations: index ix_conversations_user_id"),
    "conv_missing_default": ("ALTER TABLE conversations ALTER COLUMN created_at DROP DEFAULT",
                             "conversations.created_at: server default"),
    "conv_extra_not_null_no_default": ("ALTER TABLE conversations ADD COLUMN extra TEXT NOT NULL",
                                       "conversations.extra: unknown NOT NULL column"),
    # --- existing chats.conversation_id
    "chats_col_wrong_type": ("ALTER TABLE chats ADD COLUMN conversation_id BIGINT",
                             "chats.conversation_id: type is"),
    "chats_col_not_null": ("ALTER TABLE chats ADD COLUMN conversation_id INTEGER NOT NULL",
                           "chats.conversation_id: nullable"),
    "chats_fk_wrong_ondelete": ("ALTER TABLE chats ADD COLUMN conversation_id INTEGER "
                                "REFERENCES conversations(id) ON DELETE CASCADE",
                                "chats.conversation_id: foreign key"),
    "chats_fk_no_action": ("ALTER TABLE chats ADD COLUMN conversation_id INTEGER REFERENCES conversations(id)",
                           "chats.conversation_id: foreign key"),
    "chats_fk_wrong_referenced_column": (
        "ALTER TABLE conversations ADD CONSTRAINT uq_conv_user UNIQUE (user_id); "
        "ALTER TABLE chats ADD COLUMN conversation_id INTEGER "
        "REFERENCES conversations(user_id) ON DELETE SET NULL",
        "chats.conversation_id: foreign key"),
    "chats_fk_wrong_target_table": ("ALTER TABLE chats ADD COLUMN conversation_id INTEGER "
                                    "REFERENCES users(id) ON DELETE SET NULL",
                                    "chats.conversation_id: foreign key"),
    "chats_index_wrong_columns": ("ALTER TABLE chats ADD COLUMN conversation_id INTEGER; "
                                  "CREATE INDEX ix_chats_conversation_id ON chats(user_id)",
                                  "chats: index ix_chats_conversation_id"),
    "chats_index_wrong_uniqueness": ("ALTER TABLE chats ADD COLUMN conversation_id INTEGER; "
                                     "CREATE UNIQUE INDEX ix_chats_conversation_id ON chats(conversation_id)",
                                     "chats: index ix_chats_conversation_id"),
    "chats_extra_not_null_no_default": ("ALTER TABLE chats ADD COLUMN extra TEXT NOT NULL",
                                        "chats.extra: unknown NOT NULL column"),
}
_NEEDS_EMPTY_CHATS = {"chats_col_not_null", "chats_extra_not_null_no_default"}


@pytest.mark.parametrize("name", sorted(D82_INCOMPATIBLE))
def test_d82_incompatible_existing_object_fails_clearly_and_rolls_back_completely(dburl, name):
    sql, fragment = D82_INCOMPATIBLE[name]
    _c30d_with_conversation_tables(dburl)
    execute(dburl, USER)
    if name not in _NEEDS_EMPTY_CHATS:
        execute(dburl, "INSERT INTO chats(user_id,user_message,ai_response) VALUES (1,'q','a')")
    execute(dburl, sql)
    before = snapshot(dburl)
    r = alembic(dburl, "upgrade", D82, check=False)
    assert r.returncode != 0, "incompatible existing object was silently accepted"
    assert "Incompatible existing schema; nothing was changed" in r.stderr and fragment in r.stderr, r.stderr[-1500:]
    after = snapshot(dburl)
    assert after == before  # schema, data, comments and revision all unchanged
    assert after["version"] == [(C30D,)] and _comment(dburl) is None


def test_d82_compatible_existing_objects_are_accepted_and_only_missing_ones_created(dburl):
    _c30d_with_conversation_tables(dburl)
    execute(dburl, "ALTER TABLE chats ADD COLUMN conversation_id INTEGER "
                   "REFERENCES conversations(id) ON DELETE SET NULL; "
                   "CREATE INDEX ix_chats_conversation_id ON chats(conversation_id)")
    before = snapshot(dburl)
    alembic(dburl, "upgrade", D82)
    assert _comment(dburl) is None  # nothing was created, so nothing is recorded
    assert _strip_version(snapshot(dburl)) == _strip_version(before)


# ---- d82/e5: ownership record validated BEFORE upgrade writes -----------------------

BAD_D82_RECORDS = [
    "not json at all", "[1, 2, 3]", '"just a string"',
    '{"d82a61f4b903": "x"}', '{"d82a61f4b903": []}', '{"d82a61f4b903": null}',
    '{"d82a61f4b903": {"tables": "conversations"}}', '{"d82a61f4b903": {"tables": [1]}}',
    '{"d82a61f4b903": {"tables": ["users"]}}',
    '{"d82a61f4b903": {"tables": ["conversations"], "indexes": ["ix_users_id"]}}',
    '{"d82a61f4b903": {"tables": ["conversations"], "bogus": []}}',
    '{"d82a61f4b903": {"columns": ["chats.user_id"]}}',
    '{"d82a61f4b903": {"constraints": ["chats.users_pkey"]}}',
    '{"d82a61f4b903": {"tables": ["conversations"], "columns": "chats.conversation_id"}}',
]


@pytest.mark.parametrize("record", BAD_D82_RECORDS)
def test_d82_upgrade_refuses_malformed_record_and_changes_nothing(dburl, record):
    alembic(dburl, "upgrade", C30D)
    execute(dburl, "COMMENT ON TABLE alembic_version IS '" + record.replace("'", "''") + "'")
    before = snapshot(dburl)
    r = alembic(dburl, "upgrade", D82, check=False)
    assert r.returncode != 0 and "refusing to" in r.stderr.lower(), r.stderr[-800:]
    assert snapshot(dburl) == before  # schema, data, revision AND the original comment unchanged
    assert _comment(dburl) == record
    assert {"conversations", "projects"}.isdisjoint(tables(dburl))


def test_d82_upgrade_preserves_other_revisions_records_even_when_malformed(dburl):
    import json
    alembic(dburl, "upgrade", C30D)
    foreign = {"e5f1a7c92b04": "garbage that is not ours", "other": {"x": [1, {"y": 2}]}}
    execute(dburl, "COMMENT ON TABLE alembic_version IS '" + json.dumps(foreign) + "'")
    alembic(dburl, "upgrade", D82)
    rec = _rec(dburl)
    assert rec["e5f1a7c92b04"] == foreign["e5f1a7c92b04"] and rec["other"] == foreign["other"]
    assert rec[D82]["tables"] == ["projects", "conversations"]


def test_d82_upgrade_merges_into_a_valid_existing_record_instead_of_replacing_it(dburl):
    """The existing record names an object this run does NOT create, so a replace would lose it."""
    import json
    _c30d_with_conversation_tables(dburl)  # ix_conversations_user_id pre-exists
    execute(dburl, "COMMENT ON TABLE alembic_version IS '" + json.dumps(
        {D82: {"indexes": ["ix_conversations_user_id"]}}) + "'")
    alembic(dburl, "upgrade", D82)
    rec = _rec(dburl)[D82]
    assert rec["indexes"] == ["ix_conversations_user_id", "ix_chats_conversation_id"]  # kept + added
    assert rec["columns"] == ["chats.conversation_id"] and rec["tables"] == []


def test_d82_upgrade_that_creates_nothing_leaves_a_valid_record_untouched(dburl):
    import json
    _stamped_create_all_at(dburl, C30D)
    rec = json.dumps({D82: {"tables": ["conversations"]}, "other": 1})
    execute(dburl, "COMMENT ON TABLE alembic_version IS '" + rec + "'")
    before = snapshot(dburl)
    alembic(dburl, "upgrade", D82)
    assert _comment(dburl) == rec  # byte-identical: nothing created => nothing written
    assert _strip_version(snapshot(dburl)) == _strip_version(before)


BAD_E5_RECORDS = [
    '"memories"', "[]", '{"tables": "memories"}', '{"tables": ["users"]}',
    '{"tables": ["memories"], "bogus": []}', '{"columns": ["chats.id"]}',
]


@pytest.mark.parametrize("bad", BAD_E5_RECORDS)
def test_e5_upgrade_refuses_malformed_own_record_and_changes_nothing(dburl, bad):
    import json
    alembic(dburl, "upgrade", D82)
    d82_rec = _rec(dburl)[D82]
    comment = '{"%s": %s, "e5f1a7c92b04": %s}' % (D82, json.dumps(d82_rec), bad)
    execute(dburl, "COMMENT ON TABLE alembic_version IS '" + comment.replace("'", "''") + "'")
    before = snapshot(dburl)
    r = alembic(dburl, "upgrade", "head", check=False)
    assert r.returncode != 0 and "refusing to modify" in r.stderr.lower(), r.stderr[-800:]
    assert snapshot(dburl) == before
    assert _comment(dburl) == comment and before["version"] == [(D82,)]


def test_e5_upgrade_merges_into_a_valid_existing_record(dburl):
    """The existing e5 record names projects, which e5 does NOT create now; it must be kept."""
    import json
    alembic(dburl, "upgrade", D82)
    rec = _rec(dburl)
    rec["e5f1a7c92b04"] = {"tables": ["projects"]}
    execute(dburl, "COMMENT ON TABLE alembic_version IS '" + json.dumps(rec) + "'")
    alembic(dburl, "upgrade", "head")
    e5 = _rec(dburl)["e5f1a7c92b04"]
    assert e5["tables"][0] == "projects" and e5["tables"].count("projects") == 1
    assert set(e5["tables"]) == {"projects", "memories", "user_profiles", "life_roles", "goals"}
    assert _rec(dburl)[D82] == rec[D82]  # d82's record preserved


# ---- test-fixture safety -------------------------------------------------------

REMOTE_URLS = [
    "postgresql://u:p@db.example.com:5432/postgres",
    "postgresql://u:p@fake-neon-host.example.invalid/neondb?sslmode=require",
    "postgresql://u@10.0.0.5/postgres",
    "postgresql://u@192.168.1.10/postgres",
    "postgresql://u@127.0.0.1.evil.com/postgres",
    "postgresql://u@localhost.example.com/postgres",
    "postgresql://u@[2001:db8::1]/postgres",
    "postgresql://u@127.0.0.2/postgres",
    "postgresql:///postgres",                    # no host (unix socket)
    "postgresql://u@/postgres?host=/var/run/postgresql",
    "mysql://u@127.0.0.1/db",
    "not a url",
]


@pytest.mark.parametrize("url", REMOTE_URLS)
def test_non_loopback_admin_url_rejected_before_any_connection(url, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("create_engine called for a rejected URL")
    monkeypatch.setattr(sys.modules[__name__], "create_engine", boom)
    with pytest.raises(ValueError):
        _create_throwaway_db(url)
    with pytest.raises(ValueError):
        _drop_throwaway_db(url, "latz_mig_0123456789ab")


@pytest.mark.parametrize("url", [
    "postgresql://u@localhost/postgres", "postgresql://u:p@127.0.0.1:55433/postgres",
    "postgresql+psycopg2://u@[::1]:5432/postgres", "postgresql://u@LOCALHOST/postgres"])
def test_loopback_admin_urls_accepted(url):
    validate_admin_url(url)


@pytest.mark.parametrize("name", ["postgres", "template1", "latz", "latz_mig_", "latz_mig_XYZ",
                                  "latz_mig_0123456789abc", "latz_mig_0123456789ab; DROP DATABASE postgres",
                                  "prod_latz_mig_0123456789ab", ""])
def test_cleanup_refuses_names_that_are_not_fixture_created(name, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("create_engine called for a refused drop")
    monkeypatch.setattr(sys.modules[__name__], "create_engine", boom)
    with pytest.raises(ValueError):
        _drop_throwaway_db("postgresql://u@127.0.0.1/postgres", name)


# ---- f7a2c9d1e3b6: ai_usage_daily (ownership-aware) --------------------------------
F7 = "f7a2c9d1e3b6"
USAGE_ROW = ("INSERT INTO ai_usage_daily (scope, usage_date, requests, tokens) "
             "VALUES ('global', '2026-11-18', 3, 900)")


def _create_all_stamped_e5(url):
    _create_all(url)
    alembic(url, "stamp", E5)


def test_f7a2_creates_the_usage_table_with_its_unique_key_and_matches_the_model(dburl):
    alembic(dburl, "upgrade", "head")
    assert "ai_usage_daily" in tables(dburl)
    assert scalar(dburl, "select count(*) from pg_indexes where tablename='ai_usage_daily' "
                         "and indexname='uq_ai_usage_daily_scope_date'") == 1
    assert diff_vs_models(dburl) == []


# 1. fresh upgrade then downgrade
def test_f7a2_fresh_upgrade_records_ownership_and_empty_downgrade_removes_only_its_key(dburl):
    alembic(dburl, "upgrade", "head")
    assert _rec(dburl)[F7] == {"tables": ["ai_usage_daily"]}
    others = {k: v for k, v in _rec(dburl).items() if k != F7}
    alembic(dburl, "downgrade", E5)
    assert version(dburl) == E5
    assert "ai_usage_daily" not in tables(dburl)
    assert _rec(dburl) == others  # every other revision's record is unchanged


# 2. populated owned table refuses downgrade
def test_f7a2_downgrade_refuses_when_the_owned_table_has_rows_and_changes_nothing(dburl):
    alembic(dburl, "upgrade", "head")
    execute(dburl, USAGE_ROW)
    before = snapshot(dburl)
    r = alembic(dburl, "downgrade", E5, check=False)
    assert r.returncode != 0 and "Refusing to drop non-empty table 'ai_usage_daily'" in r.stderr
    assert snapshot(dburl) == before
    assert version(dburl) == HEAD


# 3. pre-existing compatible table is untouched and unowned
def test_f7a2_upgrade_on_a_create_all_database_leaves_the_table_untouched_and_unowned(dburl):
    _create_all_stamped_e5(dburl)
    execute(dburl, USAGE_ROW)
    before = snapshot(dburl)
    alembic(dburl, "upgrade", "head")
    assert version(dburl) == HEAD
    assert F7 not in _rec(dburl)
    assert _comment(dburl) is None
    assert _strip_version(snapshot(dburl)) == _strip_version(before)
    alembic(dburl, "downgrade", E5)  # not owned: the table and its rows survive
    assert scalar(dburl, "select tokens from ai_usage_daily") == 900


@pytest.mark.parametrize("sql", [
    "ALTER TABLE ai_usage_daily DROP COLUMN tokens",
    "ALTER TABLE ai_usage_daily ALTER COLUMN scope TYPE text",
    "ALTER TABLE ai_usage_daily ALTER COLUMN scope TYPE varchar(10)",
    "ALTER TABLE ai_usage_daily ALTER COLUMN requests DROP NOT NULL",
    "ALTER TABLE ai_usage_daily ALTER COLUMN tokens DROP DEFAULT",
    "ALTER TABLE ai_usage_daily ALTER COLUMN usage_date TYPE timestamp",
    "ALTER TABLE ai_usage_daily DROP CONSTRAINT uq_ai_usage_daily_scope_date",
])
# 4. pre-existing incompatible table is rejected
def test_f7a2_incompatible_preexisting_table_is_rejected_and_nothing_changes(dburl, sql):
    _create_all_stamped_e5(dburl)
    execute(dburl, sql)
    before = snapshot(dburl)
    r = alembic(dburl, "upgrade", "head", check=False)
    assert r.returncode != 0 and "Incompatible existing schema" in r.stderr
    assert snapshot(dburl) == before
    assert version(dburl) == E5


# 5. malformed ownership metadata preserves the table
@pytest.mark.parametrize("comment", [
    "not json at all",
    "[1, 2]",
    '{"f7a2c9d1e3b6": "oops"}',
    '{"f7a2c9d1e3b6": {"tables": ["users"]}}',
    '{"f7a2c9d1e3b6": {"tables": ["ai_usage_daily"], "columns": ["x.y"]}}',
])
def test_f7a2_malformed_ownership_metadata_preserves_the_table_on_downgrade(dburl, comment):
    alembic(dburl, "upgrade", "head")
    execute(dburl, "COMMENT ON TABLE alembic_version IS '" + comment.replace("'", "''") + "'")
    before = snapshot(dburl)
    alembic(dburl, "downgrade", E5)
    after = snapshot(dburl)
    assert version(dburl) == E5
    assert "ai_usage_daily" in tables(dburl)
    assert _strip_version(after) == _strip_version(before)  # comment and table untouched


def test_f7a2_missing_ownership_record_preserves_the_table_on_downgrade(dburl):
    alembic(dburl, "upgrade", "head")
    execute(dburl, "COMMENT ON TABLE alembic_version IS NULL")
    alembic(dburl, "downgrade", E5)
    assert "ai_usage_daily" in tables(dburl)
    assert _comment(dburl) is None


def test_f7a2_upgrade_refuses_a_malformed_shared_comment_or_own_record(dburl):
    alembic(dburl, "upgrade", E5)
    execute(dburl, "COMMENT ON TABLE alembic_version IS 'someone elses note'")
    before = snapshot(dburl)
    r = alembic(dburl, "upgrade", "head", check=False)
    assert r.returncode != 0 and "refusing to overwrite" in r.stderr
    assert snapshot(dburl) == before


# 6. the e5 (and d82) metadata stays intact
def test_f7a2_keeps_e5_and_d82_records_intact_through_upgrade_and_downgrade(dburl):
    alembic(dburl, "upgrade", E5)
    e5_state = _rec(dburl)
    assert F7 not in e5_state
    alembic(dburl, "upgrade", "head")
    assert {k: v for k, v in _rec(dburl).items() if k != F7} == e5_state
    alembic(dburl, "downgrade", E5)
    assert _rec(dburl) == e5_state
    assert set(_rec(dburl)["e5f1a7c92b04"]["tables"]) == {"memories", "user_profiles", "life_roles", "goals"}


def test_f7a2_preserves_other_revisions_records_even_when_they_are_unrecognised(dburl):
    import json
    alembic(dburl, "upgrade", E5)
    data = _rec(dburl)
    data["zz_future_rev"] = {"tables": ["whatever"], "note": "kept"}
    execute(dburl, "COMMENT ON TABLE alembic_version IS '" + json.dumps(data, sort_keys=True) + "'")
    alembic(dburl, "upgrade", "head")
    assert _rec(dburl)["zz_future_rev"] == data["zz_future_rev"]
    alembic(dburl, "downgrade", E5)
    assert _rec(dburl) == data


# 7. re-upgrade after a successful downgrade
def test_f7a2_reupgrade_after_downgrade_recreates_table_and_ownership(dburl):
    alembic(dburl, "upgrade", "head")
    alembic(dburl, "downgrade", E5)
    alembic(dburl, "upgrade", "head")
    assert version(dburl) == HEAD
    assert _rec(dburl)[F7] == {"tables": ["ai_usage_daily"]}
    assert diff_vs_models(dburl) == []
    execute(dburl, USAGE_ROW)
    assert scalar(dburl, "select tokens from ai_usage_daily") == 900


def test_f7a2_extra_nullable_column_on_a_preexisting_table_is_tolerated(dburl):
    _create_all_stamped_e5(dburl)
    execute(dburl, "ALTER TABLE ai_usage_daily ADD COLUMN note text")
    alembic(dburl, "upgrade", "head")
    assert version(dburl) == HEAD and F7 not in _rec(dburl)


# ---- f7a2c9d1e3b6: stricter validation of a pre-existing table -----------------------
@pytest.mark.parametrize("sql", [
    "ALTER TABLE ai_usage_daily ADD COLUMN extra text NOT NULL",
    "ALTER TABLE ai_usage_daily ADD COLUMN extra integer NOT NULL",
    "ALTER TABLE ai_usage_daily ALTER COLUMN requests DROP DEFAULT",
    "ALTER TABLE ai_usage_daily ALTER COLUMN updated_at DROP DEFAULT",
    "ALTER TABLE ai_usage_daily ALTER COLUMN requests SET DEFAULT 5",
    "ALTER TABLE ai_usage_daily ALTER COLUMN tokens SET DEFAULT 1",
    "ALTER TABLE ai_usage_daily ALTER COLUMN tokens SET DEFAULT -0.5",
    "ALTER TABLE ai_usage_daily ALTER COLUMN updated_at SET DEFAULT '2000-01-01'",
    "ALTER TABLE ai_usage_daily ALTER COLUMN updated_at SET DEFAULT now() + interval '1 day'",
    "ALTER TABLE ai_usage_daily ALTER COLUMN id DROP DEFAULT",
    "ALTER TABLE ai_usage_daily ALTER COLUMN updated_at SET NOT NULL",
], ids=["extra_notnull_text", "extra_notnull_int", "requests_no_default", "updated_at_no_default",
        "requests_default_5", "tokens_default_1", "tokens_default_fraction", "updated_at_constant",
        "updated_at_shifted", "id_not_generated", "updated_at_not_null"])
def test_f7a2_rejects_incompatible_extra_columns_and_wrong_or_missing_defaults(dburl, sql):
    _create_all_stamped_e5(dburl)
    execute(dburl, sql)
    before = snapshot(dburl)
    r = alembic(dburl, "upgrade", "head", check=False)
    assert r.returncode != 0 and "Incompatible existing schema" in r.stderr
    assert snapshot(dburl) == before  # nothing changed, no record written
    assert version(dburl) == E5 and _comment(dburl) is None


@pytest.mark.parametrize("sql", [
    "ALTER TABLE ai_usage_daily ADD COLUMN extra text",
    "ALTER TABLE ai_usage_daily ADD COLUMN extra text NOT NULL DEFAULT 'x'",
    "ALTER TABLE ai_usage_daily ADD COLUMN extra integer GENERATED ALWAYS AS IDENTITY",
    "ALTER TABLE ai_usage_daily ADD COLUMN extra integer GENERATED ALWAYS AS (requests + 1) STORED",
    "ALTER TABLE ai_usage_daily ALTER COLUMN requests SET DEFAULT '0'",
    "ALTER TABLE ai_usage_daily ALTER COLUMN tokens SET DEFAULT (0)",
    "ALTER TABLE ai_usage_daily ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE ai_usage_daily ALTER COLUMN updated_at SET DEFAULT transaction_timestamp()",
], ids=["extra_nullable", "extra_notnull_with_default", "extra_identity", "extra_generated",
        "requests_quoted_zero", "tokens_parenthesised_zero", "updated_at_current_timestamp",
        "updated_at_transaction_timestamp"])
def test_f7a2_accepts_harmless_variations_without_claiming_ownership(dburl, sql):
    _create_all_stamped_e5(dburl)
    execute(dburl, sql)
    alembic(dburl, "upgrade", "head")
    assert version(dburl) == HEAD
    assert F7 not in _rec(dburl) and _comment(dburl) is None  # pre-existing: never owned
    execute(dburl, "INSERT INTO ai_usage_daily (scope, usage_date) VALUES ('global', '2026-11-19')")
    assert scalar(dburl, "select requests from ai_usage_daily") == 0  # the quota insert still works


def test_f7a2_expected_defaults_match_the_model_and_a_fresh_table(dburl):
    import importlib.util
    from src.models import AiUsageDaily

    spec = importlib.util.spec_from_file_location(
        "f7a2_mig", Path(__file__).resolve().parents[1] / "alembic" / "versions" / "f7a2c9d1e3b6_add_ai_usage_daily.py")
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    table = AiUsageDaily.__table__
    for name in ("requests", "tokens"):
        assert str(table.c[name].server_default.arg) == mig.EXPECTED_DEFAULTS[name]
    assert str(table.c["updated_at"].server_default.arg) == "now()" == mig.EXPECTED_DEFAULTS["updated_at"]
    assert {c.name for c in table.c} == {"id", "scope", "usage_date", "requests", "tokens", "updated_at"}
    # The table the migration itself creates must pass its own validation.
    alembic(dburl, "upgrade", "head")
    alembic(dburl, "downgrade", E5)
    alembic(dburl, "upgrade", "head")
    assert _rec(dburl)[F7] == {"tables": ["ai_usage_daily"]}


def test_f7a2_extra_not_null_column_is_rejected_even_on_a_populated_table_via_a_default_drop(dburl):
    """A table with data and a column whose default was later removed is still incompatible."""
    _create_all_stamped_e5(dburl)
    execute(dburl, "ALTER TABLE ai_usage_daily ADD COLUMN extra text NOT NULL DEFAULT 'x'")
    execute(dburl, USAGE_ROW)
    execute(dburl, "ALTER TABLE ai_usage_daily ALTER COLUMN extra DROP DEFAULT")
    before = snapshot(dburl)
    r = alembic(dburl, "upgrade", "head", check=False)
    assert r.returncode != 0 and "extra NOT NULL column without a default" in r.stderr
    assert snapshot(dburl) == before

"""Row level security on every table (default deny for any role other than the owner)

Revision ID: d5f6a7b8c9d0
Revises: c4e5f6a7b8c9
Create Date: 2026-10-09

The API connects as the role that owns the tables, which RLS does not restrict (no FORCE),
so the application keeps working. Any other database role — a read-only reporting user, a
leaked secondary credential, a hosted REST layer — gets no rows at all unless a policy is
added for it explicitly. Per-user isolation itself is enforced in the API (every query is
scoped to the user / partner from the token; see tests/api/test_security_access_control.py).
The function aff_enable_rls() can be re-run after adding tables.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d5f6a7b8c9d0"
down_revision: Union[str, None] = "c4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENABLE = """
CREATE OR REPLACE FUNCTION aff_enable_rls() RETURNS integer AS $fn$
DECLARE
    t record;
    n integer := 0;
BEGIN
    FOR t IN
        SELECT c.relname FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
        WHERE ns.nspname = current_schema() AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t.relname);
        n := n + 1;
    END LOOP;
    RETURN n;
END;
$fn$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(_ENABLE)
    op.execute("SELECT aff_enable_rls()")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    DO $do$
    DECLARE t record;
    BEGIN
        FOR t IN
            SELECT c.relname FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
            WHERE ns.nspname = current_schema() AND c.relkind IN ('r', 'p') AND c.relrowsecurity
        LOOP
            EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', t.relname);
        END LOOP;
    END
    $do$;
    """)
    op.execute("DROP FUNCTION IF EXISTS aff_enable_rls()")

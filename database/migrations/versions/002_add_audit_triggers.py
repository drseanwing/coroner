"""Add audit triggers for automatic change logging

Revision ID: 002_add_audit_triggers
Revises: 001_initial_schema
Create Date: 2026-01-25

Creates PostgreSQL triggers for automatic audit logging on:
- sources table
- findings table
- analyses table
- posts table

The trigger function captures INSERT, UPDATE, DELETE operations and stores
them in the audit_log table with old/new values as JSONB.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_add_audit_triggers'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # Create trigger function for audit logging
    # ==========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION log_table_changes()
        RETURNS TRIGGER AS $$
        DECLARE
            audit_action TEXT;
            old_data JSONB;
            new_data JSONB;
            record_id UUID;
        BEGIN
            -- Determine action type
            IF (TG_OP = 'INSERT') THEN
                audit_action := 'created';
                old_data := NULL;
                new_data := to_jsonb(NEW);
                record_id := NEW.id;
            ELSIF (TG_OP = 'UPDATE') THEN
                audit_action := 'updated';
                old_data := to_jsonb(OLD);
                new_data := to_jsonb(NEW);
                record_id := NEW.id;
            ELSIF (TG_OP = 'DELETE') THEN
                audit_action := 'deleted';
                old_data := to_jsonb(OLD);
                new_data := NULL;
                record_id := OLD.id;
            ELSE
                RAISE EXCEPTION 'Unknown TG_OP: %', TG_OP;
            END IF;

            -- Insert audit record
            INSERT INTO audit_log (
                table_name,
                record_id,
                action,
                old_values,
                new_values,
                changed_at
            ) VALUES (
                TG_TABLE_NAME,
                record_id,
                audit_action,
                old_data,
                new_data,
                now()
            );

            -- Return appropriate row
            IF (TG_OP = 'DELETE') THEN
                RETURN OLD;
            ELSE
                RETURN NEW;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ==========================================================================
    # Create triggers on all audited tables
    # ==========================================================================

    audited_tables = ['sources', 'findings', 'analyses', 'posts']

    for table_name in audited_tables:
        # Create trigger for INSERT, UPDATE, DELETE
        op.execute(f"""
            CREATE TRIGGER audit_{table_name}_changes
            AFTER INSERT OR UPDATE OR DELETE ON {table_name}
            FOR EACH ROW
            EXECUTE FUNCTION log_table_changes();
        """)


def downgrade() -> None:
    # ==========================================================================
    # Drop all audit triggers
    # ==========================================================================

    audited_tables = ['sources', 'findings', 'analyses', 'posts']

    for table_name in audited_tables:
        op.execute(f"DROP TRIGGER IF EXISTS audit_{table_name}_changes ON {table_name}")

    # ==========================================================================
    # Drop trigger function
    # ==========================================================================
    op.execute("DROP FUNCTION IF EXISTS log_table_changes()")

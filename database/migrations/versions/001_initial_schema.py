"""Initial schema - create all tables

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-01-21

Creates the complete database schema for Patient Safety Monitor:
- sources: Data source registry
- findings: Raw collected investigation data
- analyses: LLM-generated analysis results
- posts: Generated blog content
- audit_log: Change tracking
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # Create enum types
    # ==========================================================================
    
    # FindingStatus enum
    finding_status = postgresql.ENUM(
        'new', 'classified', 'analysed', 'published', 'excluded',
        name='finding_status',
        create_type=False,
    )
    finding_status.create(op.get_bind(), checkfirst=True)

    # PostStatus enum
    post_status = postgresql.ENUM(
        'draft', 'pending_review', 'approved', 'published', 'rejected',
        name='post_status',
        create_type=False,
    )
    post_status.create(op.get_bind(), checkfirst=True)

    # LLMProvider enum
    llm_provider = postgresql.ENUM(
        'claude', 'openai',
        name='llm_provider',
        create_type=False,
    )
    llm_provider.create(op.get_bind(), checkfirst=True)
    
    # ==========================================================================
    # Create sources table
    # ==========================================================================
    op.create_table(
        'sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('code', sa.String(50), nullable=False, unique=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('country', sa.String(2), nullable=False),
        sa.Column('region', sa.String(50), nullable=True),
        sa.Column('base_url', sa.Text, nullable=False),
        sa.Column('scraper_class', sa.String(100), nullable=False),
        sa.Column('schedule_cron', sa.String(50), nullable=False,
                  server_default='0 6 * * *'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('last_scraped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('config_json', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    
    op.create_index('ix_sources_code', 'sources', ['code'])
    op.create_index('ix_sources_country', 'sources', ['country'])
    op.create_index('ix_sources_country_active', 'sources', ['country', 'is_active'])
    
    # ==========================================================================
    # Create findings table
    # ==========================================================================
    op.create_table(
        'findings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('title', sa.Text, nullable=False),
        sa.Column('deceased_name', sa.String(200), nullable=True),
        sa.Column('date_of_death', sa.Date, nullable=True),
        sa.Column('date_of_finding', sa.Date, nullable=True),
        sa.Column('coroner_name', sa.String(200), nullable=True),
        sa.Column('source_url', sa.Text, nullable=False),
        sa.Column('pdf_url', sa.Text, nullable=True),
        sa.Column('pdf_stored_path', sa.Text, nullable=True),
        sa.Column('content_text', sa.Text, nullable=True),
        sa.Column('content_html', sa.Text, nullable=True),
        sa.Column('categories', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('is_healthcare', sa.Boolean, nullable=True),
        sa.Column('healthcare_confidence', sa.Numeric(3, 2), nullable=True),
        sa.Column('status', finding_status, nullable=False, server_default='new'),
        sa.Column('metadata_json', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='CASCADE'),
    )
    
    op.create_index('ix_findings_source_id', 'findings', ['source_id'])
    op.create_index('ix_findings_source_external', 'findings',
                    ['source_id', 'external_id'], unique=True)
    op.create_index('ix_findings_status', 'findings', ['status'])
    op.create_index('ix_findings_status_healthcare', 'findings',
                    ['status', 'is_healthcare'])
    op.create_index('ix_findings_date', 'findings', ['date_of_finding'])
    
    # ==========================================================================
    # Create analyses table
    # ==========================================================================
    op.create_table(
        'analyses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('finding_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('llm_provider', llm_provider, nullable=False),
        sa.Column('llm_model', sa.String(50), nullable=False),
        sa.Column('prompt_version', sa.String(20), nullable=False),
        sa.Column('summary', sa.Text, nullable=False),
        sa.Column('human_factors', postgresql.JSONB, nullable=False),
        sa.Column('latent_hazards', postgresql.JSONB, nullable=False,
                  server_default='[]'),
        sa.Column('recommendations', postgresql.JSONB, nullable=False,
                  server_default='[]'),
        sa.Column('key_learnings', postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column('settings', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('specialties', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('tokens_input', sa.Integer, nullable=True),
        sa.Column('tokens_output', sa.Integer, nullable=True),
        sa.Column('cost_usd', sa.Numeric(10, 4), nullable=True),
        sa.Column('raw_response', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['finding_id'], ['findings.id'], ondelete='CASCADE'),
    )
    
    op.create_index('ix_analyses_finding_id', 'analyses', ['finding_id'])
    
    # ==========================================================================
    # Create posts table
    # ==========================================================================
    op.create_table(
        'posts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('analysis_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('slug', sa.String(200), nullable=False, unique=True),
        sa.Column('title', sa.Text, nullable=False),
        sa.Column('content_markdown', sa.Text, nullable=False),
        sa.Column('content_html', sa.Text, nullable=True),
        sa.Column('excerpt', sa.Text, nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('status', post_status, nullable=False, server_default='draft'),
        sa.Column('reviewer_notes', sa.Text, nullable=True),
        sa.Column('reviewed_by', sa.String(100), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['analysis_id'], ['analyses.id'], ondelete='CASCADE'),
    )
    
    op.create_index('ix_posts_analysis_id', 'posts', ['analysis_id'])
    op.create_index('ix_posts_slug', 'posts', ['slug'])
    op.create_index('ix_posts_status', 'posts', ['status'])
    op.create_index('ix_posts_status_published', 'posts', ['status', 'published_at'])
    
    # ==========================================================================
    # Create audit_log table
    # ==========================================================================
    op.create_table(
        'audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('table_name', sa.String(100), nullable=False),
        sa.Column('record_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('old_values', postgresql.JSONB, nullable=True),
        sa.Column('new_values', postgresql.JSONB, nullable=True),
        sa.Column('changed_by', sa.String(100), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    
    op.create_index('ix_audit_log_table_name', 'audit_log', ['table_name'])
    op.create_index('ix_audit_log_record_id', 'audit_log', ['record_id'])
    op.create_index('ix_audit_log_table_record', 'audit_log',
                    ['table_name', 'record_id'])
    op.create_index('ix_audit_log_changed_at', 'audit_log', ['changed_at'])
    
    # ==========================================================================
    # Create updated_at trigger function
    # ==========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    
    # Add triggers for tables with updated_at
    for table in ['sources', 'findings', 'posts']:
        op.execute(f"""
            CREATE TRIGGER update_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    # Drop triggers
    for table in ['sources', 'findings', 'posts']:
        op.execute(f"DROP TRIGGER IF EXISTS update_{table}_updated_at ON {table}")
    
    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    
    # Drop tables (in reverse order of creation due to foreign keys)
    op.drop_table('audit_log')
    op.drop_table('posts')
    op.drop_table('analyses')
    op.drop_table('findings')
    op.drop_table('sources')
    
    # Drop enum types
    op.execute("DROP TYPE IF EXISTS llm_provider")
    op.execute("DROP TYPE IF EXISTS post_status")
    op.execute("DROP TYPE IF EXISTS finding_status")

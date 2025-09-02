"""initial_schema

Revision ID: 1f173c4cce8c
Revises: 
Create Date: 2025-09-02 17:52:46.471070

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1f173c4cce8c'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure the pgcrypto extension is available for gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    
    # Create gpts table
    op.create_table('gpts',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create api_keys table
    op.create_table('api_keys',
        sa.Column('token_hash', sa.LargeBinary(), nullable=False),
        sa.Column('gpt_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_used', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['gpt_id'], ['gpts.id'], ),
        sa.PrimaryKeyConstraint('token_hash')
    )
    
    # Create collections table
    op.create_table('collections',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('gpt_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('schema', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['gpt_id'], ['gpts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('gpt_id', 'name', name='collections_gpt_id_name_key')
    )
    
    # Create objects table
    op.create_table('objects',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('gpt_id', sa.Text(), nullable=False),
        sa.Column('collection', sa.Text(), nullable=False),
        sa.Column('body', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['gpt_id'], ['gpts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['gpt_id', 'collection'], ['collections.gpt_id', 'collections.name'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create the required indexes
    op.create_index(
        'objects_gpt_coll_created_desc', 
        'objects', 
        ['gpt_id', 'collection', 'created_at', 'id'], 
        unique=False,
        postgresql_ops={'created_at': 'DESC', 'id': 'DESC'}
    )
    
    op.create_index(
        'objects_body_gin', 
        'objects', 
        ['body'], 
        unique=False,
        postgresql_using='gin'
    )


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('objects_body_gin', table_name='objects')
    op.drop_index('objects_gpt_coll_created_desc', table_name='objects')
    
    # Drop tables in reverse order due to foreign key constraints
    op.drop_table('objects')
    op.drop_table('collections')
    op.drop_table('api_keys')
    op.drop_table('gpts')
    
    # Note: We don't drop the pgcrypto extension as it might be used by other parts of the database

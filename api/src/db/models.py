"""SQLAlchemy models for the GPT Object Store schema."""

import os
from sqlalchemy import (
    Column, Text, DateTime, LargeBinary, ForeignKey, ForeignKeyConstraint,
    Index, UniqueConstraint, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
from sqlalchemy import create_engine, MetaData

# Create base class for models
Base = declarative_base()

# Custom metadata to ensure we can reference it in alembic
metadata = MetaData()


class GPT(Base):
    """GPT table model."""
    __tablename__ = 'gpts'
    
    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class APIKey(Base):
    """API Keys table model."""
    __tablename__ = 'api_keys'
    
    token_hash = Column(LargeBinary, primary_key=True)
    gpt_id = Column(Text, ForeignKey('gpts.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_used = Column(DateTime(timezone=True))


class Collection(Base):
    """Collections table model."""
    __tablename__ = 'collections'
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    gpt_id = Column(Text, ForeignKey('gpts.id'), nullable=False)
    name = Column(Text, nullable=False)
    schema = Column(JSONB)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('gpt_id', 'name', name='collections_gpt_id_name_key'),
    )


class Object(Base):
    """Objects table model."""
    __tablename__ = 'objects'
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    gpt_id = Column(Text, ForeignKey('gpts.id', ondelete='CASCADE'), nullable=False)
    collection = Column(Text, nullable=False)
    body = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        ForeignKeyConstraint(['gpt_id', 'collection'], ['collections.gpt_id', 'collections.name'], ondelete='CASCADE'),
        Index('objects_gpt_coll_created_desc', 'gpt_id', 'collection', 'created_at', 'id', postgresql_ops={'created_at': 'DESC', 'id': 'DESC'}),
        Index('objects_body_gin', 'body', postgresql_using='gin'),
    )


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv(
        "DATABASE_URL", 
        "postgresql://gptstore:change-me@localhost:5432/gptstore"
    )


def create_engine_from_env():
    """Create SQLAlchemy engine from environment configuration."""
    database_url = get_database_url()
    return create_engine(database_url)
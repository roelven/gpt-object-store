"""Tests for migration file syntax and structure."""

import pytest
import os
import sys
import importlib.util
from pathlib import Path


class TestMigrationSyntax:
    """Test that migration files are syntactically correct."""

    def test_initial_migration_imports(self):
        """Test that the initial migration file imports correctly."""
        # Find the migration file
        migrations_dir = Path(__file__).parent.parent.parent / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("*_initial_schema.py"))
        
        assert len(migration_files) == 1, "Should have exactly one initial schema migration"
        
        migration_file = migration_files[0]
        
        # Load the migration module
        spec = importlib.util.spec_from_file_location("migration", migration_file)
        migration_module = importlib.util.module_from_spec(spec)
        
        # This will raise an exception if there are syntax errors
        spec.loader.exec_module(migration_module)
        
        # Check that required functions exist
        assert hasattr(migration_module, 'upgrade')
        assert hasattr(migration_module, 'downgrade')
        assert callable(migration_module.upgrade)
        assert callable(migration_module.downgrade)
        
        # Check that required variables exist
        assert hasattr(migration_module, 'revision')
        assert hasattr(migration_module, 'down_revision')
        
        # Check revision is a string
        assert isinstance(migration_module.revision, str)
        assert len(migration_module.revision) > 0

    def test_alembic_env_syntax(self):
        """Test that alembic env.py has correct syntax."""
        env_file = Path(__file__).parent.parent.parent / "migrations" / "env.py"
        assert env_file.exists(), "env.py should exist in migrations directory"
        
        # Read the content and check for required patterns
        content = env_file.read_text()
        
        # Check that required imports are present
        assert 'from alembic import context' in content
        assert 'from sqlalchemy import' in content
        
        # Check that required functions are defined
        assert 'def run_migrations_offline()' in content
        assert 'def run_migrations_online()' in content
        
        # Check that our model imports are present
        assert 'from db.models import' in content

    def test_database_models_import(self):
        """Test that database models import correctly."""
        # Add src directory to path
        src_dir = Path(__file__).parent.parent.parent / "src"
        sys.path.insert(0, str(src_dir))
        
        try:
            from db.models import Base, GPT, APIKey, Collection, Object
            
            # Check that models have required attributes
            assert hasattr(GPT, '__tablename__')
            assert hasattr(APIKey, '__tablename__')
            assert hasattr(Collection, '__tablename__')
            assert hasattr(Object, '__tablename__')
            
            # Check table names
            assert GPT.__tablename__ == 'gpts'
            assert APIKey.__tablename__ == 'api_keys'
            assert Collection.__tablename__ == 'collections'
            assert Object.__tablename__ == 'objects'
            
            # Check that Base metadata is available
            assert hasattr(Base, 'metadata')
            assert len(Base.metadata.tables) >= 4
            
        finally:
            sys.path.pop(0)

    def test_migration_creates_all_required_tables(self):
        """Test that migration includes all required tables from CLAUDE.md."""
        migrations_dir = Path(__file__).parent.parent.parent / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("*_initial_schema.py"))
        
        migration_file = migration_files[0]
        
        # Read the migration file content
        content = migration_file.read_text()
        
        # Check that all required tables are created
        required_tables = ['gpts', 'api_keys', 'collections', 'objects']
        for table in required_tables:
            assert f"create_table('{table}'" in content, f"Migration should create {table} table"
        
        # Check that required indexes are created
        assert 'objects_gpt_coll_created_desc' in content
        assert 'objects_body_gin' in content
        
        # Check that pgcrypto extension is created
        assert 'CREATE EXTENSION IF NOT EXISTS pgcrypto' in content
        
        # Check that downgrade removes everything
        assert 'drop_table(' in content
        assert 'drop_index(' in content

    def test_requirements_include_needed_packages(self):
        """Test that requirements.txt includes all needed database packages."""
        requirements_file = Path(__file__).parent.parent.parent / "requirements.txt"
        assert requirements_file.exists(), "requirements.txt should exist"
        
        content = requirements_file.read_text()
        
        # Check for required packages
        assert 'alembic' in content
        assert 'asyncpg' in content
        assert 'sqlalchemy' in content
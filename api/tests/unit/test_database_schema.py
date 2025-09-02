"""Tests for database schema verification."""

import pytest
import asyncio
import os
from typing import List, Dict, Any
import asyncpg
from src.db.connection import get_database_url


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_connection():
    """Create a database connection for testing."""
    database_url = get_database_url()
    conn = await asyncpg.connect(database_url)
    yield conn
    await conn.close()


class TestDatabaseSchema:
    """Test the database schema matches the requirements."""

    async def test_gpts_table_exists(self, db_connection):
        """Test that the gpts table exists with correct columns."""
        result = await db_connection.fetch("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'gpts' 
            ORDER BY column_name
        """)
        
        assert len(result) == 3
        columns = {row['column_name']: (row['data_type'], row['is_nullable']) for row in result}
        
        assert 'id' in columns
        assert columns['id'][0] == 'text'
        assert columns['id'][1] == 'NO'
        
        assert 'name' in columns
        assert columns['name'][0] == 'text'
        assert columns['name'][1] == 'NO'
        
        assert 'created_at' in columns
        assert columns['created_at'][0] == 'timestamp with time zone'
        assert columns['created_at'][1] == 'NO'

    async def test_api_keys_table_exists(self, db_connection):
        """Test that the api_keys table exists with correct columns."""
        result = await db_connection.fetch("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'api_keys' 
            ORDER BY column_name
        """)
        
        assert len(result) == 4
        columns = {row['column_name']: (row['data_type'], row['is_nullable']) for row in result}
        
        assert 'token_hash' in columns
        assert columns['token_hash'][0] == 'bytea'
        assert columns['token_hash'][1] == 'NO'
        
        assert 'gpt_id' in columns
        assert columns['gpt_id'][0] == 'text'
        assert columns['gpt_id'][1] == 'NO'
        
        assert 'created_at' in columns
        assert columns['created_at'][0] == 'timestamp with time zone'
        assert columns['created_at'][1] == 'NO'
        
        assert 'last_used' in columns
        assert columns['last_used'][0] == 'timestamp with time zone'
        assert columns['last_used'][1] == 'YES'

    async def test_collections_table_exists(self, db_connection):
        """Test that the collections table exists with correct columns."""
        result = await db_connection.fetch("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'collections' 
            ORDER BY column_name
        """)
        
        assert len(result) == 5
        columns = {row['column_name']: (row['data_type'], row['is_nullable']) for row in result}
        
        assert 'id' in columns
        assert columns['id'][0] == 'uuid'
        assert columns['id'][1] == 'NO'
        
        assert 'gpt_id' in columns
        assert columns['gpt_id'][0] == 'text'
        assert columns['gpt_id'][1] == 'NO'
        
        assert 'name' in columns
        assert columns['name'][0] == 'text'
        assert columns['name'][1] == 'NO'
        
        assert 'schema' in columns
        assert columns['schema'][0] == 'jsonb'
        assert columns['schema'][1] == 'YES'
        
        assert 'created_at' in columns
        assert columns['created_at'][0] == 'timestamp with time zone'
        assert columns['created_at'][1] == 'NO'

    async def test_objects_table_exists(self, db_connection):
        """Test that the objects table exists with correct columns."""
        result = await db_connection.fetch("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'objects' 
            ORDER BY column_name
        """)
        
        assert len(result) == 6
        columns = {row['column_name']: (row['data_type'], row['is_nullable']) for row in result}
        
        assert 'id' in columns
        assert columns['id'][0] == 'uuid'
        assert columns['id'][1] == 'NO'
        
        assert 'gpt_id' in columns
        assert columns['gpt_id'][0] == 'text'
        assert columns['gpt_id'][1] == 'NO'
        
        assert 'collection' in columns
        assert columns['collection'][0] == 'text'
        assert columns['collection'][1] == 'NO'
        
        assert 'body' in columns
        assert columns['body'][0] == 'jsonb'
        assert columns['body'][1] == 'NO'
        
        assert 'created_at' in columns
        assert columns['created_at'][0] == 'timestamp with time zone'
        assert columns['created_at'][1] == 'NO'
        
        assert 'updated_at' in columns
        assert columns['updated_at'][0] == 'timestamp with time zone'
        assert columns['updated_at'][1] == 'NO'

    async def test_primary_keys_exist(self, db_connection):
        """Test that all primary keys are correctly defined."""
        # Check gpts primary key
        result = await db_connection.fetch("""
            SELECT constraint_name, column_name 
            FROM information_schema.key_column_usage 
            WHERE table_name = 'gpts' AND constraint_name LIKE '%_pkey'
        """)
        assert len(result) == 1
        assert result[0]['column_name'] == 'id'
        
        # Check api_keys primary key
        result = await db_connection.fetch("""
            SELECT constraint_name, column_name 
            FROM information_schema.key_column_usage 
            WHERE table_name = 'api_keys' AND constraint_name LIKE '%_pkey'
        """)
        assert len(result) == 1
        assert result[0]['column_name'] == 'token_hash'
        
        # Check collections primary key
        result = await db_connection.fetch("""
            SELECT constraint_name, column_name 
            FROM information_schema.key_column_usage 
            WHERE table_name = 'collections' AND constraint_name LIKE '%_pkey'
        """)
        assert len(result) == 1
        assert result[0]['column_name'] == 'id'
        
        # Check objects primary key
        result = await db_connection.fetch("""
            SELECT constraint_name, column_name 
            FROM information_schema.key_column_usage 
            WHERE table_name = 'objects' AND constraint_name LIKE '%_pkey'
        """)
        assert len(result) == 1
        assert result[0]['column_name'] == 'id'

    async def test_foreign_keys_exist(self, db_connection):
        """Test that all foreign key constraints are correctly defined."""
        # Get all foreign key constraints
        result = await db_connection.fetch("""
            SELECT 
                tc.table_name, 
                kcu.column_name, 
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name,
                tc.constraint_name
            FROM 
                information_schema.table_constraints AS tc 
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                  AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
            ORDER BY tc.table_name, kcu.column_name
        """)
        
        fk_dict = {}
        for row in result:
            table = row['table_name']
            if table not in fk_dict:
                fk_dict[table] = []
            fk_dict[table].append({
                'column': row['column_name'],
                'foreign_table': row['foreign_table_name'],
                'foreign_column': row['foreign_column_name']
            })
        
        # Check api_keys foreign key
        assert 'api_keys' in fk_dict
        api_keys_fks = fk_dict['api_keys']
        assert len(api_keys_fks) == 1
        assert api_keys_fks[0]['column'] == 'gpt_id'
        assert api_keys_fks[0]['foreign_table'] == 'gpts'
        assert api_keys_fks[0]['foreign_column'] == 'id'
        
        # Check collections foreign key
        assert 'collections' in fk_dict
        collections_fks = fk_dict['collections']
        assert len(collections_fks) == 1
        assert collections_fks[0]['column'] == 'gpt_id'
        assert collections_fks[0]['foreign_table'] == 'gpts'
        assert collections_fks[0]['foreign_column'] == 'id'
        
        # Check objects foreign keys
        assert 'objects' in fk_dict
        objects_fks = fk_dict['objects']
        assert len(objects_fks) >= 2  # Should have at least 2 foreign keys

    async def test_unique_constraints_exist(self, db_connection):
        """Test that unique constraints are correctly defined."""
        result = await db_connection.fetch("""
            SELECT 
                tc.table_name, 
                kcu.column_name,
                tc.constraint_name
            FROM 
                information_schema.table_constraints AS tc 
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'UNIQUE'
            AND tc.table_name = 'collections'
            ORDER BY tc.table_name, kcu.column_name
        """)
        
        # Should have unique constraint on (gpt_id, name) for collections
        constraint_columns = [row['column_name'] for row in result]
        assert 'gpt_id' in constraint_columns
        assert 'name' in constraint_columns

    async def test_required_indexes_exist(self, db_connection):
        """Test that the required indexes exist."""
        # Check for objects_gpt_coll_created_desc index
        result = await db_connection.fetch("""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'objects' 
            AND indexname = 'objects_gpt_coll_created_desc'
        """)
        assert len(result) == 1
        index_def = result[0]['indexdef']
        assert 'gpt_id' in index_def
        assert 'collection' in index_def
        assert 'created_at' in index_def
        assert 'DESC' in index_def
        
        # Check for objects_body_gin index
        result = await db_connection.fetch("""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'objects' 
            AND indexname = 'objects_body_gin'
        """)
        assert len(result) == 1
        index_def = result[0]['indexdef']
        assert 'body' in index_def
        assert 'gin' in index_def.lower()

    async def test_pgcrypto_extension_exists(self, db_connection):
        """Test that the pgcrypto extension is installed."""
        result = await db_connection.fetch("""
            SELECT extname FROM pg_extension WHERE extname = 'pgcrypto'
        """)
        assert len(result) == 1
        assert result[0]['extname'] == 'pgcrypto'

    async def test_gen_random_uuid_function_works(self, db_connection):
        """Test that gen_random_uuid() function is available and works."""
        result = await db_connection.fetch("SELECT gen_random_uuid() as uuid")
        assert len(result) == 1
        uuid_val = result[0]['uuid']
        assert uuid_val is not None
        assert len(str(uuid_val)) == 36  # Standard UUID string length

    async def test_default_values_work(self, db_connection):
        """Test that default values are correctly set."""
        # Test default UUID generation in collections
        await db_connection.execute("""
            INSERT INTO gpts (id, name) VALUES ('test-gpt', 'Test GPT')
        """)
        
        await db_connection.execute("""
            INSERT INTO collections (gpt_id, name) VALUES ('test-gpt', 'test-collection')
        """)
        
        result = await db_connection.fetch("""
            SELECT id, created_at FROM collections WHERE gpt_id = 'test-gpt'
        """)
        
        assert len(result) == 1
        assert result[0]['id'] is not None
        assert result[0]['created_at'] is not None
        
        # Clean up test data
        await db_connection.execute("""
            DELETE FROM collections WHERE gpt_id = 'test-gpt'
        """)
        await db_connection.execute("""
            DELETE FROM gpts WHERE id = 'test-gpt'
        """)
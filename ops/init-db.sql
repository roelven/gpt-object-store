-- GPT Object Store Database Initialization
-- This script ensures the database is properly configured for the application
-- The actual schema is managed by Alembic migrations

-- Ensure we're using the correct database
\c gptstore;

-- Ensure the pgcrypto extension is available (may already be installed)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Set timezone to UTC for consistency
SET timezone = 'UTC';

-- Configure some basic PostgreSQL settings for better JSONB performance
-- These settings help with JSONB operations and GIN indexes
ALTER DATABASE gptstore SET shared_preload_libraries = 'pg_stat_statements';
ALTER DATABASE gptstore SET log_statement = 'mod';
ALTER DATABASE gptstore SET log_min_duration_statement = 1000;

-- Ensure proper locale for consistent sorting
-- This is important for stable pagination ordering
SHOW lc_collate;
SHOW lc_ctype;

-- Log successful initialization
SELECT 'GPT Object Store database initialized successfully' AS status;
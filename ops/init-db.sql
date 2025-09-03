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
-- Note: shared_preload_libraries must be set at server level, not database level
ALTER DATABASE gptstore SET log_statement = 'mod';
ALTER DATABASE gptstore SET log_min_duration_statement = 1000;

-- Ensure proper locale for consistent sorting
-- This is important for stable pagination ordering
SELECT name, setting FROM pg_settings WHERE name IN ('lc_collate', 'lc_ctype');

-- Log successful initialization
SELECT 'GPT Object Store database initialized successfully' AS status;
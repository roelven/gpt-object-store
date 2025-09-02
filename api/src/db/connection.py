"""Database connection utilities for GPT Object Store."""

import os
from typing import Optional
import asyncpg
from asyncpg import Pool


class DatabaseManager:
    """Manages database connections and pool."""
    
    def __init__(self):
        self.pool: Optional[Pool] = None
        self._database_url = os.getenv(
            "DATABASE_URL", 
            "postgresql://gptstore:change-me@localhost:5432/gptstore"
        )
    
    async def initialize(self) -> None:
        """Initialize the database connection pool."""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                self._database_url,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
    
    async def close(self) -> None:
        """Close the database connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
    
    async def get_connection(self):
        """Get a database connection from the pool."""
        if not self.pool:
            await self.initialize()
        return self.pool.acquire()
    
    async def execute_query(self, query: str, *args):
        """Execute a query and return results."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def execute_command(self, command: str, *args):
        """Execute a command (INSERT, UPDATE, DELETE) and return status."""
        async with self.pool.acquire() as conn:
            return await conn.execute(command, *args)


# Global database manager instance
db_manager = DatabaseManager()


async def get_db_pool() -> Pool:
    """Get the database connection pool."""
    if not db_manager.pool:
        await db_manager.initialize()
    return db_manager.pool


async def get_db_connection():
    """Get a database connection context manager."""
    return await db_manager.get_connection()
"""API key management with secure hashing and validation."""

import hashlib
import secrets
from typing import Optional
from datetime import datetime

import asyncpg
from passlib.context import CryptContext

from ..db.connection import get_db_pool
from ..errors.problem_details import UnauthorizedError


# Use bcrypt for secure password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_api_key() -> str:
    """Generate a new API key.
    
    Returns:
        A cryptographically secure random API key string.
    """
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> bytes:
    """Hash an API key for secure storage.
    
    Args:
        api_key: The plain text API key
        
    Returns:
        Hashed API key as bytes
    """
    return pwd_context.hash(api_key).encode('utf-8')


def verify_api_key(api_key: str, hashed: bytes) -> bool:
    """Verify an API key against its hash.
    
    Args:
        api_key: The plain text API key to verify
        hashed: The stored hash as bytes
        
    Returns:
        True if the API key is valid, False otherwise
    """
    try:
        return pwd_context.verify(api_key, hashed.decode('utf-8'))
    except Exception:
        return False


async def create_api_key(gpt_id: str, api_key: Optional[str] = None) -> str:
    """Create a new API key for a GPT.
    
    Args:
        gpt_id: The GPT ID to associate with the API key
        api_key: Optional specific API key to use (if None, generates new one)
        
    Returns:
        The plain text API key (only returned here, not stored)
        
    Raises:
        asyncpg.ForeignKeyViolationError: If gpt_id doesn't exist
    """
    if api_key is None:
        api_key = generate_api_key()
    
    token_hash = hash_api_key(api_key)
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO api_keys (token_hash, gpt_id) VALUES ($1, $2)",
            token_hash, gpt_id
        )
    
    return api_key


async def validate_api_key(api_key: str) -> Optional[str]:
    """Validate an API key and return the associated GPT ID.
    
    Args:
        api_key: The plain text API key to validate
        
    Returns:
        The GPT ID if the API key is valid, None otherwise
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Fetch all API key hashes to check against
        # In production with many keys, consider adding an index on partial hash
        rows = await conn.fetch(
            "SELECT token_hash, gpt_id FROM api_keys"
        )
        
        for row in rows:
            if verify_api_key(api_key, row['token_hash']):
                # Update last_used timestamp
                await conn.execute(
                    "UPDATE api_keys SET last_used = $1 WHERE token_hash = $2",
                    datetime.utcnow(), row['token_hash']
                )
                return row['gpt_id']
    
    return None


async def revoke_api_key(api_key: str) -> bool:
    """Revoke an API key by deleting it from the database.
    
    Args:
        api_key: The plain text API key to revoke
        
    Returns:
        True if the API key was found and revoked, False otherwise
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Find and delete the API key
        rows = await conn.fetch(
            "SELECT token_hash FROM api_keys"
        )
        
        for row in rows:
            if verify_api_key(api_key, row['token_hash']):
                await conn.execute(
                    "DELETE FROM api_keys WHERE token_hash = $1",
                    row['token_hash']
                )
                return True
    
    return False


async def list_api_keys_for_gpt(gpt_id: str) -> list[dict]:
    """List API keys for a specific GPT (returns metadata only, not keys).
    
    Args:
        gpt_id: The GPT ID to list API keys for
        
    Returns:
        List of API key metadata dictionaries
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT created_at, last_used
            FROM api_keys 
            WHERE gpt_id = $1
            ORDER BY created_at DESC
            """,
            gpt_id
        )
        
        return [
            {
                "created_at": row['created_at'],
                "last_used": row['last_used']
            }
            for row in rows
        ]
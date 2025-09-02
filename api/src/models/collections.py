"""Pydantic models for collections."""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class CollectionBase(BaseModel):
    """Base collection model with common fields."""
    
    name: str = Field(
        ..., 
        min_length=1, 
        max_length=100,
        description="Collection name",
        examples=["notes", "tasks", "documents"]
    )
    json_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="schema",
        description="Optional JSON Schema for collection validation"
    )


class CollectionCreate(CollectionBase):
    """Model for creating a new collection."""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "notes",
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["title", "content"]
                }
            }
        }
    )


class CollectionUpdate(BaseModel):
    """Model for updating a collection."""
    
    json_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="schema",
        description="Updated JSON Schema for collection validation"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high"]
                        }
                    },
                    "required": ["title", "content"]
                }
            }
        }
    )


class Collection(CollectionBase):
    """Complete collection model with all fields."""
    
    id: UUID = Field(description="Collection UUID")
    gpt_id: str = Field(description="GPT ID that owns this collection")
    created_at: datetime = Field(description="Creation timestamp")
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "gpt_id": "gpt-4-custom",
                "name": "notes",
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["title", "content"]
                },
                "created_at": "2024-01-01T12:00:00Z"
            }
        }
    )


class CollectionResponse(Collection):
    """Response model for collection API endpoints."""
    pass


class CollectionListResponse(BaseModel):
    """Response model for listing collections."""
    
    collections: list[Collection] = Field(description="List of collections")
    next_cursor: Optional[str] = Field(default=None, description="Cursor for next page")
    has_more: bool = Field(description="Whether more collections are available")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "collections": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "gpt_id": "gpt-4-custom",
                        "name": "notes",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "content": {"type": "string"}
                            }
                        },
                        "created_at": "2024-01-01T12:00:00Z"
                    }
                ],
                "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNC0wMS0wMVQxMjowMDowMFoiLCJpZCI6IjU1MGU4NDAwLWUyOWItNDFkNC1hNzE2LTQ0NjY1NTQ0MDAwMCJ9",
                "has_more": False
            }
        }
    )


# Database row model (for internal use)
class CollectionRow(BaseModel):
    """Model representing a collection database row."""
    
    id: UUID
    gpt_id: str
    name: str
    json_schema: Optional[Dict[str, Any]] = Field(alias="schema")
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
    
    def to_collection(self) -> Collection:
        """Convert to public Collection model."""
        return Collection(
            id=self.id,
            gpt_id=self.gpt_id,
            name=self.name,
            json_schema=self.json_schema,
            created_at=self.created_at
        )
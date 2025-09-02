"""Pydantic models for objects."""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class ObjectBase(BaseModel):
    """Base object model with common fields."""
    
    body: Dict[str, Any] = Field(
        ...,
        description="Object JSON data",
        examples=[
            {"title": "My Note", "content": "Note content", "tags": ["work", "important"]},
            {"name": "Task 1", "completed": False, "priority": "high"}
        ]
    )


class ObjectCreate(ObjectBase):
    """Model for creating a new object."""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "body": {
                    "title": "My First Note",
                    "content": "This is the content of my note",
                    "tags": ["personal", "ideas"],
                    "priority": "medium"
                }
            }
        }
    )


class ObjectUpdate(BaseModel):
    """Model for updating an object (partial updates)."""
    
    body: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Updated object JSON data (partial or complete)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "body": {
                    "priority": "high",
                    "tags": ["work", "urgent"]
                }
            }
        }
    )


class Object(ObjectBase):
    """Complete object model with all fields."""
    
    id: UUID = Field(description="Object UUID")
    gpt_id: str = Field(description="GPT ID that owns this object")
    collection: str = Field(description="Collection name this object belongs to")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "gpt_id": "gpt-4-custom",
                "collection": "notes",
                "body": {
                    "title": "Meeting Notes",
                    "content": "Important meeting notes from today",
                    "tags": ["work", "meetings"],
                    "attendees": ["Alice", "Bob"]
                },
                "created_at": "2024-01-01T12:00:00Z",
                "updated_at": "2024-01-01T12:30:00Z"
            }
        }
    )


class ObjectResponse(Object):
    """Response model for object API endpoints."""
    pass


class ObjectListResponse(BaseModel):
    """Response model for listing objects."""
    
    objects: list[Object] = Field(description="List of objects")
    next_cursor: Optional[str] = Field(default=None, description="Cursor for next page")
    has_more: bool = Field(description="Whether more objects are available")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "objects": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "gpt_id": "gpt-4-custom",
                        "collection": "notes",
                        "body": {
                            "title": "Note 1",
                            "content": "First note content"
                        },
                        "created_at": "2024-01-01T12:00:00Z",
                        "updated_at": "2024-01-01T12:00:00Z"
                    },
                    {
                        "id": "660e8400-e29b-41d4-a716-446655440001",
                        "gpt_id": "gpt-4-custom",
                        "collection": "notes",
                        "body": {
                            "title": "Note 2",
                            "content": "Second note content"
                        },
                        "created_at": "2024-01-01T11:30:00Z",
                        "updated_at": "2024-01-01T11:30:00Z"
                    }
                ],
                "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNC0wMS0wMVQxMTozMDowMFoiLCJpZCI6IjY2MGU4NDAwLWUyOWItNDFkNC1hNzE2LTQ0NjY1NTQ0MDAwMSJ9",
                "has_more": True
            }
        }
    )


# Database row model (for internal use)
class ObjectRow(BaseModel):
    """Model representing an object database row."""
    
    id: UUID
    gpt_id: str
    collection: str
    body: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
    
    def to_object(self) -> Object:
        """Convert to public Object model."""
        return Object(
            id=self.id,
            gpt_id=self.gpt_id,
            collection=self.collection,
            body=self.body,
            created_at=self.created_at,
            updated_at=self.updated_at
        )


# Pagination-specific models
class ObjectsQueryParams(BaseModel):
    """Query parameters for objects endpoints."""
    
    limit: int = Field(default=50, ge=1, le=200, description="Number of objects per page")
    cursor: Optional[str] = Field(default=None, description="Cursor for pagination")
    order: str = Field(default="desc", pattern="^(asc|desc)$", description="Sort order")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "limit": 50,
                "cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNC0wMS0wMVQxMjowMDowMFoiLCJpZCI6IjU1MGU4NDAwLWUyOWItNDFkNC1hNzE2LTQ0NjY1NTQ0MDAwMCJ9",
                "order": "desc"
            }
        }
    )
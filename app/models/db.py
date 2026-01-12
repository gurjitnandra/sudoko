"""Utilities for working with MongoDB ObjectId in Pydantic models."""
from __future__ import annotations

from bson import ObjectId
from pydantic import BaseModel, Field


class PyObjectId(ObjectId):
    """Custom ObjectId type to use with Pydantic."""

    @classmethod
    def __get_validators__(cls):  # type: ignore[override]
        yield cls.validate

    @classmethod
    def validate(cls, value: str | ObjectId) -> ObjectId:
        if isinstance(value, ObjectId):
            return value
        if not ObjectId.is_valid(value):
            raise ValueError("Invalid ObjectId")
        return ObjectId(value)


class MongoModel(BaseModel):
    """Base model that configures JSON encoders for ObjectId."""

    id: PyObjectId | None = Field(default=None, alias="_id")

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True

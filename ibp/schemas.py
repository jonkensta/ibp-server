"""IBP pydantic schemas."""

import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JurisdictionEnum(str, Enum):
    """Enumeration for inmate jurisdictions."""

    TEXAS = "Texas"
    FEDERAL = "Federal"


class ActionEnum(str, Enum):
    """Enumeration for request actions."""

    FILLED = "Filled"
    TOSSED = "Tossed"


class ShippingMethodEnum(str, Enum):
    """Enumeration for unit shipping methods."""

    BOX = "Box"
    INDIVIDUAL = "Individual"


class UnitBase(BaseModel):
    """Base schema for Unit model."""

    name: str
    street1: str
    street2: Optional[str] = None
    city: str
    zipcode: str = Field(min_length=5, max_length=12)
    state: str = Field(min_length=2, max_length=3)
    url: Optional[str] = None
    jurisdiction: JurisdictionEnum
    shipping_method: Optional[ShippingMethodEnum] = None


class InmateBase(BaseModel):
    """Base schema for Inmate model."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    jurisdiction: JurisdictionEnum
    id: int
    race: Optional[str] = None
    sex: Optional[str] = None
    release: Optional[datetime.date] = None
    url: Optional[str] = None


class LookupBase(BaseModel):
    """Base schema for Lookup model."""

    datetime_created: datetime.datetime


class RequestBase(BaseModel):
    """Base schema for Request model."""

    date_processed: datetime.date
    date_postmarked: datetime.date
    action: ActionEnum


class CommentBase(BaseModel):
    """Base schema for Comment model."""

    datetime_created: datetime.datetime
    author: str
    body: str = Field(max_length=60)


class UnitCreate(UnitBase):
    """Schema for creating a new Unit."""


class InmateCreate(InmateBase):
    """Schema for creating a new Inmate."""

    unit_id: Optional[int] = None


class LookupCreate(LookupBase):
    """Schema for creating a new Lookup."""

    index: Optional[int] = None


class RequestCreate(RequestBase):
    """Schema for creating a new Request."""

    index: Optional[int] = None
    shipment_autoid: Optional[int] = None


class CommentCreate(CommentBase):
    """Schema for creating a new Comment."""

    index: Optional[int] = None


class UnitUpdate(UnitBase):
    """Schema for updating an existing Unit."""

    name: Optional[str] = None
    street1: Optional[str] = None
    city: Optional[str] = None
    zipcode: Optional[str] = None
    state: Optional[str] = None
    jurisdiction: Optional[JurisdictionEnum] = None
    shipping_method: Optional[ShippingMethodEnum] = None


class InmateUpdate(InmateBase):
    """Schema for updating an existing Inmate."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    jurisdiction: Optional[JurisdictionEnum] = None
    id: Optional[int] = None
    unit_id: Optional[int] = None
    datetime_fetched: Optional[datetime.datetime] = None
    date_last_lookup: Optional[datetime.date] = None


class RequestUpdate(RequestBase):
    """Schema for updating an existing Request."""

    date_processed: Optional[datetime.date] = None
    date_postmarked: Optional[datetime.date] = None
    action: Optional[ActionEnum] = None
    shipment_autoid: Optional[int] = None


class CommentUpdate(CommentBase):
    """Schema for updating an existing Comment."""

    datetime_created: Optional[datetime.datetime] = None
    author: Optional[str] = None
    body: Optional[str] = None


class RequestInDB(RequestBase):
    """Schema for Request records as stored in the database."""

    inmate_jurisdiction: JurisdictionEnum
    inmate_id: int
    index: int
    shipment_autoid: Optional[int] = None
    status: str

    class Config:  # pylint: disable=too-few-public-methods
        """Pydantic configuration for ORM mode."""

        from_attributes = True


class CommentInDB(CommentBase):
    """Schema for Comment records as stored in the database."""

    inmate_jurisdiction: JurisdictionEnum
    inmate_id: int
    index: int

    class Config:  # pylint: disable=too-few-public-methods
        """Pydantic configuration for ORM mode."""

        from_attributes = True


class LookupInDB(LookupBase):
    """Schema for Lookup records as stored in the database."""

    inmate_jurisdiction: JurisdictionEnum
    inmate_id: int
    index: int

    class Config:  # pylint: disable=too-few-public-methods
        """Pydantic configuration for ORM mode."""

        from_attributes = True


class UnitInDB(UnitBase):
    """Schema for Unit records as stored in the database."""

    autoid: int

    class Config:  # pylint: disable=too-few-public-methods
        """Pydantic configuration for ORM mode."""

        from_attributes = True


class InmateInDB(InmateBase):
    """Schema for Inmate records as stored in the database."""

    datetime_fetched: Optional[datetime.datetime] = None
    date_last_lookup: Optional[datetime.date] = None
    unit_id: Optional[int] = None

    requests: list[RequestInDB] = []
    comments: list[CommentInDB] = []
    lookups: list[datetime.datetime] = []

    class Config:  # pylint: disable=too-few-public-methods
        """Pydantic configuration for ORM mode."""

        from_attributes = True

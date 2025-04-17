""":py:mod:`pydantic` schemas for :py:mod:`ibp.models`.

The following schema classes and their corresponding instances are used in this
project to serialize Python objects to and from JSON representations.

:note: See :py:mod:`pydantic` for more details on marshalling.

"""

import datetime
import enum
import typing

import pydantic
from pydantic import BaseModel


class Jurisdiction(str, enum.Enum):
    """Enumeration of valid inmate jurisdictions."""

    texas = "Texas"
    federal = "Federal"


class UnitBase(BaseModel):
    """:py:mod:`pydantic` base schema for :py:class:`ibp.models.Unit`."""

    name: pydantic.constr(to_upper=True)
    """Unit name."""

    url: pydantic.HttpUrl
    """Unit URL if available."""

    street1: pydantic.constr(min_length=1)
    """Street1 of the prison unit address."""

    street2: pydantic.constr(min_length=1)
    """Street2 of the prison unit address."""

    city: pydantic.constr(min_length=1)
    """City of the prison unit address."""

    zipcode: pydantic.constr(min_length=5, max_length=12)
    """Zipcode of the prison unit address."""

    state: pydantic.constr(min_length=1)
    """State of the prison unit address."""

    jurisdiction: jurisdiction
    """Jurisdiction of the prison unit."""


class UnitCreate(UnitBase):
    """:py:mod:`pydantic` create schema for :py:class:`ibp.models.Unit`."""


class Unit(UnitBase):
    """:py:mod:`pydantic` schema for :py:class:`ibp.models.Unit`."""

    id: int
    """Read-only auto-incrementing unit index."""

    class Config:
        from_attributes = True


class LookupBase(BaseModel):
    """:py:mod:`pydantic` base schema for :py:class:`ibp.models.Lookup`."""


class LookupCreate(LookupBase):
    """:py:mod:`pydantic` create schema for :py:class:`ibp.models.Lookup`."""


class Lookup(LookupBase):
    """:py:mod:`pydantic` schema for :py:class:`ibp.models.Lookup`."""

    index: int
    """Read-only auto-incrementing unit index."""

    datetime: datetime.datetime
    """Datetime of the volunteer lookup for an inmate."""

    class Config:
        from_attributes = True


class CommentBase(BaseModel):
    """:py:mod:`pydantic` base schema for :py:class:`ibp.models.Comment`."""

    author: pydantic.constr(min_length=1)
    """Author of the comment."""

    body: pydantic.constr(min_length=1)
    """Body of the comment."""


class CommentCreate(BaseModel):
    """:py:mod:`pydantic` create schema for :py:class:`ibp.models.Comment`."""


class Comment(BaseModel):
    """:py:mod:`pydantic` schema for :py:class:`ibp.models.Comment`."""

    index: int
    """Read-only auto-incrementing comment index."""

    datetime: datetime.datetime
    """Datetime of when the comment was made."""

    class Config:
        from_attributes = True


class RequestAction(str, enum.Enum):
    """Enumeration of valid responses to a request."""

    tossed = "Tossed"
    filled = "Filled"


class RequestBase(BaseModel):
    """:py:mod:`pydantic` base schema for :py:class:`ibp.models.Request`."""

    date_postmarked: datetime.date
    """USPS postmarkdate of the accompanying letter."""

    action: RequestAction
    """Action taken on the corresponding request."""


class Request(RequestBase):
    """:py:mod:`pydantic` schema for :py:class:`ibp.models.Request`."""

    index: int
    """Read-only auto-incrementing request index."""

    class Config:
        from_attributes = True


class RequestAddress(BaseModel):
    """:py:mod:`pydantic` schema for a :py:class:`ibp.models.Request` address."""

    name: inmate_name,
    street1: unit.street1,
    street2: unit.street2,
    city: unit.city,
    state: unit.state,
    zipcode: unit.zipcode,


class InmateBase(BaseModel):
    """:py:mod:`pydantic` base schema for :py:class:`ibp.models.Inmate`."""

    jurisdiction: str
    """Prison system holding the inmate."""

    id: int
    """Inmate's numeric identifier as used in their jurisdiction."""

    first_name: str
    """Inmate first name.

    In some cases, this is given by the provider; in others cases, it is parsed
    from the full name using :py:class:`nameparser.parser.HumanName`.

    """

    last_name: str
    """Inmate last name.

    In some cases, this is given as-is by the provider; in others cases, it is
    parsed from the full name using :py:class:`nameparser.parser.HumanName`.

    """

    unit: typing.Optional[Unit]
    """Prison unit holding the inmate."""

    sex: str
    """Inmate gender as reported by provider."""

    race: str
    """Inmate race as reported by provider."""

    url: typing.Optional[pydantic.HttpUrl]
    """Inmate URL where their information is web accessible."""

    release: datetime.date | str
    """Date of when this inmate is set to be released."""


class InmateCreate(InmateBase):
    """:py:mod:`pydantic` create schema for :py:class:`ibp.models.Inmate`."""


class Inmate(InmateBase):
    """:py:mod:`pydantic` create schema for :py:class:`ibp.models.Inmate`."""

    datetime_fetched: datetime.datetime
    """Datetime when inmate data was fetched from provider."""

    lookups: list[Lookup]
    """List of lookups performed on this inmate by IBP volunteers."""

    comments: list[Comment]
    """List of comments on this inmate made by IBP volunteers."""

    requests: list[Request]
    """List of requests made by this inmate."""

    # release_warning: str
    # """Warning if an inmate is to be released soon."""

    class Config:
        from_attributes = True


class InmateSearchResults(BaseModel):
    """:py:mod:`pydantic` schema :py:class:`ibp.models.Inmate` search results."""

    inmates: list[Inmate]
    errors: list[pydantic.constr(min_length=1)]


class ShipmentBase(BaseModel):
    """:py:mod:`pydantic` base schema for :py:class:`ibp.models.Shipment`."""

    date_shipped: datetime.date
    """Date that the shipment was made."""

    tracking_url: pydantic.HttpUrl
    """Shipping service tracking URL if available."""

    tracking_code: str
    """Shipping service tracking code if available."""

    weight: int
    """Weight of the shipment in ounces."""

    postage: int
    """Postage of the shipment in US cents."""


class ShipmentCreate(ShipmentBase):
    """:py:mod:`pydantic` create schema for :py:class:`ibp.models.Shipment`."""


class Shipment(ShipmentBase):
    """:py:mod:`pydantic` schema for :py:class:`ibp.models.Shipment`."""

    id: int
    """Read-only auto-incrementing shipment index."""

    class Config:
        from_attributes = True



""":py:mod:`sqlalchemy` models used for the IBP database.

The following classes model the database abstraction used by IBP for its SQLite
database. These relate to the day-to-day IBP logistics, including:

    * recording results of searches for inmates through :py:class:`Inmate`,
    * recording volunteer lookups for inmates through :py:class:`Lookup`,
    * recording volunteer comments on inmates through :py:class:`Comment`,
    * processing book requests from inmates through :py:class:`Request`,
    * recording package shipments through :py:class:`Shipment`,
    * recording unit jurisdiction and address information through :py:class:`Unit`

In addition to the models, this module also defines a few convenience items:

    * Special column types :py:data:`Jurisdiction`, :py:class:`ReleaseDate`
    * Query class :py:class:`InmateQuery` for extra :py:class:`Inmate` query methods.
    * Inmate foreign-key mix-in :py:class:`HasInmateIndexKey`

These utility items are exported and documented but should not likely be used
anywhere else apart from here.

"""

# pylint: disable=too-few-public-methods, invalid-name

import typing

import sqlalchemy
from sqlalchemy import (
    Column, Enum, Text, Integer, String, DateTime, Date, ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.processors import str_to_date
from sqlalchemy.schema import ForeignKeyConstraint
from sqlalchemy.ext.declarative import declared_attr

from flask_sqlalchemy import BaseQuery

import pymates

import ibp

Base: typing.Any = ibp.db.Model  # typing.Any to suppress mypy errors.
"""Base class for :py:mod:`sqlalchemy` models.

This is actually just an alias for the Model base class exposed by the
:py:mod:`flask_sqlalchemy` plugin. However, we alias it as Base to support the
possibility that might change the base class for our models down the road.
This also seems to follow the naming :py:mod:`sqlalchemy` naming convention
more closely.
"""

Jurisdiction = Enum('Texas', 'Federal', name='jurisdiction_enum')
"""Alias for inmate jurisdiction :py:class:`sqlalchemy.types.Enum`.

Columns of this type store the jurisdiction level of the inmate.
Currently, this must be either 'Texas' or 'Federal', but the supported list
may be extended to include other jurisdictions in the future
(for example, other states or counties).
"""


class ReleaseDate(String):
    """Inmate release date SQLAlchemy column type.

    Sometimes "release dates" returned from the providers are not dates at all;
    instead, they are strings like "LIFE SENTENCE" or "UNKNOWN". To handle
    these cases, we model release dates as a :py:class:`sqlalchemy.types.String`
    type but override the :py:meth:`sqlalchemy.types.String.result_processor`
    method used to postprocess values extracted from the database. In
    particular, when a value is extracted from this column, the following
    happens:

    1. We process the string value as a :py:class:`sqlalchemy.types.Date`.
    2. If this fails, we process the value as a :py:class:`sqlalchemy.types.String`.

    :note: This column type subclasses :py:class:`sqlalchemy.types.String`
           without overriding :py:func:`__init__` and uses the same inputs.


    """

    # pylint: disable=unused-argument
    def result_processor(self, dialect, coltype):
        """Return result processor."""

        super_result_processor = super().result_processor(dialect, coltype)

        def identity(value):
            return value

        process_string = super_result_processor or identity

        def process(value):
            try:
                return str_to_date(value)
            except ValueError:
                return process_string(value)

        return process


class InmateQuery(BaseQuery):
    """Query class for supporting special inmate search methods.
    """

    # pylint: disable=redefined-builtin
    def providers_by_id(self, id):
        """Query inmate providers with an inmate ID.

        :param id: Inmate TDCJ or FBOP ID to search.
        :type id: int

        :returns: tuple of (:py:data:`inmates`, :py:data:`errors`) where

            - :py:data:`inmates` is a QueryResult for the inmate search.
            - :py:data:`errors` is a list of error strings.

        """

        inmates, errors = pymates.query_by_inmate_id(id)
        inmates = map(Inmate.from_response, inmates)

        with self.session.begin_nested():
            for inmate in inmates:
                self.session.merge(inmate)

        inmates = self.filter_by(id=id)
        return inmates, errors

    def providers_by_name(self, first_name, last_name):
        """Query inmate providers with an inmate ID.

        :param first_name: Inmate first name to search.
        :type first_name: str

        :param last_name: Inmate last name to search.
        :type last_name: str

        :returns: tuple of (:py:data:`inmates`, :py:data:`errors`) where

            - :py:data:`inmates` is a QueryResult for the inmate search.
            - :py:data:`errors` is a list of error strings.

        """

        inmates, errors = pymates.query_by_name(first_name, last_name)
        inmates = map(Inmate.from_response, inmates)

        with self.session.begin_nested():
            for inmate in inmates:
                self.session.merge(inmate)

        tolower = sqlalchemy.func.lower
        inmates = self.filter(tolower(Inmate.last_name) == tolower(last_name))
        inmates = inmates.filter(Inmate.first_name.ilike(first_name + "%"))

        return inmates, errors


class Inmate(Base):
    """SQLAlchemy ORM model for inmate data.
    """

    __tablename__ = 'inmates'

    query_class = InmateQuery

    first_name = Column(String)
    """Inmate first name.

    In some cases, this is given by the provider; in others cases, it is parsed
    from the full name using :py:class:`nameparser.parser.HumanName`.

    """

    last_name = Column(String)
    """Inmate last name.

    In some cases, this is given as-is by the provider; in others cases, it is
    parsed from the full name using :py:class:`nameparser.parser.HumanName`.

    """

    jurisdiction = Column(Jurisdiction, primary_key=True)
    """Prison system holding the inmate."""

    id = Column(Integer, primary_key=True)
    """Inmate's numeric identifier as used in their jurisdiction."""

    unit_id = Column(Integer, ForeignKey('units.id'), default=None)
    """Foreign key into the table corresponding to :py:class:`Unit`.

    Only used to resolve the relationship to :py:class:`Unit`.

    """

    unit = relationship('Unit', uselist=False)
    """Prison unit holding the inmate."""

    sex = Column(String)
    """Inmate gender as reported by provider."""

    url = Column(String)
    """Inmate URL where their information is web accessible."""

    race = Column(String)
    """Inmate race as reported by provider."""

    release = Column(ReleaseDate)
    """Date of when this inmate is set to be released."""

    datetime_fetched = Column(DateTime)
    """Datetime when inmate data was fetched from provider."""

    lookups = relationship('Lookup', order_by='desc(Lookup.datetime)')
    """List of lookups performed on this inmate by IBP volunteers."""

    comments = relationship('Comment', order_by="desc(Comment.datetime)")
    """List of comments on this inmate made by IBP volunteers."""

    requests = relationship('Request', order_by="desc(Request.date_postmarked)")
    """List of requests made by this inmate."""

    @classmethod
    def from_response(cls, response):
        """Construct Inmate object from `pymates` response object.
        """
        kwargs = dict(response)
        kwargs['id'] = int(kwargs['id'].replace('-', ''))
        kwargs['unit'] = Unit.query.filter_by(name=kwargs['unit']).first()
        return Inmate(**kwargs)


class HasInmateIndexKey:
    """Mix-In for injecting an Inmate + index key.
    """
    # pylint: disable=no-self-argument, no-self-use

    @declared_attr
    def __table_args__(cls):
        """Declare ForeignKeyConstraint attribute into inmates table."""
        return (
            ForeignKeyConstraint(
                ['inmate_jurisdiction', 'inmate_id'],
                ['inmates.jurisdiction', 'inmates.id'],
            ),
        )

    @declared_attr
    def inmate_jurisdiction(cls):
        """Jurisdiction of inmate this item pertains to."""
        return Column(Jurisdiction, primary_key=True)

    @declared_attr
    def inmate_id(cls):
        """ID of inmate this item pertains to."""
        return Column(Integer, primary_key=True)

    @declared_attr
    def index(cls):
        """Counter to disambiguate items pointing to the same inmate."""
        return Column(Integer, primary_key=True)


class Lookup(Base, HasInmateIndexKey):
    """Model for inmate system lookups."""

    __tablename__ = 'lookups'

    datetime = Column(DateTime, nullable=False)
    """Datetime of when the inmate lookup was performed."""


class Comment(Base, HasInmateIndexKey):
    """Model comments on a particular inmates."""

    __tablename__ = 'comments'

    datetime = Column(DateTime, nullable=False)
    """Datetime of when the comment was made."""

    author = Column(String, nullable=False)
    """The author of the comment."""

    body = Column(Text, nullable=False)
    """The body of the comment."""


class Request(Base, HasInmateIndexKey):
    """Model for inmate package request."""

    __tablename__ = 'requests'

    date_processed = Column(Date, nullable=False)
    """Date that the request was processed by a volunteer."""

    date_postmarked = Column(Date, nullable=False)
    """Date that the request was postmarked by the mail service."""

    Action = Enum('Filled', 'Tossed', name='action_enum')
    """Alias for request action :py:class:`sqlalchemy.types.Enum`.

    Available actions right now are 'Filled' and 'Tossed':

    - 'Filled' means that a package was ordered to be made in response to this request.
    - 'Tossed' means that the letter was thrown away and no package was made.

    """

    action = Column(Action, nullable=False)
    """Action taken by the IBP volunteer in response to the request."""

    inmate = relationship('Inmate', uselist=False)
    """Inmate that made the request."""

    shipment_id = Column(Integer, ForeignKey('shipments.id'))
    """Foreign key into the table corresponding to :py:class:`Shipment`.

    Only used to resolve the relationship to :py:class:`Shipment`.

    """

    shipment = relationship('Shipment', uselist=False)
    """Shipment containing package made in response to this request."""


class Shipment(Base):
    """SQLAlchemy ORM model for shipments made in response to requests."""

    __tablename__ = 'shipments'

    id = Column(Integer, primary_key=True)
    """Auto-incrementing identifier to serve as primary key."""

    date_shipped = Column(Date, nullable=False)
    """Date that the shipment was made."""

    tracking_url = Column(String)
    """Shipping service tracking URL if available."""

    tracking_code = Column(String)
    """Shipping service tracking code if available."""

    weight = Column(Integer, nullable=False)
    """Weight of the shipment in ounces."""

    postage = Column(Integer, nullable=False)
    """Postage of the shipment in US cents."""

    requests = relationship('Request')
    """Lists of requests this shipment responds to."""

    unit_id = Column(Integer, ForeignKey('units.id'), default=None)
    unit = relationship('Unit', uselist=False)


class Unit(Base):
    """Model for prison units."""

    __tablename__ = 'units'

    id = Column(Integer, primary_key=True)
    """Auto-incrementing identifier to serve as primary key."""

    name = Column(String, nullable=False)
    """Name of the prison unit."""

    street1 = Column(String, nullable=False)
    """Street1 of the prison unit address."""

    street2 = Column(String)
    """Street2 of the prison unit address."""

    city = Column(String, nullable=False)
    """City of the prison unit address."""

    zipcode = Column(String(12), nullable=False)
    """Zipcode of the prison unit address."""

    state = Column(String(3), nullable=False)
    """State of the prison unit address."""

    url = Column(String)
    """URL of the prison unit if available."""

    jurisdiction = Column(Jurisdiction)
    """Jurisdiction of the prison unit."""

    ShippingMethod = Enum('Box', 'Individual', name='shipping_enum')
    """Alias for shipping method :py:class:`sqlalchemy.types.Enum`.

    Available shipping methods right now are 'Box' and 'Individual':

    - 'Box' means that this unit allows multiple inmate packages to be combined in bulk.
    - 'Individual' means that a shipment must be made for each inmate package.

    """

    shipping_method = Column(ShippingMethod)
    """Shipping method to use for this prison unit."""

    inmates = relationship('Inmate')
    """List of inmates residing in this prison unit."""

    shipments = relationship('Shipment')
    """List of shipments made to this prison unit."""

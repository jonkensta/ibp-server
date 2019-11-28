"""SQLAlchemy models used for the IBP database.

The following classes model the database abstraction used by IBP for its SQLite
database. These all relate to the day-to-day logistics of handling searches and
lookups for Texas inmates and the handling, processing, and shipments
corresponding to requests from them.

In addition, this module also defines a few convenience items.
These include classes and aliases for special column types, an inmate
foreign-key mix-in, and a special InmateQuery class for providing extra methods
to the Inmate class' query object added by the Flask-SQLAlchemy extension.
These are exported and documented but should not likely be used anywhere else
apart from here.

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
"""Base class for SQLAlchemy models.

This is actually just an alias for the Model base class exposed by the
Flask-SQLAlchemy plugin. However, we alias it as Base to support the
possibility that might change the base class for our models down the road.
This also seems to follow the naming SQLAlchemy naming convention more
closely.
"""

Jurisdiction = Enum('Texas', 'Federal', name='jurisdiction_enum')
"""Alias for Inmate jurisdiction SQLAlchemy column type.

Columns of this type store the jurisdiction level of the inmate.
Currently, this must be either 'Texas' or 'Federal', but the supported list
may be extended to include other jurisdictions in the future (for example,
other states or counties).
"""


class ReleaseDate(String):
    """Inmate release date SQLAlchemy column type.

    Sometimes release dates returned from provider queries are not dates at
    all; instead, they are strings like "LIFE SENTENCE" or "UNKNOWN". To handle
    these cases, we model release dates as :py:class:`sqlalchemy.String`
    columns but override the process by which they are extracted from the
    database.  Specifically, we subclass :py:class:`sqlalchemy.String` but
    override its :py:func:`result_processor` method to do the following:

    1. We attempt to parse the string value as a date.
    2. If this fails, we parse the String value as a String (cannot fail).
    3. The value is returned as part of the query results.

    :note: This column type supports the same input parameters as the
           :class:`sqlalchemy.String` column type.

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

    def providers_by_id(self, id):
        """Query inmate providers with an inmate ID.

        :param id: Inmate TDCJ or FBOP ID to search.
        :type id: int

        :returns: tuple of (inmates, errors) where

            - `inmates` is a QueryResult for the inmate search.
            - `errors` is a list of error strings.
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

        :returns: tuple of (inmates, errors) where

            - `inmates` is a QueryResult for the inmate search.
            - `errors` is a list of error strings.
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
    """Inmate first name as returned by HumanName module."""

    last_name = Column(String)
    """Inmate last name as returned by HumanName module."""

    jurisdiction = Column(Jurisdiction, primary_key=True)
    """Prison system that this inmate resides in."""

    id = Column(Integer, primary_key=True)
    """Numeric identifier as used by the FBOP or TDCJ."""

    unit_id = Column(Integer, ForeignKey('units.id'), default=None)
    """Foreign key into the table corresponding to `Unit`.

    Only used to provide a way for the `Unit` relationship to be resolved.

    """

    unit = relationship('Unit', uselist=False)
    """Prison unit that this inmate is reported to reside."""

    sex = Column(String)
    """Inmate gender as reported by provider."""

    url = Column(String)
    """Inmate URL where their information is web accessible."""

    race = Column(String)
    """Inmate race as reported by provider."""

    release = Column(ReleaseDate)
    """Date of when this inmate is set to be released."""

    datetime_fetched = Column(DateTime)
    """Datetime of when this inmate entry was last fetched by a provider."""

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
    """
    Mix-In for injecting an Inmate + index key.
    """
    # pylint: disable=no-self-argument, no-self-use

    @declared_attr
    def __table_args__(cls):
        """Declare ForeignKeyConstraint attribute for inmates table."""
        return (
            ForeignKeyConstraint(
                ['inmate_jurisdiction', 'inmate_id'],
                ['inmates.jurisdiction', 'inmates.id'],
            ),
        )

    @declared_attr
    def inmate_jurisdiction(cls):
        """Declare Inmate jurisdiction column attribute."""
        return Column(Jurisdiction, primary_key=True)

    @declared_attr
    def inmate_id(cls):
        """Declare Inmate ID column attribute."""
        return Column(Integer, primary_key=True)

    @declared_attr
    def index(cls):
        """Declare index column attribute."""
        return Column(Integer, primary_key=True)


class Lookup(Base, HasInmateIndexKey):
    """Model for inmate system lookups."""

    __tablename__ = 'lookups'

    datetime = Column(DateTime, nullable=False)


class Comment(Base, HasInmateIndexKey):
    """Model comments on a particular inmates."""

    __tablename__ = 'comments'

    datetime = Column(DateTime, nullable=False)
    author = Column(String, nullable=False)
    body = Column(Text, nullable=False)


class Request(Base, HasInmateIndexKey):
    """Model for inmate package request."""

    __tablename__ = 'requests'

    date_processed = Column(Date, nullable=False)
    date_postmarked = Column(Date, nullable=False)

    Action = Enum('Filled', 'Tossed', name='action_enum')
    action = Column(Action, nullable=False)

    inmate = relationship('Inmate', uselist=False)

    shipment_id = Column(Integer, ForeignKey('shipments.id'))
    shipment = relationship('Shipment', uselist=False)


class Shipment(Base):
    """Model for request shipments."""

    __tablename__ = 'shipments'

    id = Column(Integer, primary_key=True)

    date_shipped = Column(Date, nullable=False)

    tracking_url = Column(String)
    tracking_code = Column(String)

    weight = Column(Integer, nullable=False)
    postage = Column(Integer, nullable=False)  # postage in cents

    requests = relationship('Request')

    unit_id = Column(Integer, ForeignKey('units.id'), default=None)
    unit = relationship('Unit', uselist=False)


class Unit(Base):
    """Model for prison units."""

    __tablename__ = 'units'

    id = Column(Integer, primary_key=True)

    name = Column(String, nullable=False)
    street1 = Column(String, nullable=False)
    street2 = Column(String)

    city = Column(String, nullable=False)
    zipcode = Column(String(12), nullable=False)
    state = Column(String(3), nullable=False)

    url = Column(String)
    jurisdiction = Column(Jurisdiction)

    ShippingMethod = Enum('Box', 'Individual', name='shipping_enum')
    shipping_method = Column(ShippingMethod)

    inmates = relationship('Inmate')
    shipments = relationship('Shipment')

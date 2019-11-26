"""
IBP database models.
"""

# pylint: disable=too-few-public-methods, invalid-name

import typing
from datetime import datetime

import sqlalchemy
from sqlalchemy import (
    Column, Enum, Text, Integer, String, DateTime, Date, ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.schema import ForeignKeyConstraint
from sqlalchemy.ext.declarative import declared_attr

from flask_sqlalchemy import BaseQuery

import pymates

import ibp

Base: typing.Any = ibp.db.Model  # Add typing.Any to suppress mypy errors.
Jurisdiction = Enum('Texas', 'Federal', name='jurisdiction_enum')


class ReleaseDate(String):
    """Inmate release date database column type."""

    def __init__(self, date_format='%Y-%m-%d'):
        super(ReleaseDate, self).__init__()
        self.date_format = date_format

    # pylint: disable=unused-argument
    def result_processor(self, *args, **kwargs):
        """Return result processor."""
        def process(value):
            if value is None:
                return None
            strptime = datetime.strptime
            try:
                value = strptime(value, self.date_format).date()
            except ValueError:
                pass
            return value
        return process


class InmateQuery(BaseQuery):
    """Class for special inmate query methods"""

    def providers_by_id(self, id_):
        """Query inmate providers with an inmate ID."""

        inmates, errors = pymates.query_by_inmate_id(id_)
        inmates = map(Inmate.from_response, inmates)

        with self.session.begin_nested():
            for inmate in inmates:
                self.session.merge(inmate)

        inmates = self.filter_by(id=id_)
        return inmates, errors

    def providers_by_name(self, first_name, last_name):
        """Query inmate providers with an inmate name."""

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
    """Model for Texas Federal and state inmates."""

    __tablename__ = 'inmates'
    query_class = InmateQuery

    first_name = Column(String)
    last_name = Column(String)

    jurisdiction = Column(Jurisdiction, primary_key=True)
    id = Column(Integer, primary_key=True)

    unit_id = Column(Integer, ForeignKey('units.id'), default=None)
    unit = relationship('Unit', uselist=False)

    sex = Column(String)
    url = Column(String)
    race = Column(String)
    release = Column(ReleaseDate)

    datetime_fetched = Column(DateTime)

    lookups = relationship('Lookup', order_by='desc(Lookup.datetime)')
    comments = relationship('Comment', order_by="desc(Comment.datetime)")
    requests = relationship('Request', order_by="desc(Request.date_postmarked)")

    @classmethod
    def from_response(cls, response):
        """Construct Inmate object from pymates response"""
        kwargs = dict(response)
        kwargs['id'] = int(kwargs['id'].replace('-', ''))
        kwargs['unit'] = Unit.query.filter_by(name=kwargs['unit']).first()
        return Inmate(**kwargs)


class HasInmateIndexKey:
    """Mix-In for injecting an Inmate + index key."""
    # pylint: disable=no-self-argument, no-self-use

    @declared_attr
    def __table_args__(cls):
        """Declare ForeignKeyConstraint Table attribute."""
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

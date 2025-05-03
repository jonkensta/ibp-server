"""IBP sqlalchemy models."""

import datetime

import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.types
from sqlalchemy import Enum  # type: ignore
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import relationship
from sqlalchemy.schema import ForeignKeyConstraint, UniqueConstraint

from .base import config, db


class ReleaseDate(sqlalchemy.types.TypeDecorator):
    """Inmate release date SQLAlchemy column type."""

    impl = sqlalchemy.types.String
    python_type = str

    cache_ok = True

    def process_bind_param(self, value, _):
        try:
            return value.isoformat()
        except AttributeError:
            return str(value)

    def process_literal_param(self, value, _):
        try:
            return value.isoformat()
        except AttributeError:
            return str(value)

    def process_result_value(self, value, _):
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return value


class Inmate(db.Model):  # pylint: disable=too-many-instance-attributes
    """Inmate sqlalchemy model."""

    __tablename__ = "inmates"

    autoid = Column(Integer, primary_key=True)

    first_name = Column(String)
    last_name = Column(String)

    jurisdiction = Column(
        Enum("Texas", "Federal", name="jurisdiction_enum"), nullable=False
    )
    id = Column(Integer, nullable=False)

    unit_id = Column(Integer, ForeignKey("units.autoid"))
    unit = relationship("Unit", uselist=False, back_populates="inmates")

    race = Column(String)
    sex = Column(String)
    release = Column(ReleaseDate)
    url = Column(String)

    datetime_fetched = Column(DateTime)
    date_last_lookup = Column(Date)

    requests = relationship(
        "Request",
        back_populates="inmate",
        order_by="desc(Request.date_postmarked)",
    )

    comments = relationship("Comment", order_by="desc(Comment.datetime)")

    _lookups_association = relationship("Lookup", order_by="desc(Lookup.datetime)")
    lookups = association_proxy("_lookups_association", "datetime")

    @declared_attr
    def __table_args__(cls):  # pylint: disable=no-self-argument
        return (UniqueConstraint("jurisdiction", "id"),)

    def entry_is_fresh(self):
        """Flag if an entry is fresh."""
        if self.datetime_fetched is None:
            return False

        age = datetime.datetime.now() - self.datetime_fetched
        ttl_hours = config.getint("warnings", "inmates_cache_ttl")
        ttl = datetime.timedelta(hours=ttl_hours)
        return age < ttl


class Lookup(db.Model):  # pylint: disable=too-few-public-methods
    """Sqlalchemy for IBP lookups."""

    __tablename__ = "lookups"

    autoid = Column(Integer, primary_key=True)
    datetime = Column(DateTime, nullable=False)

    inmate_id = Column(Integer, ForeignKey("inmates.autoid"))

    def __init__(self, dt):
        super().__init__()
        self.datetime = dt


class Request(db.Model):  # pylint: disable=too-few-public-methods
    """Sqlalchemy model for IBP requests."""

    __tablename__ = "requests"

    autoid = Column(Integer, primary_key=True)

    date_processed = Column(Date, nullable=False)
    date_postmarked = Column(Date, nullable=False)

    action = Column(Enum("Filled", "Tossed", name="action_enum"), nullable=False)

    inmate_autoid = Column(Integer, ForeignKey("inmates.autoid"))
    inmate = relationship("Inmate", uselist=False, back_populates="requests")

    shipment_autoid = Column(Integer, ForeignKey("shipments.autoid"))
    shipment = relationship("Shipment", uselist=False, back_populates="requests")

    @property
    def status(self):
        """Return status of a request."""
        shipped = self.shipment and self.shipment.date_shipped and "Shipped"
        return shipped or self.action


class Shipment(db.Model):  # pylint: disable=too-few-public-methods
    """Sqlalchemy model for IBP shipments."""

    __tablename__ = "shipments"

    autoid = Column(Integer, primary_key=True)

    date_shipped = Column(Date, nullable=False)

    tracking_url = Column(String)
    tracking_code = Column(String)

    weight = Column(Integer, nullable=False)
    postage = Column(Integer, nullable=False)  # postage in cents

    requests = relationship("Request", back_populates="shipment")

    unit_id = Column(Integer, ForeignKey("units.autoid"))
    unit = relationship("Unit", uselist=False, back_populates="shipments")


class Comment(db.Model):  # pylint: disable=too-few-public-methods
    """Sqlalchemy model for IBP comments."""

    __tablename__ = "comments"

    autoid = Column(Integer, primary_key=True)

    datetime = Column(DateTime, nullable=False)
    author = Column(String, nullable=False)
    body = Column(Text, nullable=False)

    inmate_id = Column(Integer, ForeignKey("inmates.autoid"))

    @classmethod
    def from_form(cls, form):
        """Update comment instance from a form."""
        return cls(
            datetime=datetime.datetime.today(),
            author=form.author.data,
            body=form.comment.data,
        )


class Unit(db.Model):  # pylint: disable=too-many-instance-attributes
    """Sqlalchemy model for IBP units."""

    __tablename__ = "units"

    autoid = Column(Integer, primary_key=True)

    name = Column(String, nullable=False)
    street1 = Column(String, nullable=False)
    street2 = Column(String)

    city = Column(String, nullable=False)
    zipcode = Column(String(12), nullable=False)
    state = Column(String(3), nullable=False)

    url = Column(String)
    jurisdiction = Column(
        Enum("Texas", "Federal", name="jurisdiction_enum"), nullable=False
    )

    shipping_method = Column(Enum("Box", "Individual", name="shipping_enum"))

    inmates = relationship("Inmate", back_populates="unit")
    shipments = relationship("Shipment", back_populates="unit")

    @declared_attr
    def __table_args__(cls):  # pylint: disable=no-self-argument
        return (UniqueConstraint("jurisdiction", "name"),)

    def update_from_form(self, form):
        """Update a unit instance from a form."""
        self.name = form.name.data
        self.url = form.url.data or None
        self.city = form.city.data
        self.state = form.state.data
        self.street1 = form.street1.data
        self.street2 = form.street2.data
        self.zipcode = form.zipcode.data
        self.shipping_method = form.shipping_method.data or None

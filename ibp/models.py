"""IBP sqlalchemy models."""

from datetime import datetime, timedelta

import pymates as providers
import sqlalchemy
import sqlalchemy.orm
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declared_attr

import ibp

Model = ibp.db.Model
Column = ibp.db.Column

Text = ibp.db.Text
Integer = ibp.db.Integer
String = ibp.db.String
DateTime = ibp.db.DateTime
Date = ibp.db.Date
Enum = ibp.db.Enum

ForeignKey = ibp.db.ForeignKey
UniqueConstraint = ibp.db.UniqueConstraint

relationship = ibp.db.relationship


class ReleaseDate(String):  # pylint: disable=too-few-public-methods
    """Custom column type for release date."""

    def result_processor(self, *_):
        """Create a release date result processor."""

        def process(value):
            if value is None:
                return None
            try:
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                pass
            return value

        return process


class Inmate(Model):  # pylint: disable=too-many-instance-attributes
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

    @classmethod
    def from_response(cls, session, response):
        """Create an Inmate instance from a provider response."""
        kwargs = dict(response)
        kwargs["id"] = int(kwargs["id"].replace("-", ""))
        kwargs["unit"] = session.query(Unit).filter_by(name=kwargs["unit"]).first()
        return cls(**kwargs)

    @classmethod
    def query_by_autoid(cls, session, autoid):
        """Query the inmate providers by autoid."""
        inmate = cls.query.filter_by(autoid=autoid).first()

        if inmate is None or inmate.entry_is_fresh():
            return cls.query.filter_by(autoid=autoid)

        timeout = ibp.config.getfloat("providers", "timeout")
        inmates, _ = providers.query_by_inmate_id(
            inmate.id, jurisdictions=[inmate.jurisdiction], timeout=timeout
        )

        with session.begin_nested():
            for inmate in inmates:
                inmate = cls.from_response(session, inmate)
                session.merge(inmate)

        return cls.query.filter_by(autoid=autoid)

    @classmethod
    def query_by_inmate_id(cls, session, id_):
        """Query the inmate providers by inmate id."""
        inmates, errors = providers.query_by_inmate_id(id_)

        with session.begin_nested():
            for inmate in inmates:
                inmate = cls.from_response(session, inmate)
                session.merge(inmate)

        inmates = cls.query.filter_by(id=id_)
        return inmates, errors

    @classmethod
    def query_by_name(cls, session, first_name, last_name):
        """Query the inmate providers by name."""
        timeout = ibp.config.getfloat("providers", "timeout")
        inmates, errors = providers.query_by_name(
            first_name, last_name, timeout=timeout
        )

        with session.begin_nested():
            for inmate in inmates:
                inmate = cls.from_response(session, inmate)
                session.merge(inmate)

        sql_lower = sqlalchemy.func.lower
        inmates = cls.query.filter(
            sql_lower(Inmate.last_name) == sql_lower(last_name)
        ).filter(Inmate.first_name.ilike(first_name + "%"))
        return inmates, errors

    @declared_attr
    def __table_args__(cls):  # pylint: disable=no-self-argument
        return (UniqueConstraint("jurisdiction", "id"),)

    def entry_is_fresh(self):
        """Flag if an entry is fresh."""
        if self.datetime_fetched is None:
            return False

        age = datetime.now() - self.datetime_fetched
        ttl_hours = ibp.config.getint("warnings", "inmates_cache_ttl")
        ttl = timedelta(hours=ttl_hours)
        return age < ttl


class Lookup(Model):  # pylint: disable=too-few-public-methods
    """Sqlalchemy for IBP lookups."""

    __tablename__ = "lookups"

    autoid = Column(Integer, primary_key=True)
    datetime = Column(DateTime, nullable=False)
    inmate_id = Column(Integer, ForeignKey("inmates.autoid"))


class Request(Model):  # pylint: disable=too-few-public-methods
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


class Shipment(Model):  # pylint: disable=too-few-public-methods
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


class Comment(Model):  # pylint: disable=too-few-public-methods
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
            datetime=datetime.today(),
            author=form.author.data,
            body=form.comment.data,
        )


class Unit(Model):
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

    inmates = ibp.db.relationship("Inmate", back_populates="unit")
    shipments = ibp.db.relationship("Shipment", back_populates="unit")

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

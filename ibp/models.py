"""IBP sqlalchemy models."""

import datetime
from typing import Optional

import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.types
from sqlalchemy import Enum  # type: ignore
from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import mapped_column  # pylint: disable=no-name-in-module
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.schema import ForeignKeyConstraint, PrimaryKeyConstraint

from .base import config
from .db import Base


class ReleaseDate(sqlalchemy.types.TypeDecorator):
    """Inmate release date SQLAlchemy column type."""

    impl = sqlalchemy.types.String
    python_type = str

    cache_ok = True

    def process_bind_param(self, value, _):
        """Process value before binding to database."""
        if value is None:
            return None
        try:
            return value.isoformat()
        except AttributeError:
            return str(value)

    def process_literal_param(self, value, _):
        """Process value for literal inclusion in SQL string."""
        if value is None:
            return "NULL"
        try:
            return f"'{value.isoformat()}'"
        except AttributeError:
            return f"'{str(value)}'"

    def process_result_value(self, value, _):
        """Process value after fetching from database."""
        if value is None:
            return None
        try:
            return datetime.date.fromisoformat(value)
        except (ValueError, TypeError):
            return value


Jurisdiction = Enum("Texas", "Federal", name="jurisdiction_enum")


class HasInmateIndex:  # pylint: disable=too-few-public-methods
    """Mixin for models associated with an Inmate."""

    inmate_jurisdiction: Mapped[str] = mapped_column(Jurisdiction, nullable=False)
    inmate_id: Mapped[int] = mapped_column(Integer, nullable=False)
    index: Mapped[int] = mapped_column(Integer, nullable=False)

    @declared_attr
    def __table_args__(cls):  # pylint: disable=no-self-argument
        return (
            PrimaryKeyConstraint(
                "inmate_jurisdiction",
                "inmate_id",
                "index",
            ),
            ForeignKeyConstraint(
                ["inmate_jurisdiction", "inmate_id"],
                ["inmates.jurisdiction", "inmates.id"],
            ),
        )

    @declared_attr
    def inmate(cls) -> Mapped["Inmate"]:  # pylint: disable=no-self-argument
        """Declare the relationship to the Inmate model."""
        return relationship("Inmate", uselist=False)


class Inmate(Base):  # pylint: disable=too-many-instance-attributes
    """Inmate sqlalchemy model."""

    __tablename__ = "inmates"

    __table_args__ = (
        ForeignKeyConstraint(
            ["jurisdiction", "unit_name"],
            ["units.jurisdiction", "units.name"],
        ),
    )

    # Composite Primary Key: jurisdiction and id
    jurisdiction: Mapped[str] = mapped_column(
        Jurisdiction, primary_key=True, nullable=False
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)

    first_name: Mapped[Optional[str]] = mapped_column(String)
    last_name: Mapped[Optional[str]] = mapped_column(String)

    unit_name: Mapped[Optional[str]] = mapped_column(String)
    unit: Mapped[Optional["Unit"]] = relationship(
        "Unit", foreign_keys=[jurisdiction, unit_name], uselist=False
    )

    race: Mapped[Optional[str]] = mapped_column(String)
    sex: Mapped[Optional[str]] = mapped_column(String)
    release: Mapped[Optional[datetime.date]] = mapped_column(ReleaseDate)
    url: Mapped[Optional[str]] = mapped_column(String)

    datetime_fetched: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    requests: Mapped[list["Request"]] = relationship(
        "Request",
        back_populates="inmate",
        order_by="desc(Request.date_postmarked)",
        cascade="all, delete-orphan",
        collection_class=list,
    )

    comments: Mapped[list["Comment"]] = relationship(
        "Comment",
        back_populates="inmate",
        order_by="desc(Comment.datetime_created)",
        cascade="all, delete-orphan",
        collection_class=list,
    )

    lookups: Mapped[list["Lookup"]] = relationship(
        "Lookup",
        back_populates="inmate",
        order_by="desc(Lookup.datetime_created)",
        cascade="all, delete-orphan",
        collection_class=list,
    )

    def entry_is_fresh(self) -> bool:
        """Flag if an entry is fresh."""
        if self.datetime_fetched is None:
            return False

        age = datetime.datetime.now() - self.datetime_fetched
        ttl_hours = config.getint("warnings", "inmates_cache_ttl")
        ttl = datetime.timedelta(hours=ttl_hours)
        return age < ttl


class Lookup(HasInmateIndex, Base):  # pylint: disable=too-few-public-methods
    """Sqlalchemy for IBP lookups."""

    __tablename__ = "lookups"

    datetime_created: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False
    )


class Request(HasInmateIndex, Base):  # pylint: disable=too-few-public-methods
    """Sqlalchemy model for IBP requests."""

    __tablename__ = "requests"

    date_processed: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    date_postmarked: Mapped[datetime.date] = mapped_column(Date, nullable=False)

    action: Mapped[str] = mapped_column(
        Enum("Filled", "Tossed", name="action_enum"), nullable=False
    )

    @property
    def status(self) -> str:
        """Return status of a request."""
        shipped = self.shipment and self.shipment.date_shipped and "Shipped"
        return shipped or self.action


class Comment(HasInmateIndex, Base):  # pylint: disable=too-few-public-methods
    """Sqlalchemy model for IBP comments."""

    __tablename__ = "comments"

    datetime_created: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False
    )
    author: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class Unit(
    Base
):  # pylint: disable=too-many-instance-attributes, too-few-public-methods
    """Sqlalchemy model for IBP units."""

    __tablename__ = "units"

    jurisdiction: Mapped[str] = mapped_column(Jurisdiction, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)

    street1: Mapped[str] = mapped_column(String, nullable=False)
    street2: Mapped[Optional[str]] = mapped_column(String)

    city: Mapped[str] = mapped_column(String, nullable=False)
    zipcode: Mapped[str] = mapped_column(String(12), nullable=False)
    state: Mapped[str] = mapped_column(String(3), nullable=False)

    url: Mapped[Optional[str]] = mapped_column(String)

    shipping_method: Mapped[Optional[str]] = mapped_column(
        Enum("Box", "Individual", name="shipping_enum")
    )

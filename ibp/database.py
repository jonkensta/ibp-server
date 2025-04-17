"""Database engine bindings and session-maker."""

import typing
import urllib

import sqlalchemy
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from .base import get_toplevel_path


def build_uri():
    """Build a URI to the sqlite3 database."""
    toplevel = get_toplevel_path()
    filepath = toplevel.joinpath("data.db").absolute()
    uri_parts = ("sqlite", "/", str(filepath), "", "", "")  # netloc needs to be "/".
    return urllib.parse.urlunparse(uri_parts)


def create_engine():
    """Create an engine for our sqlite database."""
    return sqlalchemy.create_engine(
        build_uri(), connect_args={"check_same_thread": False}
    )


Session = sessionmaker(
    bind=create_engine(), autocommit=False, autoflush=False, future=True
)

Base: typing.Any = declarative_base()
"""Base class for :py:mod:`sqlalchemy` models."""

Base.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def update_from_kwargs(self, **kwargs):
    """Update a model object from given keyword arguments."""
    for key, value in kwargs.items():
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            msg = f"'{self.__class__}' has no attribute named '{key}'"
            raise AttributeError(msg)


# Add update_from_kwargs method to Base to provide to all model objects.
Base.update_from_kwargs = update_from_kwargs

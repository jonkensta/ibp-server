"""IBP database methods."""

from sqlalchemy import MetaData

# pylint: disable=no-name-in-module
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .base import config, get_toplevel_path


def get_uri():
    """Get URI of sqlite3 database."""
    toplevel = get_toplevel_path()
    filepath = toplevel.joinpath(config.get("database", "database")).absolute()
    return f"sqlite+aiosqlite:///{filepath}"


def build_engine():
    """Build an async engine."""
    return create_async_engine(get_uri())


def build_async_sessionmaker():
    """Build an async sessionmaker."""
    return async_sessionmaker(
        autocommit=False, autoflush=False, bind=build_engine(), class_=AsyncSession
    )


async_session = build_async_sessionmaker()


class Base(DeclarativeBase):  # pylint: disable=too-few-public-methods
    """Base for SQLAlchemy models."""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )

    def update_from_kwargs(self, **kwargs):
        """Update a model object from given keyword arguments."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                msg = f"'{self.__class__}' has no attribute named '{key}'"
                raise AttributeError(msg)

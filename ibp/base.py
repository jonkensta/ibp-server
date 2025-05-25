"""Initialize the IBP FastAPI application."""

import configparser
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


def get_toplevel_path() -> Path:
    """Get project toplevel path."""
    return Path(__file__).parent.parent


def read_server_config():
    """Read configuration file at module load time."""
    toplevel = get_toplevel_path()
    filepath = os.path.join(toplevel, "conf", "server.conf")
    server_config = configparser.ConfigParser()
    server_config.read([filepath])
    return server_config


config = read_server_config()


def get_database_uri():
    """Get URI of sqlite3 database."""
    toplevel = get_toplevel_path()
    filepath = toplevel.joinpath(config.get("database", "database")).absolute()
    # For SQLite, using 'sqlite+aiosqlite' for async support with SQLAlchemy
    return f"sqlite+aiosqlite:///{filepath}"


# Initialize FastAPI app
app = FastAPI(
    title="Inside Books Project API",
    description="API for managing inmate data, requests, shipments, and comments.",
    version="0.1.0",
)

# Configure SQLAlchemy for async operations
DATABASE_URL = get_database_uri()
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)


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


class RotatingStream:
    """Model a rotating stream for logging purposes."""

    def __init__(self, max_lines=1000):
        """Initialize the rotating stream."""
        self._max_lines = int(max_lines)
        self._buffer = ""
        self.lines = []

    def write(self, s):
        """Write a string to the rotating stream."""
        self._buffer += s

        # append the newly written lines
        *lines, self._buffer = self._buffer.split(logging.StreamHandler.terminator)
        self.lines.extend(lines)

        # coerce to max_lines length
        self.lines = self.lines[(-self._max_lines) :]

    def flush(self, *args, **kwargs):
        """Flush the rotating stream."""


log_stream = RotatingStream()


def build_log_handlers():
    """Build the log handlers for the IBP application."""
    format_ = config.get("logging", "format", raw=True)
    formatter = logging.Formatter(format_)

    handler_ = RotatingFileHandler(
        config.get("logging", "logfile"),
        maxBytes=config.getint("logging", "rotation_size"),
    )
    handler_.setFormatter(formatter)
    yield handler_

    handler_ = logging.StreamHandler(stream=log_stream)
    handler_.setFormatter(formatter)
    yield handler_

    handler_ = logging.StreamHandler()
    handler_.setFormatter(formatter)
    yield handler_


root_logger = logging.getLogger()
root_logger.handlers = []
log_level = logging.getLevelName(config.get("logging", "level"))
log_handlers = list(build_log_handlers())

for logger in (
    logging.getLogger("PROVIDERS"),
    logging.getLogger("sqlalchemy.engine"),
):
    logger.setLevel(log_level)
    for handler in log_handlers:
        logger.addHandler(handler)

for logger_name in (
    "asyncio",
    "uvicorn",
):
    logging.getLogger(logger_name).setLevel(logging.ERROR)

root_logger.info("Starting IBP Application")

# Import models to ensure they are registered with SQLAlchemy metadata
from ibp import models  # pylint: disable=wrong-import-position, unused-import

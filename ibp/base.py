"""Initialize the IBP flask application."""

import configparser
import functools
import logging
import os
import urllib
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

import flask
from flask import Flask
from flask_bootstrap import Bootstrap  # type: ignore
from flask_sqlalchemy import SQLAlchemy  # type: ignore
from flask_wtf.csrf import CSRFProtect  # type: ignore
from sqlalchemy import MetaData
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


config = read_server_config()  # pylint: disable=invalid-name

# setup flask application
app = Flask(__name__)


def get_database_uri():
    toplevel = get_toplevel_path()
    filepath = toplevel.joinpath(config.get("database", "database")).absolute()
    uri_parts = ("sqlite", "/", str(filepath), "", "", "")  # netloc needs to be "/".
    return urllib.parse.urlunparse(uri_parts)


database_uri = get_database_uri()

app.config.update(
    SECRET_KEY=config.get("server", "secret_key"),
    SQLALCHEMY_DATABASE_URI=get_database_uri(),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
)

Bootstrap(app)
csrf = CSRFProtect(app)


class Base(DeclarativeBase):
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


db = SQLAlchemy(model_class=Base)
db.init_app(app)

app.config["REMEMBER_COOKIE_DURATION"] = timedelta(minutes=10)

# configure logging


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
        self.lines = self.lines[(-self._max_lines) :]  # noqa: E203

    def flush(self, *args, **kwargs):
        """Flush the rotating stream."""


log_stream = RotatingStream()


def build_log_handlers():
    """Build the log handlers for the IBP application."""
    format_ = config.get("logging", "format", raw=True)
    formatter = logging.Formatter(format_)

    handler = RotatingFileHandler(
        config.get("logging", "logfile"),
        maxBytes=config.getint("logging", "rotation_size"),
    )
    handler.setFormatter(formatter)
    yield handler

    handler = logging.StreamHandler(stream=log_stream)
    handler.setFormatter(formatter)
    yield handler

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    yield handler


app.logger.handlers = []
log_level = logging.getLevelName(config.get("logging", "level"))
log_handlers = list(build_log_handlers())

for logger in (
    app.logger,
    logging.getLogger("PROVIDERS"),
):
    logger.setLevel(log_level)
    for handler in log_handlers:
        logger.addHandler(handler)

for logger in (
    logging.getLogger("urllib3"),
    logging.getLogger("werkzeug"),
    logging.getLogger("requests"),
):
    logger.setLevel(logging.ERROR)

app.logger.info("Starting IBP Application")


from ibp import models, views  # pylint: disable=wrong-import-position, unused-import


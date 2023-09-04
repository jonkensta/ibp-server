"""Database engine bindings and session-maker."""

import urllib

import sqlalchemy  # type: ignore
from sqlalchemy.orm import sessionmaker  # type: ignore

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

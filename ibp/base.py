"""IBP server base module."""

import os
import configparser


def get_toplevel_directory():
    """Get project toplevel directory."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def read_server_config():
    """Read configuration file at module load time."""
    toplevel = get_toplevel_directory()
    filepath = os.path.join(toplevel, "conf", "server.conf")
    server_config = configparser.ConfigParser()
    server_config.read([filepath])
    return server_config


config = read_server_config()  # pylint: disable=invalid-name

# pylint: disable=unused-import, wrong-import-position
from . import models
from . import routes
from .routes import app

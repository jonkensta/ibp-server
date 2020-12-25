"""IBP server base module."""

import os
import configparser
from pathlib import Path


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

# pylint: disable=unused-import, wrong-import-position
from . import models  # noqa: F401, E402
from . import routes  # noqa: F401, E402
from .routes import app  # noqa: F401, E402

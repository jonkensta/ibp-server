"""IBP server base module."""

import configparser
from os.path import abspath, dirname
from os.path import join as join_path

# pylint: disable=unused-import

config = configparser.ConfigParser()
_config_fpath = abspath(join_path(dirname(__file__), "..", "conf", "server.conf"))
config.read([_config_fpath, ".ibpserver.conf"])

from . import models
from . import routes
from .routes import app

# pylint: disable=invalid-name

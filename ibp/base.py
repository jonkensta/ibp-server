"""IBP server base module."""

import configparser
from os.path import abspath, dirname
from os.path import join as join_path

import bottle

# pylint: disable=unused-import

from . import models
from . import routes
from .routes import app

# pylint: disable=invalid-name

config_fpath = abspath(join_path(dirname(__file__), "..", "conf", "server.conf"))
config = configparser.ConfigParser()
config.read([config_fpath, ".ibpserver.conf"])

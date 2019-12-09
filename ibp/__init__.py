"""Initialize the Flask app."""

# pylint: disable=invalid-name

import os
from configparser import SafeConfigParser

import flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

CONFIG = SafeConfigParser()

config_fname = "development.conf"
local_dir = os.path.dirname(os.path.realpath(__file__))
root_dir = os.path.join(local_dir, os.path.pardir)
config_fpath = os.path.abspath(os.path.join(root_dir, "conf", config_fname))
CONFIG.read(config_fpath)

# setup flask application
app = flask.Flask(__name__)

database_fpath = os.path.join(root_dir, CONFIG.get("database", "database"))
database_fpath = os.path.abspath(database_fpath)
database_uri = "sqlite:///" + database_fpath

app.config.update(
    SECRET_KEY=CONFIG.get("server", "secret_key"),
    SQLALCHEMY_DATABASE_URI=database_uri,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
)

db = SQLAlchemy(app)
db.Model.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

CORS(app)

import ibp.views  # pylint: disable=wrong-import-position
import ibp.models  # pylint: disable=wrong-import-position

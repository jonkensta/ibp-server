"""
Initialize the Flask app.
"""

import os
from datetime import timedelta
from configparser import SafeConfigParser

import flask
from flask_sqlalchemy import SQLAlchemy

CONFIG = SafeConfigParser()

config_fname = 'development.conf'
local_dir = os.path.dirname(os.path.realpath(__file__))
root_dir = os.path.join(local_dir, os.path.pardir)
config_fpath = os.path.abspath(os.path.join(root_dir, 'conf', config_fname))
CONFIG.read(config_fpath)

# setup flask application
APP = flask.Flask(__name__)

database_fpath = os.path.join(root_dir, CONFIG.get('database', 'database'))
database_fpath = os.path.abspath(database_fpath)
database_uri = 'sqlite:///' + database_fpath

APP.config.update(
    SECRET_KEY=CONFIG.get('server', 'secret_key'),
    SQLALCHEMY_DATABASE_URI=database_uri,
    SQLALCHEMY_TRACK_MODIFICATIONS=False
)

DB = SQLAlchemy(APP)
DB.Model.metadata.naming_convention = {
    'ix': 'ix_%(column_0_label)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s'
}

APP.config['REMEMBER_COOKIE_DURATION'] = timedelta(minutes=10)


# set up models
import ibp.models  # noqa

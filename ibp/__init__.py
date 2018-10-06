import os
import functools
from datetime import timedelta

import logging

from ConfigParser import SafeConfigParser

import flask
from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy

config = SafeConfigParser()

flask_env = os.getenv('FLASK_ENV', 'production')
if flask_env == 'production':
    config_fname = 'production.conf'
else:
    config_fname = 'development.conf'

local_dir = os.path.dirname(os.path.realpath(__file__))
root_dir = os.path.join(local_dir, os.path.pardir)
config_fpath = os.path.abspath(os.path.join(root_dir, 'conf', config_fname))
config.read(config_fpath)

# configure logging
log = logging.getLogger()
log.setLevel(config.get('logging', 'level'))

logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('requests').setLevel(logging.ERROR)
logging.getLogger('oauth2client.client').setLevel(logging.ERROR)
logging.getLogger('googleapiclient.discovery').setLevel(logging.ERROR)
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

log_formatter = logging.Formatter(config.get('logging', 'format', raw=True))

log_handler = logging.StreamHandler()
log_handler.setFormatter(log_formatter)
log.addHandler(log_handler)


class RotatingStream(object):

    def __init__(self, max_lines=1000):
        self._max_lines = int(max_lines)
        self._buffer = ''
        self.lines = []

    def write(self, s):
        self._buffer += s

        # append the newly written lines
        lines = self._buffer.split('\n')
        self.lines.extend(lines[:-1])
        self._buffer = lines[-1]

        # coerce to max_lines length
        self.lines = self.lines[-self._max_lines:]


log_stream = RotatingStream()
log_handler = logging.StreamHandler(log_stream)
log_handler.setFormatter(log_formatter)
log.addHandler(log_handler)

# setup flask application
app = Flask(__name__)
app.logger.setLevel(config.get('logging', 'level'))

database_fpath = os.path.join(root_dir, config.get('database', 'database'))
database_fpath = os.path.abspath(database_fpath)
database_uri = 'sqlite:///' + database_fpath

app.config.update(
    SECRET_KEY=config.get('server', 'secret_key'),
    SQLALCHEMY_DATABASE_URI=database_uri,
    SQLALCHEMY_TRACK_MODIFICATIONS=False
)

Bootstrap(app)
csrf = CSRFProtect(app)

db = SQLAlchemy(app)
db.Model.metadata.naming_convention = {
    'ix': 'ix_%(column_0_label)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s'
}

app.config['REMEMBER_COOKIE_DURATION'] = timedelta(minutes=10)
login_manager = LoginManager(app)


# convenience methods
def get_config_section(section):
    config = {}
    options = ibp.config.options(section)
    for option in options:
        try:
            config[option] = ibp.config.get(section, option)
        except Exception:
            config[option] = None
    return config


def appkey_required(view_function):
    correct_appkey = config.get('server', 'apikey')

    @functools.wraps(view_function)
    def inner(*args, **kwargs):
        received_appkey = flask.request.form.get('key')
        if received_appkey == correct_appkey:
            return view_function(*args, **kwargs)
        else:
            return "an application key is required", 401

    return inner


# set up flask views
import ibp.views  # noqa

# set up models
import ibp.models  # noqa

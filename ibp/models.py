import httplib2
import functools

from datetime import datetime, timedelta

import apiclient
import oauth2client.client as oauth2client

import sqlalchemy
import sqlalchemy.orm
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.associationproxy import association_proxy

from flask_login import current_user

import pymates as providers

import ibp
from . import oauth2

db = ibp.db
session = ibp.db.session


class UniqueMixin(object):

    @classmethod
    def unique_filter(cls, *args, **kwargs):
        raise NotImplementedError

    @classmethod
    def as_unique(cls, *args, **kwargs):
        cache = getattr(session, '_unique_cache', None)
        if cache is None:
            session._unique_cache = cache = {}

        key = (cls,) + args
        if key in cache:
            obj = cache[key]

        else:
            obj = cls.unique_filter(*args, **kwargs).first()
            if obj is None:
                obj = cls(*args, **kwargs)
                session.add(obj)

            cache[key] = obj

        try:
            session.add(obj)
        except sqlalchemy.exc.InvalidRequestError:
            pass

        return obj


@sqlalchemy.event.listens_for(sqlalchemy.orm.Session, 'after_flush')
def clear_unique_cache(session, ctx):
    session._unique_cache = {}


class ReleaseDate(db.String):

    def __init__(self, date_format='%Y-%m-%d'):
        super(ReleaseDate, self).__init__()
        self.date_format = date_format

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            strptime = datetime.strptime
            try:
                value = strptime(value, self.date_format).date()
            except ValueError:
                pass
            return value
        return process


class Inmate(db.Model, UniqueMixin):
    __tablename__ = 'inmates'

    autoid = db.Column(db.Integer, primary_key=True)

    first_name = db.Column(db.String)
    last_name = db.Column(db.String)

    jurisdiction = db.Column(
        db.Enum('Texas', 'Federal', name='jurisdiction_enum'), nullable=False
    )
    id = db.Column(db.Integer, nullable=False)

    unit_id = db.Column(db.Integer, db.ForeignKey('units.autoid'))
    unit = db.relationship('Unit', uselist=False, back_populates='inmates')

    race = db.Column(db.String)
    sex = db.Column(db.String)
    release = db.Column(ReleaseDate)
    url = db.Column(db.String)

    datetime_fetched = db.Column(db.DateTime)
    date_last_lookup = db.Column(db.Date)

    requests = db.relationship(
        'Request',
        back_populates='inmate', order_by="desc(Request.date_postmarked)",
    )

    alerts = db.relationship('Alert', back_populates='inmate')
    comments = db.relationship(
        'Comment',
        order_by="desc(Comment.datetime)"
    )

    _lookups_association = db.relationship(
        'Lookup',
        order_by='desc(Lookup.datetime)'
    )
    lookups = association_proxy('_lookups_association', 'datetime')

    @classmethod
    def from_response(cls, response):
        jurisdiction = response['jurisdiction']
        id_ = int(response['id'].replace('-', ''))
        with session.no_autoflush:
            inmate = cls.as_unique(jurisdiction, id_)
            inmate.update_from_response(**response)
        return inmate

    @classmethod
    def query_by_autoid(cls, autoid):
        inmate = cls.query.filter_by(autoid=autoid).first()

        if inmate is None or inmate.entry_is_fresh():
            return cls.query.filter_by(autoid=autoid)

        timeout = ibp.config.getfloat('providers', 'timeout')
        inmates, _ = providers.query_by_inmate_id(
            inmate.id, jurisdictions=[inmate.jurisdiction], timeout=timeout
        )
        inmates = map(cls.from_response, inmates)

        session.add_all(inmates)
        session.commit()

        return cls.query.filter_by(autoid=autoid)

    @classmethod
    def query_by_inmate_id(cls, id_):
        inmates, errors = providers.query_by_inmate_id(id_)
        inmates = map(Inmate.from_response, inmates)

        session.add_all(inmates)
        session.commit()

        inmates = cls.query.filter_by(id=id_)
        return inmates, errors

    @classmethod
    def query_by_name(cls, first_name, last_name):
        timeout = ibp.config.getfloat('providers', 'timeout')
        inmates, errors = providers.query_by_name(
            first_name, last_name, timeout=timeout
        )
        inmates = map(Inmate.from_response, inmates)

        session.add_all(inmates)
        session.commit()

        sql_lower = sqlalchemy.func.lower
        inmates = (
            cls.query
            .filter(sql_lower(Inmate.last_name) == sql_lower(last_name))
            .filter(Inmate.first_name.ilike(first_name + "%"))
        )
        return inmates, errors

    @classmethod
    def unique_filter(cls, jurisdiction, id_):
        return cls.query.filter_by(jurisdiction=jurisdiction, id=id_)

    @declared_attr
    def __table_args__(cls):
        return (db.UniqueConstraint('jurisdiction', 'id'),)

    def __init__(self, jurisdiction, id_, **kwargs):
        kwargs['jurisdiction'] = jurisdiction
        kwargs['id'] = id_
        super(Inmate, self).__init__(**kwargs)

    def entry_is_fresh(self):
        if self.datetime_fetched is None:
            return False

        age = datetime.now() - self.datetime_fetched
        ttl_hours = ibp.config.getint('warnings', 'inmates_cache_ttl')
        ttl = timedelta(hours=ttl_hours)
        return age < ttl

    def try_fetch_update(self):
        if not self.entry_is_fresh():
            self = Inmate.query_by_autoid(self.autoid).first()

    def update_from_response(self, **kwargs):
        unit_name = kwargs.get('unit') or ''
        if self.unit is None or self.unit.name != unit_name:
            self.unit = Unit.query.filter_by(name=unit_name).first()

        self.first_name = kwargs['first_name']
        self.last_name = kwargs['last_name']

        self.sex = kwargs.get('sex')
        self.url = kwargs.get('url')
        self.race = kwargs.get('race')
        self.release = kwargs.get('release')

        self.datetime_fetched = kwargs.get('datetime_fetched')
        self.date_last_lookup = kwargs.get('date_last_lookup')


class Lookup(db.Model):
    __tablename__ = 'lookups'

    autoid = db.Column(db.Integer, primary_key=True)
    datetime = db.Column(db.DateTime, nullable=False)
    inmate_id = db.Column(db.Integer, db.ForeignKey('inmates.autoid'))

    def __init__(self, dt):
        self.datetime = dt
        self.done_by = None  # FIXME
        super(Lookup, self).__init__()


class Request(db.Model):
    __tablename__ = 'requests'

    autoid = db.Column(db.Integer, primary_key=True)

    date_processed = db.Column(db.Date, nullable=False)
    date_postmarked = db.Column(db.Date, nullable=False)

    action = db.Column(
        db.Enum('Filled', 'Tossed', name='action_enum'), nullable=False
    )

    inmate_autoid = db.Column(db.Integer, db.ForeignKey('inmates.autoid'))
    inmate = db.relationship(
        'Inmate', uselist=False, back_populates='requests'
    )

    shipment_autoid = db.Column(db.Integer, db.ForeignKey('shipments.autoid'))
    shipment = db.relationship(
        'Shipment', uselist=False, back_populates='requests'
    )

    @property
    def status(self):
        shipped = self.shipment and self.shipment.date_shipped and 'Shipped'
        return (shipped or self.action)

    def __init__(self, **kwargs):
        super(Request, self).__init__(**kwargs)


class Shipment(db.Model):
    __tablename__ = 'shipments'

    autoid = db.Column(db.Integer, primary_key=True)

    date_shipped = db.Column(db.Date, nullable=False)

    tracking_url = db.Column(db.String)
    tracking_code = db.Column(db.String)

    weight = db.Column(db.Integer, nullable=False)
    postage = db.Column(db.Integer, nullable=False)  # postage in cents

    requests = db.relationship(
        'Request', back_populates='shipment'
    )

    unit_id = db.Column(db.Integer, db.ForeignKey('units.autoid'))
    unit = db.relationship(
        'Unit', uselist=False, back_populates='shipments'
    )

    def __init__(self, **kwargs):
        super(Shipment, self).__init__(**kwargs)


if False:
    @sqlalchemy.event.listens_for(sqlalchemy.orm.Session, 'after_flush')
    def delete_empty_shipments(session, ctx):
        query = Shipment.query.filter(~Shipment.requests.any())
        query.delete(synchronize_session=False)


class Comment(db.Model):
    __tablename__ = 'comments'

    autoid = db.Column(db.Integer, primary_key=True)

    datetime = db.Column(db.DateTime, nullable=False)
    author = db.Column(db.String, nullable=False)
    body = db.Column(db.Text, nullable=False)

    inmate_id = db.Column(db.Integer, db.ForeignKey('inmates.autoid'))

    def __init__(self, **kwargs):
        super(Comment, self).__init__(**kwargs)

    @classmethod
    def from_form(cls, form):
        return cls(
            datetime=datetime.today(),
            author=form.author.data,
            body=form.comment.data,
        )


class Unit(db.Model):
    __tablename__ = 'units'

    autoid = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String, nullable=False)
    street1 = db.Column(db.String, nullable=False)
    street2 = db.Column(db.String)

    city = db.Column(db.String, nullable=False)
    zipcode = db.Column(db.String(12), nullable=False)
    state = db.Column(db.String(3), nullable=False)

    url = db.Column(db.String)
    jurisdiction = db.Column(
        db.Enum('Texas', 'Federal', name='jurisdiction_enum'), nullable=False
    )

    shipping_method = db.Column(
        db.Enum('Box', 'Individual', name='shipping_enum')
    )

    inmates = db.relationship('Inmate', back_populates='unit')
    shipments = db.relationship('Shipment', back_populates='unit')

    def __init__(self, **kwargs):
        super(Unit, self).__init__(**kwargs)

    @declared_attr
    def __table_args__(cls):
        return (db.UniqueConstraint('jurisdiction', 'name'),)

    def update_from_form(self, form):
        self.url = form.url.data or None
        self.city = form.city.data
        self.state = form.state.data
        self.street1 = form.street1.data
        self.street2 = form.street2.data
        self.zipcode = form.zipcode.data
        self.shipping_method = form.shipping_method.data or None


class Alert(db.Model):
    __tablename__ = 'alerts'

    autoid = db.Column(db.Integer, primary_key=True)
    requester = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=False)

    inmate_id = db.Column(db.Integer, db.ForeignKey('inmates.autoid'))
    inmate = db.relationship('Inmate', uselist=False, back_populates='alerts')

    def notify(self):
        raise NotImplementedError

        subject = "New request from {} inmate {}, {} #{:08d}".format(
            self.inmate.jurisdiction,
            self.inmate.last_name,
            self.inmate.first_name,
            self.inmate.id
        )

        body = (
            "This is an automatic email alert "
            "to inform you that a request has been received from:\n\n"
            "\t{} inmate {}, {} #{:08d}\n"
            "\t{}\n\n"
            "The volunteer processing this request has been asked "
            "to hold this letter for you.\n"
            "To stop receiving these alerts, please reply stating so."
        ).format(
            self.inmate.jurisdiction,
            self.inmate.last_name,
            self.inmate.first_name,
            self.inmate.id,
            self.inmate.url
        )

        current_user.send_message(self.email, subject, body)


def lazy_property(fn):
    attr_name = '_lazy_' + fn.__name__

    @property
    @functools.wraps(fn)
    def inner(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, fn(self))
        return getattr(self, attr_name)

    return inner


class User(db.Model, UniqueMixin):
    __tablename__ = 'users'

    autoid = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, nullable=False, unique=True)

    is_active = True
    is_anonymous = False

    authorized = db.Column(
        db.Boolean(name='is_authorized_boolean'), default=False, nullable=False
    )

    credentials_id = db.Column(db.Integer, db.ForeignKey('credentials.autoid'))
    credentials = db.relationship(
        'Credentials',
        single_parent=True, uselist=False, cascade='all, delete-orphan'
    )

    @classmethod
    def unique_filter(cls, email, **kwargs):
        return cls.query.filter_by(email=email)

    @classmethod
    def from_google(cls, google):
        http = google.authorize(httplib2.Http())
        service = apiclient.discovery.build('oauth2', 'v2', http=http)
        userinfo = service.userinfo().get().execute()
        user = cls.as_unique(userinfo['email'])

        if user.credentials is None:
            user.credentials = Credentials.from_google(google)

        return user

    @classmethod
    def get(cls, email):
        return cls.query.filter_by(email=email).first()

    @lazy_property
    def _http(self):
        return self.credentials.authorize(httplib2.Http())

    @lazy_property
    def _gmail(self):
        return apiclient.discovery.build('gmail', 'v1', http=self._http)

    @lazy_property
    def _oauth2(self):
        return apiclient.discovery.build('oauth2', 'v2', http=self._http)

    @property
    def is_authenticated(self):
        return self.credentials is not None and self.authorized

    def __init__(self, email, **kwargs):
        super(User, self).__init__(email=email, **kwargs)

    def get_id(self):
        return self.email


class Credentials(db.Model):
    __tablename__ = 'credentials'

    autoid = db.Column(db.Integer, primary_key=True)

    access_token = db.Column(db.String, nullable=False)
    client_id = db.Column(db.String, nullable=False)
    client_secret = db.Column(db.String, nullable=False)
    refresh_token = db.Column(db.String, nullable=False)
    token_expiry = db.Column(db.DateTime, nullable=False)
    token_uri = db.Column(db.String, nullable=False)
    user_agent = db.Column(db.String)

    def __init__(self, **kwargs):
        super(Credentials, self).__init__(**kwargs)

    @classmethod
    def from_google(cls, google):
        kwargs = dict(
            access_token=google.access_token,
            client_id=google.client_id,
            client_secret=google.client_secret,
            refresh_token=google.refresh_token,
            token_expiry=google.token_expiry,
            token_uri=google.token_uri,
            user_agent=google.user_agent
        )
        credentials = cls(**kwargs)
        db.session.commit()
        return credentials

    @lazy_property
    def _google(self):
        credentials = oauth2client.OAuth2Credentials(
            self.access_token,
            self.client_id,
            self.client_secret,
            self.refresh_token,
            self.token_expiry,
            self.token_uri,
            self.user_agent
        )
        store = oauth2.DatabaseStore(session, self.autoid)
        credentials.set_store(store)
        return credentials

    def authorize(self, http):
        return self._google.authorize(http)

import threading
from urlparse import urljoin

import oauth2client.client as oauth2client

from flask import url_for

import ibp

session = ibp.db.session


class DatabaseStore(oauth2client.Storage):

    def __init__(self, connection, autoid):
        self._session = session
        self._connection = session.connection()
        self._autoid = autoid
        super(DatabaseStore, self).__init__(lock=threading.Lock())

    def locked_put(self, credentials):
        sql = """
            UPDATE credentials
            SET
                access_token = ?,
                client_id = ?,
                client_secret = ?,
                refresh_token = ?,
                token_expiry = ?,
                token_uri = ?,
                user_agent = ?
            WHERE autoid = ?
        """
        self._connection.execute(
            sql,
            credentials.access_token,
            credentials.client_id,
            credentials.client_secret,
            credentials.refresh_token,
            credentials.token_expiry,
            credentials.token_uri,
            credentials.user_agent,
            credentials.client_id,
            self._autoid
        )

    def locked_get(self):
        sql = """
            SELECT
                access_token,
                client_id,
                client_secret,
                refresh_token,
                token_expiry,
                token_uri,
                user_agent
            FROM credentials
            WHERE autoid = ?
        """
        row = self._connection.execute(sql, self._autoid).fetchone()
        return oauth2client.OAuth2Credentials(*row)

    def locked_delete(self):
        sql = """
            DELETE FROM credentials
            WHERE autoid = ?
        """
        self._connection.execute(sql, self._autoid)


scopes = [
    urljoin('https://www.googleapis.com/auth', scope)
    for scope in ['userinfo.email', 'userinfo.profile']
]


def flow_from_config():
    google = ibp.get_config_section('google')
    return oauth2client.OAuth2WebServerFlow(
        client_id=google['id'],
        client_secret=google['secret'],
        scope=scopes,
        redirect_uri=url_for('authorized', _external=True)
    )

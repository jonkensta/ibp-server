""":py:mod:`flask` views for the IBP REST API.
"""

import functools

import flask
from flask.views import MethodView

import nameparser

import ibp
from . import models
from . import schemas


@ibp.app.route('/inmate/<jurisdiction>/<int:inmate_id>')
def show_inmate(jurisdiction, inmate_id):
    """:py:mod:`flask` view to handle a GET request for an inmate's info.
    """

    inmates, errors = models.Inmate.query.providers_by_id(inmate_id)
    inmate = inmates.filter_by(jurisdiction=jurisdiction).first_or_404()
    result = schemas.inmate.dump(inmate)
    return {'inmate': result, 'errors': errors}


@ibp.app.route('/inmate')
def show_inmates():
    """:py:mod:`flask` view to handle a GET request for an inmate search.
    """

    try:
        search = flask.request.args['query']
    except KeyError:
        return {'message': "Search input must be provided"}, 400

    if not search:
        return {'message': "Some search input must be provided"}, 400

    query = models.Inmate.query

    try:
        inmate_id = int(search.replace('-', ''))
        inmates, errors = query.providers_by_id(inmate_id)

    except ValueError:
        name = nameparser.HumanName(search)
        inmates, errors = query.providers_by_name(name.first, name.last)

    result = schemas.inmates.dump(inmates)
    return {'inmates': result, 'errors': errors}


class InmateIndexView(MethodView):
    """:py:class:`flask.views.MethodView` subclass for inmate + index views.

    This is a convenience subclass of :py:class:`flask.views.MethodView` for
    interfacing with APIs whose resources are accessed with an inmate's
    information plus an index.

    This subclass overrides the
    :py:meth:`flask.views.MethodView.dispatch_request` method and translates
    the `(jurisdiction, inmate_id, index)` arguments by finding the
    corresponding inmate, handling any corresponding errors, and finally
    passing `(inmate, index)` to the parent method.

    This interface translation provides some shared-code savings by saving each
    view method from having to do the inmate lookup and resultant error
    handling just by itself.

    """

    # pylint: disable=arguments-differ

    def dispatch_request(self, jurisdiction, inmate_id, index):
        """:py:class:`flask.views.MethodView` override for interface translation.
        """
        query = models.Inmate.query
        query = query.filter_by(jurisdiction=jurisdiction, id=inmate_id)
        inmate = query.first_or_404()
        return super().dispatch_request(inmate, index)


class RequestAPI(InmateIndexView):
    """:py:class:`InmateIndexView` API for requests.
    """

    # pylint: disable=no-self-use

    def get(self, inmate, index):
        """get a request"""
        return "handling a get request!111"

    def post(self, inmate, index):
        """create a new request"""
        return "handling a post request!11"

    def delete(self, inmate, index):
        """delete a request"""
        return "deleting a request"

    def put(self, inmate, index):
        """update a single request"""
        return "updating a single reuqest"


ibp.app.add_url_rule(
    '/request/<jurisdiction>/<int:inmate_id>/<int:index>',
    view_func=RequestAPI.as_view('request')
)


class CommentAPI(InmateIndexView):
    """:py:class:`InmateIndexView` API for comments.
    """

    # pylint: disable=no-self-use

    def get(self, inmate, index):
        """get a comment"""
        return "handling a get request!111"

    def post(self, inmate, index):
        """create a new comment"""
        return "handling a post comment"

    def delete(self, inmate, index):
        """delete a comment"""
        return "deleting a comment"

    def put(self, inmate, index):
        """update a single comment"""
        return "updating a single comment"


ibp.app.add_url_rule(
    '/comment/<jurisdiction>/<int:inmate_id>/<int:index>',
    view_func=CommentAPI.as_view('comment')
)

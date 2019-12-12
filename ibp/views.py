""":py:mod:`flask` views for the IBP REST API.

The following :py:mod:`flask` views provide the HTTP endpoints that comprise
the IBP `REST`_ API. The idea here being that a web frontend can issue requests
to these endpoints to affect the state of the IBP database. These requests are
parameterized by the following:

    - The endpoint parameters encoded in the URL.
    - The data parameters included in the request header i.e. JSON.

.. _REST: https://en.wikipedia.org/wiki/Representational_state_transfer

Here's a couple specific examples of using the API defined by these views:

    - ``POST /comment/Texas/10000001``

        Create new comment for Texas inmate # 10000001.

    - ``DELETE /request/Texas/88888888/3``

        Delete request #3 of Texas inmate # 88888888.

    - ``GET /request/Federal/77777777/4``

        Get request #4 of Federal inmate # 77777777.

    - ``PUT /request/Federal/77777777/4``

        Update request #4 of Federal inmate # 77777777.

With the final example of a PUT request, JSON data would need to be included as
part of the HTTP header to include which fields are being updated. In the other
cases, however, the parameters included in the endpoint URL are sufficient as
inputs.

"""

import flask
from flask.views import MethodView

import nameparser

import ibp
from . import misc
from . import models
from . import schemas


@ibp.app.route("/inmate/<jurisdiction>/<int:inmate_id>")
def show_inmate(jurisdiction, inmate_id):
    """:py:mod:`flask` view to handle a GET request for an inmate's info.

    This :py:mod:`flask` view uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    :returns: :py:mod:`flask` JSON response containing the following fields:

        - :py:data:`inmate` JSON encoding of the inmate information.
        - :py:data:`errors` List of error strings encountered during lookup.

    """
    inmates, errors = models.Inmate.query.providers_by_id(inmate_id)
    inmate = inmates.filter_by(jurisdiction=jurisdiction).first_or_404()
    result = schemas.inmate.dump(inmate)
    return {"inmate": result, "errors": errors}


@ibp.app.route("/inmate")
def show_inmates():
    """:py:mod:`flask` view to handle a GET request for an inmate search."""
    try:
        search = flask.request.args["query"]
    except KeyError:
        return {"message": "Search input must be provided"}, 400

    if not search:
        return {"message": "Some search input must be provided"}, 400

    query = models.Inmate.query

    try:
        inmate_id = int(search.replace("-", ""))
        inmates, errors = query.providers_by_id(inmate_id)

    except ValueError:
        name = nameparser.HumanName(search)
        inmates, errors = query.providers_by_name(name.first, name.last)

    result = schemas.inmates.dump(inmates)
    return {"inmates": result, "errors": errors}


class InmateRequiredView(MethodView):
    """:py:class:`flask.views.MethodView` subclass given an inmate is required.

    This is a convenience subclass of :py:class:`flask.views.MethodView` for
    interfacing with APIs whose resources are accessed with an inmate's
    information plus some additional information (such as an index).

    This subclass overrides the
    :py:meth:`flask.views.MethodView.dispatch_request` method and translates
    the `(jurisdiction, inmate_id, *args, **kwargs)` arguments by finding the
    corresponding inmate, handling any corresponding errors, and finally
    passing `(inmate, *args, **kwargs)` to the parent method.

    This interface translation provides some shared-code savings by saving each
    view method from having to do the inmate lookup and resultant error
    handling just by itself.

    """

    # pylint: disable=arguments-differ

    def dispatch_request(self, jurisdiction, inmate_id, *args, **kwargs):
        r""":py:class:`flask.views.MethodView` override for interface translation.

        :param jurisdiction: Political system that houses the inmate.
        :type jurisdiction: str

        :param inmate_id: Inmate numeric identifier.
        :type inmate_id: int

        :param \*args: Unnamed arguments that are passed to parent method.
        :type \*args: tuple

        :param \**kwargs: Generic kwargs that are passed to parent method.
        :type \**kwargs: dict

        :returns: :py:mod:`flask` response from appropriate web method handler.

        """
        query = models.Inmate.query
        query = query.filter_by(jurisdiction=jurisdiction, id=inmate_id)
        inmate = query.first_or_404()
        return super().dispatch_request(inmate, *args, **kwargs)


class RequestAPI(InmateRequiredView):
    """:py:class:`InmateRequiredView` API for requests."""

    # pylint: disable=no-self-use, unused-argument

    def get(self, inmate, index):
        """Get a request."""
        return "handling a get request!111"

    def post(self, inmate):
        """Create a new request."""
        return "handling a post request!11"

    def delete(self, inmate, index):
        """Delete a request."""
        return "deleting a request"

    def put(self, inmate, index):
        """Update a single request."""
        return "updating a single request"


# pylint: disable=invalid-name
request_view = RequestAPI.as_view("request")

ibp.app.add_url_rule(
    "/request/<jurisdiction>/<int:inmate_id>/<int:index>",
    view_func=request_view,
    methods=["GET", "DELETE", "PUT"],
)

ibp.app.add_url_rule(
    "/request/<jurisdiction>/<int:inmate_id>", view_func=request_view, methods=["POST"]
)


class CommentAPI(InmateRequiredView):
    """:py:class:`InmateRequiredView` API for comments."""

    # pylint: disable=no-self-use, unused-argument, no-member

    def post(self, inmate):
        """Create a new comment."""
        comment = schemas.comment.load(flask.request.json)
        comment.index = next(misc.available_indices(inmate.comments))
        inmate.comments.append(comment)
        ibp.db.session.add(comment)
        ibp.db.session.commit()
        return schemas.comment.dump(comment)

    def delete(self, inmate, index):
        """Delete a comment."""
        return "deleting a comment"

    def put(self, inmate, index):
        """Update a single comment."""
        return "updating a single comment"


# pylint: disable=invalid-name
comment_view = CommentAPI.as_view("comment")

ibp.app.add_url_rule(
    "/comment/<jurisdiction>/<int:inmate_id>/<int:index>",
    view_func=comment_view,
    methods=["GET", "DELETE", "PUT"],
)

ibp.app.add_url_rule(
    "/comment/<jurisdiction>/<int:inmate_id>", view_func=comment_view, methods=["POST"]
)

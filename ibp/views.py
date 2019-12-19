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

    - ``GET /inmate/Federal/77777777``

        Get information for Federal inmate # 77777777.

    - ``PUT /request/Federal/77777777/4``

        Update request #4 of Federal inmate # 77777777.

With the examples of the POST and PUT request, JSON data would need to be included as
part of the HTTP header for the fields being created or updated. In the other
cases, however, the parameters included in the endpoint URL might be sufficient
as inputs.

"""

# pylint: disable=no-member

import functools
from datetime import date, datetime

import flask
import nameparser
import marshmallow

import ibp
from . import misc
from . import models
from . import schemas


route = ibp.app.route  # pylint: disable=invalid-name


def load_inmate_from_url_params(view):
    """Decorate a view to require an inmate from URL parameters."""

    @functools.wraps(view)
    def inner(jurisdiction, inmate_id):
        inmates, _ = models.Inmate.query.providers_by_id(inmate_id)
        inmate = inmates.filter_by(jurisdiction=jurisdiction).first_or_404()
        return view(inmate)

    return inner


def load_cls_from_url_params(cls):
    """Decorate a view to require a given model from URL parameters."""

    def outer(view):
        @functools.wraps(view)
        def inner(jurisdiction, inmate_id, index):
            query = cls.query.filter_by(
                inmate_jurisdiction=jurisdiction, inmate_id=inmate_id, index=index,
            )
            obj = query.first_or_404()
            return view(obj)

        return inner

    return outer


@route("/inmate/<jurisdiction>/<int:inmate_id>")
@load_inmate_from_url_params
def show_inmate(inmate):
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
    return schemas.inmate.dump(inmate)


@route("/inmate")
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


@route("/request/<jurisdiction>/<int:inmate_id>", methods=["POST"])
@load_inmate_from_url_params
def post_request(inmate):
    """Create a request."""
    try:
        print(flask.request.json)
        fields = schemas.request.load(flask.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        print(exc.messages)
        return {"message": exc.messages}, 400

    index = misc.get_next_available_index(inmate.requests)
    request = models.Request(index=index, date_processed=date.today(), **fields)
    inmate.requests.append(request)
    ibp.db.session.add(request)
    ibp.db.session.commit()
    return schemas.request.dump(request)


@route("/request/<jurisdiction>/<int:inmate_id>/<int:index>", methods=["DELETE"])
@load_cls_from_url_params(models.Request)
def delete_request(request):
    """Delete a request."""
    ibp.db.session.delete(request)
    ibp.db.session.commit()
    return {}


@route("/request/<jurisdiction>/<int:inmate_id>/<int:index>", methods=["PUT"])
@load_cls_from_url_params(models.Request)
def put_request(request):
    """Update a request."""
    try:
        fields = schemas.request.load(flask.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        return {"message": exc.messages}, 400

    request.update_from_kwargs(**fields)
    ibp.db.session.add(request)
    ibp.db.session.commit()
    return schemas.request.dump(request)


@route("/comment/<jurisdiction>/<int:inmate_id>", methods=["POST"])
@load_inmate_from_url_params
def post_comment(inmate):
    """Create a comment."""
    try:
        fields = schemas.comment.load(flask.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        return {"message": exc.messages}, 400

    index = misc.get_next_available_index(inmate.comments)
    comment = models.Comment(index=index, datetime=datetime.now(), **fields)
    inmate.comments.append(comment)
    ibp.db.session.add(comment)
    ibp.db.session.commit()
    return schemas.comment.dump(comment)


@route("/comment/<jurisdiction>/<int:inmate_id>/<int:index>", methods=["DELETE"])
@load_cls_from_url_params(models.Comment)
def delete_comment(comment):
    """Delete a comment."""
    ibp.db.session.delete(comment)
    ibp.db.session.commit()
    return {}


@route("/comment/<jurisdiction>/<int:inmate_id>/<int:index>", methods=["PUT"])
@load_cls_from_url_params(models.Comment)
def put_comment(comment):
    """Update a comment."""
    try:
        fields = schemas.comment.load(flask.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        return {"message": exc.messages}, 400

    comment.update_from_kwargs(**fields)
    ibp.db.session.add(comment)
    ibp.db.session.commit()
    return schemas.comment.dump(comment)

""":py:mod:`bottle` routes for the IBP REST API.

The following :py:mod:`bottle` routes provide the HTTP endpoints that comprise
the IBP `REST`_ API. The idea here being that a web frontend can issue requests
to these endpoints to affect the state of the IBP database. These requests are
parameterized by the following:

    - The endpoint parameters encoded in the URL.
    - The data parameters included in the request header i.e. JSON.

.. _REST: https://en.wikipedia.org/wiki/Representational_state_transfer

Here's a couple specific examples of using the API defined by these routes:

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

import json
import functools
from datetime import date, datetime

import bottle
import nameparser
import sqlalchemy
import marshmallow

from . import db
from . import misc
from . import models
from . import schemas

from .base import app


def create_sqlalchemy_session(callback):
    """Bottle plugin for handling SQLAlchemy sessions."""

    def wrapper(*args, **kwargs):
        session = db.Session()

        try:
            body = callback(session, *args, **kwargs)
            session.commit()
        except sqlalchemy.exc.SQLAlchemyError as exc:
            session.rollback()
            raise bottle.HTTPError(500, "Database Error", exc)
        finally:
            session.close()

        return body

    return wrapper


app.install(create_sqlalchemy_session)


def use_json_as_response_type(callback):
    """Bottle plugin for setting json as the response type."""

    def wrapper(*args, **kwargs):
        bottle.response.content_type = "application/json"
        body = callback(*args, **kwargs)
        return json.dumps(body)

    return wrapper


app.install(use_json_as_response_type)


def default_error_handler(error):
    """Bottle default error handler."""
    bottle.response.content_type = "application/json"
    bottle.response.status = error.status
    return json.dumps({"message": error.body})


app.default_error_handler = default_error_handler


def load_inmate_from_url_params(route):
    """Decorate a route to load an inmate from URL parameters."""

    @functools.wraps(route)
    def wrapper(session, jurisdiction, inmate_id):
        inmates, _ = db.query_providers_by_id(session, inmate_id)
        try:
            inmate = inmates.filter_by(jurisdiction=jurisdiction).one()
        except sqlalchemy.orm.exc.NoResultFound as exc:
            raise bottle.HTTPError(404, "Page not found") from exc

        return route(session, inmate)

    return wrapper


def load_cls_from_url_params(cls):
    """Decorate a route to load a given model from URL parameters."""

    def decorator(route):
        @functools.wraps(route)
        def wrapper(session, jurisdiction, inmate_id, index):
            query = session.query(cls).filter_by(
                inmate_jurisdiction=jurisdiction, inmate_id=inmate_id, index=index,
            )
            try:
                result = query.one()
            except sqlalchemy.orm.exc.NoResultFound as exc:
                raise bottle.HTTPError(404, "Page not found") from exc

            return route(session, result)

        return wrapper

    return decorator


@app.get("/inmate/<jurisdiction>/<inmate_id:int>")
@load_inmate_from_url_params
def show_inmate(session, inmate):  # pylint: disable=unused-argument
    """:py:mod:`bottle` route to handle a GET request for an inmate's info.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    :returns: :py:mod:`bottle` JSON response containing the following fields:

        - :py:data:`inmate` JSON encoding of the inmate information.
        - :py:data:`errors` List of error strings encountered during lookup.

    """
    return schemas.inmate.dump(inmate)


@app.get("/inmate")
def show_inmates(session):
    """:py:mod:`bottle` route to handle a GET request for an inmate search."""
    try:
        search = bottle.request.get("query")
    except KeyError:
        raise bottle.HTTPError(400, "Search input must be provided")

    if not search:
        raise bottle.HTTPError(400, "Some search input must be provided")

    try:
        inmate_id = int(search.replace("-", ""))
        inmates, errors = db.query_providers_by_id(session, inmate_id)

    except ValueError:
        name = nameparser.HumanName(search)
        inmates, errors = db.query_providers_by_name(session, name.first, name.last)

    result = schemas.inmates.dump(inmates)
    return {"inmates": result, "errors": errors}


@app.post("/request/<jurisdiction>/<inmate_id:int>")
@load_inmate_from_url_params
def post_request(session, inmate):
    """Create a request."""
    try:
        fields = schemas.request.load(bottle.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        raise bottle.HTTPError(400, exc.messages) from exc

    index = misc.get_next_available_index(item.index for item in inmate.requests)
    request = models.Request(index=index, date_processed=date.today(), **fields)
    inmate.requests.append(request)
    session.add(request)
    return schemas.request.dump(request)


@app.delete("/request/<jurisdiction>/<inmate_id:int>/<index:int>")
@load_cls_from_url_params(models.Request)
def delete_request(session, request):
    """Delete a request."""
    session.delete(request)
    return ""


@app.put("/request/<jurisdiction>/<inmate_id:int>/<index:int>")
@load_cls_from_url_params(models.Request)
def put_request(session, request):
    """Update a request."""
    try:
        fields = schemas.request.load(bottle.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        raise bottle.HTTPError(400, exc.messages) from exc

    request.update_from_kwargs(**fields)
    session.add(request)
    return schemas.request.dump(request)


@app.post("/comment/<jurisdiction>/<inmate_id:int>")
@load_inmate_from_url_params
def post_comment(session, inmate):  # pylint: disable=unused-argument
    """Create a comment."""
    try:
        fields = schemas.comment.load(bottle.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        raise bottle.HTTPError(400, exc.messages) from exc

    index = misc.get_next_available_index(item.index for item in inmate.comments)
    comment = models.Comment(index=index, datetime=datetime.now(), **fields)
    inmate.comments.append(comment)
    session.add(comment)
    return schemas.comment.dump(comment)


@app.delete("/comment/<jurisdiction>/<inmate_id:int>/<index:int>")
@load_cls_from_url_params(models.Comment)
def delete_comment(session, comment):
    """Delete a comment."""
    session.delete(comment)
    return {}


@app.put("/comment/<jurisdiction>/<inmate_id:int>/<index:int>")
@load_cls_from_url_params(models.Comment)
def put_comment(session, comment):
    """Update a comment."""
    try:
        fields = schemas.comment.load(bottle.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        raise bottle.HTTPError(400, exc.messages) from exc

    comment.update_from_kwargs(**fields)
    session.add(comment)
    return schemas.comment.dump(comment)

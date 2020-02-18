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

###########
# Plugins #
###########

# setup bottle application
app = bottle.Bottle()  # pylint: disable=invalid-name


def enable_cors(callback):
    """Enable CORS by specifying permissive access-controls."""

    @functools.wraps(callback)
    def wrapper(*args, **kwargs):
        body = callback(*args, **kwargs)
        bottle.response.headers["Access-Control-Allow-Origin"] = "*"
        bottle.response.headers["Access-Control-Allow-Methods"] = "*"
        bottle.response.headers["Access-Control-Allow-Headers"] = "*"
        return body

    return wrapper


app.install(enable_cors)


def create_sqlalchemy_session(callback):
    """Create and close SQLAlchemy sessions for all routes."""

    @functools.wraps(callback)
    def wrapper(*args, **kwargs):
        session = db.Session()

        try:
            body = callback(session, *args, **kwargs)
        except sqlalchemy.exc.SQLAlchemyError as exc:
            session.rollback()
            raise bottle.HTTPError(500, json.dumps("A database error occurred."), exc)
        finally:
            session.close()

        return body

    return wrapper


app.install(create_sqlalchemy_session)


def use_json_as_response_type(callback):
    """Bottle plugin for setting json as the response type."""

    @functools.wraps(callback)
    def wrapper(*args, **kwargs):
        bottle.response.content_type = "application/json"
        return callback(*args, **kwargs)

    return wrapper


app.install(use_json_as_response_type)


##################
# Error handling #
##################


@enable_cors
@use_json_as_response_type
def default_error_handler(error):
    """Handle Bottle errors by setting status code and returning body."""
    bottle.response.status = error.status
    return error.body


app.default_error_handler = default_error_handler


@app.route("/<:re:.*>", method="OPTIONS")
def default_options(*args):  # pylint: disable=unused-argument
    """Enable OPTIONS method for all routes."""


###########
# Helpers #
###########


def load_inmate_from_url_params(route):
    """Decorate a route to load an inmate from URL parameters."""

    @functools.wraps(route)
    def wrapper(session, jurisdiction, inmate_id):
        inmates, _ = db.query_providers_by_id(session, inmate_id)
        try:
            inmate = inmates.filter_by(jurisdiction=jurisdiction).one()
        except sqlalchemy.orm.exc.NoResultFound as exc:
            raise bottle.HTTPError(404, json.dumps("Page not found"), exc)

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
                raise bottle.HTTPError(404, json.dumps("Page not found"), exc)

            return route(session, result)

        return wrapper

    return decorator


#################
# Inmate routes #
#################


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
def search_inmates(session):
    """:py:mod:`bottle` route to handle a GET request for an inmate search."""
    search = bottle.request.query.get("query")

    if not search:
        raise bottle.HTTPError(400, json.dumps("Some search input must be provided"))

    try:
        inmate_id = int(search.replace("-", ""))
        inmates, errors = db.query_providers_by_id(session, inmate_id)

    except ValueError:
        name = nameparser.HumanName(search)

        if not (name.first and name.last):
            message = "If using a name, please specify first and last name"
            raise bottle.HTTPError(400, json.dumps(message))

        inmates, errors = db.query_providers_by_name(session, name.first, name.last)

    result = schemas.inmates.dump(inmates)
    return json.dumps({"inmates": result, "errors": errors})


##################
# Request routes #
##################


@app.post("/request/<jurisdiction>/<inmate_id:int>")
@load_inmate_from_url_params
def create_request(session, inmate):
    """Create a request."""
    try:
        fields = schemas.request.load(bottle.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        raise bottle.HTTPError(400, json.dumps(exc.messages), exc)

    index = misc.get_next_available_index(item.index for item in inmate.requests)
    request = models.Request(index=index, date_processed=date.today(), **fields)
    inmate.requests.append(request)

    session.add(request)
    session.commit()

    return schemas.request.dump(request)


@app.delete("/request/<jurisdiction>/<inmate_id:int>/<index:int>")
@load_cls_from_url_params(models.Request)
def delete_request(session, request):
    """Delete a request."""
    session.delete(request)
    session.commit()


@app.put("/request/<jurisdiction>/<inmate_id:int>/<index:int>")
@load_cls_from_url_params(models.Request)
def update_request(session, request):
    """Update a request."""
    try:
        fields = schemas.request.load(bottle.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        raise bottle.HTTPError(400, json.dumps(exc.messages), exc)

    request.update_from_kwargs(**fields)
    session.add(request)
    session.commit()

    return schemas.request.dump(request)


##################
# Comment routes #
##################


@app.post("/comment/<jurisdiction>/<inmate_id:int>")
@load_inmate_from_url_params
def create_comment(session, inmate):
    """Create a comment."""
    try:
        fields = schemas.comment.load(bottle.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        raise bottle.HTTPError(400, json.dumps(exc.messages), exc)

    index = misc.get_next_available_index(item.index for item in inmate.comments)
    comment = models.Comment(index=index, datetime=datetime.now(), **fields)

    inmate.comments.append(comment)
    session.add(comment)
    session.commit()

    return schemas.comment.dump(comment)


@app.delete("/comment/<jurisdiction>/<inmate_id:int>/<index:int>")
@load_cls_from_url_params(models.Comment)
def delete_comment(session, comment):
    """Delete a comment."""
    session.delete(comment)
    session.commit()


@app.put("/comment/<jurisdiction>/<inmate_id:int>/<index:int>")
@load_cls_from_url_params(models.Comment)
def update_comment(session, comment):
    """Update a comment."""
    try:
        fields = schemas.comment.load(bottle.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        raise bottle.HTTPError(400, json.dumps(exc.messages), exc)

    comment.update_from_kwargs(**fields)
    session.add(comment)
    session.commit()

    return schemas.comment.dump(comment)

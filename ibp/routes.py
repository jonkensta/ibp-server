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

import io
import json
import functools
import traceback
from datetime import date, datetime

import bottle
import nameparser
import sqlalchemy
import marshmallow

from . import db
from . import misc
from . import models
from . import schemas

from .base import config

# setup bottle application
app = bottle.Bottle()  # pylint: disable=invalid-name


###########
# Plugins #
###########


def create_sqlalchemy_session(callback):
    """Create and close SQLAlchemy sessions for all routes."""

    @functools.wraps(callback)
    def wrapper(*args, **kwargs):
        session = db.Session()

        try:
            body = callback(session, *args, **kwargs)
        except sqlalchemy.exc.SQLAlchemyError as exc:
            session.rollback()
            raise bottle.HTTPError(500, "A database error occurred.", exc)
        finally:
            session.close()

        return body

    return wrapper


app.install(create_sqlalchemy_session)
app.install(bottle.JSONPlugin())


def send_bytes(bytes_, mimetype):
    """Bottle method for sending bytes objects."""
    headers = dict()
    headers["Content-Type"] = mimetype
    headers["Content-Length"] = len(bytes_)

    body = "" if bottle.request.method == "HEAD" else bytes_
    return bottle.HTTPResponse(body, **headers)


##################
# Error handling #
##################


def default_error_handler(error):
    """Handle Bottle errors by setting status code and returning body."""
    traceback.print_exc()

    bottle.response.content_type = "application/json"
    bottle.response.status = error.status

    if isinstance(error.body, list):
        return json.dumps({"messages": error.body})

    if isinstance(error.body, str):
        return json.dumps({"messages": [error.body]})

    return error.body


app.default_error_handler = default_error_handler


###########
# Helpers #
###########


def load_inmate_from_url_params(route):
    """Decorate a route to load an inmate from URL parameters."""

    @functools.wraps(route)
    def wrapper(session, jurisdiction, inmate_id):
        query = session.query(models.Inmate).filter_by(
            jurisdiction=jurisdiction, id=inmate_id
        )

        try:
            inmate = query.one()
        except sqlalchemy.orm.exc.NoResultFound:
            inmates, _ = db.query_providers_by_id(session, inmate_id)
            try:
                inmate = inmates.filter_by(jurisdiction=jurisdiction).one()
            except sqlalchemy.orm.exc.NoResultFound as exc:
                raise bottle.HTTPError(404, "Page not found", exc)

        return route(session, inmate)

    return wrapper


def load_unit_from_url_params(route):
    """Decorate a route to load an inmate from URL parameters."""

    @functools.wraps(route)
    def wrapper(session, id):  # pylint: disable=redefined-builtin, invalid-name
        query = session.query(models.Unit).filter_by(id=id)

        try:
            unit = query.one()
        except sqlalchemy.orm.exc.NoResultFound as exc:
            raise bottle.HTTPError(404, "Unit not found", exc)

        return route(session, unit)

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
                raise bottle.HTTPError(404, "Page not found", exc)

            return route(session, result)

        return wrapper

    return decorator


#################
# Inmate routes #
#################


@app.get("/inmate/<jurisdiction>/<inmate_id:int>")
def show_inmate(session, jurisdiction, inmate_id):
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
    query = session.query(models.Inmate).filter_by(
        jurisdiction=jurisdiction, id=inmate_id
    )

    try:
        inmate = query.one()
    except sqlalchemy.orm.exc.NoResultFound:
        inmates, _ = db.query_providers_by_id(session, inmate_id)

        try:
            inmate = inmates.filter_by(jurisdiction=jurisdiction).one()
        except sqlalchemy.orm.exc.NoResultFound as exc:
            raise bottle.HTTPError(404, "Page not found", exc)

    errors = []
    if inmate.db_entry_is_stale():
        inmates, errors = db.query_providers_by_id(session, inmate_id)
        inmate = inmates.filter_by(jurisdiction=jurisdiction).one()

    return {"errors": errors, "inmate": schemas.inmate.dump(inmate)}


@app.get("/inmate")
def search_inmates(session):
    """:py:mod:`bottle` route to handle a GET request for an inmate search."""
    search = bottle.request.query.get("query")

    if not search:
        raise bottle.HTTPError(400, "Some search input must be provided")

    try:
        inmate_id = int(search.replace("-", ""))
        inmates, errors = db.query_providers_by_id(session, inmate_id)

    except ValueError:
        name = nameparser.HumanName(search)

        if not (name.first and name.last):
            message = "If using a name, please specify first and last name"
            raise bottle.HTTPError(400, message)

        inmates, errors = db.query_providers_by_name(session, name.first, name.last)

    return {"inmates": schemas.inmates.dump(inmates), "errors": errors}


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
        raise bottle.HTTPError(400, exc.messages, exc)

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
        raise bottle.HTTPError(400, exc.messages, exc)

    request.update_from_kwargs(**fields)
    session.add(request)
    session.commit()

    return schemas.request.dump(request)


@app.get("/request/<jurisdiction>/<inmate_id:int>/<index:int>/label")
@load_cls_from_url_params(models.Request)
def get_request_label(session, request):  # pylint: disable=unused-argument
    """Get a label for a request."""
    label = misc.render_request_label(request)
    label_bytes_io = io.BytesIO()
    label.save(label_bytes_io, "PNG")
    label_bytes = label_bytes_io.getvalue()
    return send_bytes(label_bytes, "image/png")


@app.get("/request/<jurisdiction>/<inmate_id:int>/<index:int>/address")
@load_cls_from_url_params(models.Request)
def get_request_address(session, request):  # pylint: disable=unused-argument
    """Get the address for shipping a request."""
    inmate = request.inmate
    if inmate.db_entry_is_stale():
        db.query_providers_by_id(session, inmate.id)

    unit = inmate.unit
    if unit is None:
        raise bottle.HTTPError(400, "Inmate is not assigned to a unit.")

    try:
        assert inmate.first_name is not None and inmate.last_name is not None
    except AssertionError:
        inmate_name = f"Inmate #{inmate.id:08d}"
    else:
        first, last = inmate.first_name.title(), inmate.last_name.title()
        inmate_name = f"{first} {last} #{inmate.id:08d}"

    return {
        "name": inmate_name,
        "street1": unit.street1,
        "street2": unit.street2,
        "city": unit.city,
        "state": unit.state,
        "zipcode": unit.zipcode,
    }


@app.post("/request/<jurisdiction>/<inmate_id:int>/<index:int>/ship")
@load_cls_from_url_params(models.Request)
def ship_request(session, request):  # pylint: disable=unused-argument
    """Ship a request."""
    inmate = request.inmate
    if inmate.db_entry_is_stale():
        db.query_providers_by_id(session, inmate.id)

    unit = inmate.unit
    if unit is None:
        raise bottle.HTTPError(400, "Inmate is not assigned to a unit.")

    try:
        fields = schemas.shipment.load(bottle.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        raise bottle.HTTPError(400, exc.messages, exc)

    shipment = models.Shipment(request=request, unit=unit, **fields)
    session.add(shipment)
    session.commit()

    return schemas.shipment.dump(shipment)


@app.get("/request/<autoid:int>/address")
def get_request_address_autoid(session, autoid):
    """Get the address for shipping a request given the request autoid."""
    try:
        request = session.query(models.Request).filter_by(autoid=autoid).one()
    except sqlalchemy.orm.exc.NoResultFound as exc:
        raise bottle.HTTPError(404, "Request not found.", exc)

    inmate = request.inmate
    if inmate.db_entry_is_stale():
        db.query_providers_by_id(session, inmate.id)

    unit = inmate.unit
    if unit is None:
        raise bottle.HTTPError(400, "Inmate is not assigned to a unit.")

    try:
        assert inmate.first_name is not None and inmate.last_name is not None
    except AssertionError:
        inmate_name = f"Inmate #{inmate.id:08d}"
    else:
        first, last = inmate.first_name.title(), inmate.last_name.title()
        inmate_name = f"{first} {last} #{inmate.id:08d}"

    return {
        "name": inmate_name,
        "street1": unit.street1,
        "street2": unit.street2,
        "city": unit.city,
        "state": unit.state,
        "zipcode": unit.zipcode,
    }


@app.post("/request/<autoid:int>/ship")
def ship_request_autoid(session, autoid):
    """Ship a request given its autoid."""
    try:
        request = session.query(models.Request).filter_by(autoid=autoid).one()
    except sqlalchemy.orm.exc.NoResultFound as exc:
        raise bottle.HTTPError(404, "Request not found.", exc)

    inmate = request.inmate
    if inmate.db_entry_is_stale():
        db.query_providers_by_id(session, inmate.id)

    unit = inmate.unit
    if unit is None:
        raise bottle.HTTPError(400, "Inmate is not assigned to a unit.")

    try:
        fields = schemas.shipment.load(bottle.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        raise bottle.HTTPError(400, exc.messages, exc)

    shipment = models.Shipment(request=request, unit=unit, **fields)
    session.add(shipment)
    session.commit()

    return schemas.shipment.dump(shipment)


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
        raise bottle.HTTPError(400, exc.messages, exc)

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
        raise bottle.HTTPError(400, exc.messages, exc)

    comment.update_from_kwargs(**fields)
    session.add(comment)
    session.commit()

    return schemas.comment.dump(comment)


###############
# Unit routes #
###############


@app.get("/unit/<id:int>/address")
def get_unit_address(session, id):  # pylint: disable=redefined-builtin, invalid-name
    """Get bulk shipping address of a unit."""
    raise NotImplementedError


@app.get("/unit/<id:int>/ship")
def ship_to_unit(session, id):  # pylint: disable=redefined-builtin, invalid-name
    """Get bulk shipping address of a unit."""
    raise NotImplementedError


################
# Misc. routes #
################


@app.get("/config", skip=[create_sqlalchemy_session])
def get_config():  # pylint: disable=unused-argument
    """Get server warnings configuration."""
    warnings_keys = config["warnings"].keys()
    warnings_vals = map(int, config["warnings"].values())
    warnings = dict(zip(warnings_keys, warnings_vals))
    address = dict(config["address"])
    return {"warnings": warnings, "address": address}

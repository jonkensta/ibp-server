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
from datetime import date, datetime

import bottle  # type: ignore
import nameparser  # type: ignore
import sqlalchemy  # type: ignore
import marshmallow  # type: ignore

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


def get_cors_headers() -> dict[str, str]:
    """Get the CORS headers used within this app."""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": ", ".join(
            ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        ),
        "Access-Control-Allow-Headers": ", ".join(
            [
                "Origin",
                "Accept",
                "Content-Type",
                "X-Requested-With",
                "X-CSRF-Token",
            ]
        ),
    }


def enable_cors(callback):
    """Enable CORS for all routes."""

    @functools.wraps(callback)
    def wrapper(*args, **kwargs):
        bottle.response.headers.update(get_cors_headers())
        return callback(*args, **kwargs)

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
            raise bottle.HTTPError(500, "A database error occurred.", exc)
        finally:
            session.close()

        return body

    return wrapper


app.install(create_sqlalchemy_session)
app.install(bottle.JSONPlugin())


def send_bytes(bytes_, mimetype):
    """Bottle method for sending bytes objects."""
    headers = {
        "Content-Type": mimetype,
        "Content-Length": len(bytes_),
    }

    body = "" if bottle.request.method == "HEAD" else bytes_
    return bottle.HTTPResponse(body, **headers)


##################
# Error handling #
##################


def default_error_handler(error):
    """Handle Bottle errors by setting status code and returning body."""
    bottle.response.content_type = "application/json"
    bottle.response.status = error.status
    bottle.response.headers.update(get_cors_headers())

    messages = (
        [str(message) for message in error.body]
        if (isinstance(error.body, list))
        else [str(error.body)]
    )

    return json.dumps({"messages": messages})


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


def one_or_404(query):
    """Return a single result from a query or raise a 404 HTTP error."""
    try:
        return query.one()
    except sqlalchemy.orm.exc.NoResultFound as exc:
        raise bottle.HTTPError(404, "Unit not found", exc)


def load_unit_from_url_params(route):
    """Decorate a route to load an inmate from URL parameters."""

    @functools.wraps(route)
    def wrapper(session, id):  # pylint: disable=redefined-builtin, invalid-name
        query = session.query(models.Unit).filter_by(id=id)
        unit = one_or_404(query)
        return route(session, unit)

    return wrapper


def load_cls_from_inmate_index(cls):
    """Decorate a route to load a given model from inmate index URL parameters."""

    def decorator(route):
        @functools.wraps(route)
        def wrapper(session, jurisdiction, inmate_id, index):
            query = session.query(cls).filter_by(
                inmate_jurisdiction=jurisdiction,
                inmate_id=inmate_id,
                index=index,
            )
            result = one_or_404(query)
            return route(session, result)

        return wrapper

    return decorator


def load_cls_from_autoid(cls):
    """Decorate a route to load a given model from autoid URL parameters."""

    def decorator(route):
        @functools.wraps(route)
        def wrapper(session, autoid):
            query = session.query(cls).filter_by(autoid=autoid)
            result = one_or_404(query)
            return route(session, result)

        return wrapper

    return decorator


def get_request_address(session, request):
    """Get the address to fill a request."""
    inmate = request.inmate
    if inmate.db_entry_is_stale():
        db.query_providers_by_id(session, inmate.id)

    unit = inmate.unit
    if unit is None:
        raise bottle.HTTPError(400, "Inmate is not assigned to a unit.")

    if not (inmate.first_name is None or inmate.last_name is None):
        first, last = inmate.first_name.title(), inmate.last_name.title()
        inmate_name = f"{first} {last} #{inmate.id:08d}"
    else:
        inmate_name = f"Inmate #{inmate.id:08d}"

    return {
        "name": inmate_name,
        "street1": unit.street1,
        "street2": unit.street2,
        "city": unit.city,
        "state": unit.state,
        "zipcode": unit.zipcode,
    }


def parse_request_json(schema):
    """Parse the bottle request JSON using a schema."""
    try:
        return schema.load(bottle.request.json)
    except marshmallow.exceptions.ValidationError as exc:
        raise bottle.HTTPError(400, exc.messages, exc)


def ship_request(session, request):
    """Ship a request."""
    inmate = request.inmate
    if inmate.db_entry_is_stale():
        db.query_providers_by_id(session, inmate.id)

    unit = inmate.unit
    if unit is None:
        raise bottle.HTTPError(400, "Inmate is not assigned to a unit.")

    fields = parse_request_json(schemas.shipment)

    shipment = models.Shipment(
        requests=[request], date_shipped=date.today(), unit=unit, **fields
    )
    session.add(shipment)
    session.commit()

    return schemas.shipment.dump(shipment)


#################
# Options route #
#################


@app.route("/<:re:.*>", method="OPTIONS", skip=[create_sqlalchemy_session])
def enable_options_generic_route():
    """Respond to all OPTIONS method for all routes."""


#################
# Inmate routes #
#################


@app.get("/inmate/<jurisdiction>/<inmate_id:int>")
@load_inmate_from_url_params
def show_inmate(session, inmate):
    """:py:mod:`bottle` route to handle a GET request for an inmate's info.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    This is used to load the appropriate inmate.

    :returns: :py:mod:`bottle` JSON response containing the following fields:

        - :py:data:`inmate` JSON encoding of the inmate information.
        - :py:data:`errors` List of error strings encountered during lookup.

    """
    errors = []
    if inmate.db_entry_is_stale():
        inmates, errors = db.query_providers_by_id(session, inmate.id)
        inmate = inmates.filter_by(jurisdiction=inmate.jurisdiction).one()

    return {"errors": errors, "inmate": schemas.inmate.dump(inmate)}


@app.get("/inmate")
def search_inmates(session):
    """:py:mod:`bottle` route to handle a GET request for an inmate search.

    This :py:mod:`bottle` route uses the following GET parameter:

    :param query: The inmate query string.
    :type query: str

    This is used as the query for the inmate search.

    :returns: :py:mod:`bottle` JSON response containing the following fields:

        - :py:data:`inmates` JSON encoding of the list of inmates.
        - :py:data:`errors` List of error strings encountered during search.

    """
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
            raise bottle.HTTPError(400, message)  # pylint: disable=raise-missing-from

        inmates, errors = db.query_providers_by_name(session, name.first, name.last)

    return {"inmates": schemas.inmates.dump(inmates), "errors": errors}


##################
# Request routes #
##################


@app.post("/request/<jurisdiction>/<inmate_id:int>")
@load_inmate_from_url_params
def create_request(session, inmate):
    """:py:mod:`bottle` route to handle creating a request.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    This is used to load the appropriate inmate for request creation.

    :returns: :py:mod:`bottle` JSON response containing the request information.

    """
    fields = parse_request_json(schemas.request)

    index = misc.get_next_available_index(item.index for item in inmate.requests)
    request = models.Request(index=index, date_processed=date.today(), **fields)
    inmate.requests.append(request)

    session.add(request)
    session.commit()

    return schemas.request.dump(request)


@app.delete("/request/<jurisdiction>/<inmate_id:int>/<index:int>")
@load_cls_from_inmate_index(models.Request)
def delete_request(session, request):
    """:py:mod:`bottle` route to handle deleting a request.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    :param request_index: Request index.
    :type request_index: int

    This is used to load the appropriate request for deletion.

    :returns: None.

    """
    session.delete(request)
    session.commit()
    return {}


@app.put("/request/<jurisdiction>/<inmate_id:int>/<index:int>")
@load_cls_from_inmate_index(models.Request)
def update_request(session, request):
    """:py:mod:`bottle` route to handle updating a request.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    :param request_index: Request index.
    :type request_index: int

    This is used to load the appropriate request for updating.

    :returns: :py:mod:`bottle` JSON response containing the request information.

    """
    fields = parse_request_json(schemas.request)

    request.update_from_kwargs(**fields)
    session.add(request)
    session.commit()

    return schemas.request.dump(request)


@app.get("/request/<jurisdiction>/<inmate_id:int>/<index:int>/label")
@load_cls_from_inmate_index(models.Request)
def get_request_label(session, request):  # pylint: disable=unused-argument
    """:py:mod:`bottle` route to get a label for a request.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    :param request_index: Request index.
    :type request_index: int

    This is used to load the appropriate request.

    :returns: :py:mod:`bottle` image/png bytes object.

    """
    label = misc.render_request_label(request)
    label_bytes_io = io.BytesIO()
    label.save(label_bytes_io, "PNG")
    label_bytes = label_bytes_io.getvalue()
    return send_bytes(label_bytes, "image/png")


@app.get("/request/<jurisdiction>/<inmate_id:int>/<index:int>/address")
@load_cls_from_inmate_index(models.Request)
def get_request_address_inmate_index(session, request):
    """:py:mod:`bottle` route to get the address for a request.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    :param request_index: Request index.
    :type request_index: int

    This is used to load the appropriate request.

    :returns: :py:mod:`bottle` JSON response containing the request address information.

    """
    return get_request_address(session, request)


@app.post("/request/<jurisdiction>/<inmate_id:int>/<index:int>/ship")
@load_cls_from_inmate_index(models.Request)
def ship_request_inmate_index(session, request):
    """:py:mod:`bottle` route to ship a request.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    :param request_index: Request index.
    :type request_index: int

    This is used to load the appropriate request.

    :returns: :py:mod:`bottle` JSON response containing the shipment information.

    """
    return ship_request(session, request)


@app.get("/request/<autoid:int>/address")
@load_cls_from_autoid(models.Request)
def get_request_address_autoid(session, request):
    """:py:mod:`bottle` route to get an address for shipping a request given its autoid.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param request_autoid: Request database autoid.
    :type request_autoid: int

    This is used to load the appropriate request.

    :returns: :py:mod:`bottle` JSON response containing the request address.

    """
    return get_request_address(session, request)


@app.post("/request/<autoid:int>/ship")
@load_cls_from_autoid(models.Request)
def ship_request_autoid(session, request):
    """:py:mod:`bottle` route to ship a request given its autoid.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param request_autoid: Request database autoid.
    :type request_autoid: int

    This is used to load the appropriate request.

    :returns: :py:mod:`bottle` JSON response containing the shipment.

    """
    return ship_request(session, request)


##################
# Comment routes #
##################


@app.post("/comment/<jurisdiction>/<inmate_id:int>")
@load_inmate_from_url_params
def create_comment(session, inmate):
    """:py:mod:`bottle` route to handle creating a comment.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    This is used to load the appropriate inmate for creating the comment.

    :returns: :py:mod:`bottle` JSON response containing the comment information.

    """
    fields = parse_request_json(schemas.comment)

    index = misc.get_next_available_index(item.index for item in inmate.comments)
    comment = models.Comment(index=index, datetime=datetime.now(), **fields)

    inmate.comments.append(comment)
    session.add(comment)
    session.commit()

    return schemas.comment.dump(comment)


@app.delete("/comment/<jurisdiction>/<inmate_id:int>/<index:int>")
@load_cls_from_inmate_index(models.Comment)
def delete_comment(session, comment):
    """:py:mod:`bottle` route to handle deleting a comment.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    :param comment_index: Comment index.
    :type comment_index: int

    This is used to load the appropriate comment for deleting.

    :returns: None.

    """
    session.delete(comment)
    session.commit()
    return {}


@app.put("/comment/<jurisdiction>/<inmate_id:int>/<index:int>")
@load_cls_from_inmate_index(models.Comment)
def update_comment(session, comment):
    """:py:mod:`bottle` route to handle updating a comment.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    :param comment_index: Comment index.
    :type comment_index: int

    This is used to load the appropriate comment for updating.

    :returns: :py:mod:`bottle` JSON response containing the comment information.

    """
    fields = parse_request_json(schemas.comment)

    comment.update_from_kwargs(**fields)
    session.add(comment)
    session.commit()

    return schemas.comment.dump(comment)


###############
# Unit routes #
###############


@app.get("/unit/<id:int>/address")
@load_unit_from_url_params
def get_unit_address(session, unit):  # pylint: disable=unused-argument
    """:py:mod:`bottle` route to get the bulk shipping address for a unit.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param unit_id: Unit numeric identifier.
    :type unit_id: int

    :returns: :py:mod:`bottle` JSON response containing the unit bulk shipping address.

    """
    try:
        name = config["shipping"]["unit_address_name"]
    except AttributeError:
        name = "ATTN: Mailroom Staff"

    return {
        "name": name,
        "street1": unit.street1,
        "street2": unit.street2,
        "city": unit.city,
        "state": unit.state,
        "zipcode": unit.zipcode,
    }


@app.post("/unit/<id:int>/ship")
@load_unit_from_url_params
def ship_to_unit(session, unit):
    """:py:mod:`bottle` route for shipping a bulk package to a unit.

    This :py:mod:`bottle` route uses the following parameters extracted from the
    endpoint URL:

    :param unit_id: Unit numeric identifier.
    :type unit_id: int

    :returns: :py:mod:`bottle` JSON response containing the bulk shipment information.

    """
    fields = parse_request_json(schemas.shipment)

    shipment = models.Shipment(
        requests=[], unit=unit, date_shipped=date.today(), **fields
    )
    session.add(shipment)
    session.commit()

    return schemas.shipment.dump(shipment)


@app.get("/units")
def get_units(session):
    """:py:mod:`bottle` route for getting a list of units.

    :returns: :py:mod:`bottle` JSON response containing the list of units.

    """
    units = session.query(models.Unit)
    return {"units": schemas.units.dump(units)}


################
# Misc. routes #
################


@app.get("/config", skip=[create_sqlalchemy_session])
def get_config():
    """:py:mod:`bottle` route for getting the server configuration.

    :returns: :py:mod:`bottle` JSON response containing the following:

        - :py:data:`warnings` JSON encoding of the warnings configuration.
        - :py:data:`address` JSON encoding of the return address.

    """
    warnings = dict((key, int(value)) for (key, value) in config["warnings"].items())
    address = dict(config["address"])
    return {"warnings": warnings, "address": address}

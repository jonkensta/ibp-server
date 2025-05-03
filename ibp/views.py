"""IBP flask application views."""

import datetime
import functools

import flask
from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    render_template_string,
    url_for,
)

from . import flask_forms, models, warnings
from .base import app, config, csrf, db, log_handlers, log_stream
from .query import inmates_by_autoid as query_inmates_by_autoid
from .query import inmates_by_inmate_id as query_inmates_by_inmate_id
from .query import inmates_by_name as query_inmates_by_name


def appkey_required(view_function):
    """Require an appkey for a given view."""
    correct_appkey = config.get("server", "apikey")

    @functools.wraps(view_function)
    def inner(*args, **kwargs):
        received_appkey = flask.request.form.get("key")
        if received_appkey == correct_appkey:
            return view_function(*args, **kwargs)
        return "an application key is required", 401

    return inner


@app.route("/")
def index():
    """Load the main web page."""
    app.logger.debug("loading index")
    return render_template("index.html")


@app.route("/view_log")
def view_log():
    """Load the server log."""
    app.logger.debug("loading log")
    for handler in log_handlers:
        handler.flush()
    log = log_stream.lines
    return render_template("view_log.html", log=log)


@app.route("/inmates", methods=["GET", "POST"])
def search_inmates():
    """Perform an inmate search."""
    form = flask_forms.InmateSearchForm()

    if flask.request.method == "GET":
        app.logger.debug("loading search_inmates")
        return render_template("search_inmates.html", form=form)

    if form.validate():
        first = form.first_name.data
        last = form.last_name.data

        if first and last:
            first = form.first_name.data
            last = form.last_name.data
            inmates, errors = query_inmates_by_name(db.session, first, last)
        else:
            id_ = form.id_.data
            inmates, errors = query_inmates_by_inmate_id(db.session, id_)

    else:
        return render_template("search_inmates.html", form=form)

    if errors:
        app.logger.debug("one or more providers returned a request exception")

    for error in errors:
        flash(error, "alert-warning")

    inmates = inmates.all()  # get all results from inmates query

    if not inmates:
        app.logger.debug("no search results; loading search_inmates")
        flask.flash("no inmates matched your search", "alert-warning")
        return render_template("search_inmates.html", form=form)

    if len(inmates) == 1:
        app.logger.debug("loading single search result in view_inmate")
        inmate = inmates[0]
        return redirect(url_for("view_inmate", autoid=inmate.autoid))

    app.logger.debug("loading search results in list_inmates")
    return render_template("list_inmates.html", inmates=inmates)


@app.route("/view_inmate/<int:autoid>")
def view_inmate(autoid):
    """Load the page for a single inmate."""
    inmate = query_inmates_by_autoid(db.session, autoid).first_or_404()
    app.logger.debug(
        "loading view_inmate for %s inmate #%08d", inmate.jurisdiction, inmate.id
    )

    with db.session.begin_nested():
        del inmate.lookups[2:]
        inmate.lookups.append(datetime.datetime.now())

    inmate = query_inmates_by_autoid(db.session, autoid).one()
    postmarkdate = flask.session.get("postmarkdate")
    comment_form = flask_forms.Comment()

    return render_template(
        "view_inmate.html",
        inmate=inmate,
        postmarkdate=postmarkdate,
        date_today=datetime.date.today(),
        comment_form=comment_form,
    )


@app.route("/add_request/<int:inmate_autoid>", methods=["POST"])
def add_request(inmate_autoid):
    """Add a request for a specific inmate."""
    inmate = query_inmates_by_autoid(db.session, inmate_autoid).first_or_404()

    date_str = flask.request.form.get("postmarkdate", "")
    try:
        postmarkdate = datetime.date.fromisoformat(date_str)
    except ValueError:
        return "Please enter the USPS postmark date on the envelope.", 400

    flask.session["postmarkdate"] = postmarkdate.isoformat()

    action = flask.request.form.get("action", "Filled")

    request = models.Request(
        action=action,
        date_postmarked=postmarkdate,
        date_processed=datetime.date.today(),
        inmate=inmate,
    )
    db.session.add(request)
    inmate.requests.append(request)
    db.session.commit()

    app.logger.debug(
        "adding request #%d with %s postmark for %s inmate #%08d",
        request.autoid,
        postmarkdate,
        inmate.jurisdiction,
        inmate.id,
    )

    request = db.session.query(models.Request).filter_by(autoid=request.autoid).one()
    rendered_request = render_template("request.html", request=request)

    return jsonify({"request_autoid": str(request.autoid), "request": rendered_request})


@app.route("/request_warnings/<int:autoid>", methods=["POST"])
def request_warnings(autoid):
    """Return request warnings."""
    inmate = query_inmates_by_autoid(db.session, autoid).first_or_404()

    date_str = flask.request.form.get("postmarkdate", "")
    try:
        postmarkdate = datetime.date.fromisoformat(date_str)
    except ValueError:
        return "Please enter the USPS postmark date on the envelope.", 400

    flask.session["postmarkdate"] = postmarkdate.isoformat()

    app.logger.debug(
        "checking warnings for %s inmate #%08d, postmarkdate %s",
        inmate.jurisdiction,
        inmate.id,
        postmarkdate,
    )

    messages = []
    messages.extend(warnings.inmate(inmate))
    messages.extend(warnings.request(inmate, postmarkdate))

    if not messages:
        app.logger.debug(
            "no warnings found for %s inmate #%08d, postmarkdate %s",
            inmate.jurisdiction,
            inmate.id,
            postmarkdate,
        )
        return ""

    app.logger.debug(
        "warnings were found for %s inmate #%08d, postmarkdate %s",
        inmate.jurisdiction,
        inmate.id,
        postmarkdate,
    )

    template = """
        <ul>
            {% for message in messages %}
            <li>{{ message }}</li>
            {% endfor %}
        </ul>
    """
    template = template.strip()

    return render_template_string(template, messages=messages)


@app.route("/request_label/<int:autoid>", methods=["POST"])
def request_label(autoid):
    """Return a request label."""
    request = db.session.query(models.Request).filter_by(autoid=autoid).first_or_404()
    app.logger.debug("rendering label for request #%d", autoid)
    return render_template("request_label.xml", request=request)


@app.route("/request_info/<int:autoid>")
def request_info(autoid):
    """Return info for a request."""
    request = db.session.query(models.Request).filter_by(autoid=autoid).first_or_404()
    app.logger.debug("fetching information for request #%d", autoid)

    if request.inmate is None:
        return "Request does not have an associated inmate", 400

    inmate = request.inmate
    unit = inmate.unit

    return jsonify(
        {
            "inmate_jurisdiction": inmate.jurisdiction,
            "inmate_name": inmate.last_name + ", " + inmate.first_name,
            "inmate_id": f"{inmate.id:08d}",
            "package_id": request.autoid,
            "unit_name": unit and unit.street1 or "N/A",
            "unit_shipping_method": unit and unit.shipping_method or "N/A",
        }
    )


@app.route("/delete_request/<int:autoid>", methods=["DELETE"])
def delete_request(autoid):
    """Delete a request."""
    request = db.session.query(models.Request).filter_by(autoid=autoid).first_or_404()
    app.logger.debug("deleting request #%d", autoid)
    db.session.delete(request)
    db.session.commit()
    return ""


@app.route("/add_comment/<int:inmate_autoid>", methods=["POST"])
def add_comment(inmate_autoid):
    """Create a comment."""
    inmate = query_inmates_by_autoid(db.session, inmate_autoid).first_or_404()
    form = flask_forms.Comment()

    if form.validate():
        comment = models.Comment.from_form(form)
        db.session.add(comment)
        inmate.comments.append(comment)
        db.session.commit()

        app.logger.debug(
            "adding comment #%d for %s inmate #%08d",
            comment.autoid,
            inmate.jurisdiction,
            inmate.id,
        )

        comment = render_template("comment.html", comment=comment)
        fieldset = render_template("comment_fieldset.html", comment_form=form)
        return jsonify({"comment": comment, "fieldset": fieldset})

    fieldset = render_template("comment_fieldset.html", comment_form=form)
    return fieldset, 400


@app.route("/delete_comment/<int:autoid>", methods=["DELETE"])
def delete_comment(autoid):
    """Delete a comment."""

    comment = db.session.query(models.Comment).filter_by(autoid=autoid).first_or_404()
    app.logger.debug("deleting comment #%d", autoid)
    db.session.delete(comment)
    db.session.commit()
    return ""


@app.route("/list_units")
def list_units():
    """Return the units view."""
    app.logger.debug("loading list_units")
    units = db.session.query(models.Unit)
    return render_template("list_units.html", units=units)


@app.route("/view_unit/<int:autoid>", methods=["GET", "POST"])
def view_unit(autoid):
    """Return a unit view."""
    unit = db.session.query(models.Unit).filter_by(autoid=autoid).first_or_404()
    form = flask_forms.Unit()

    if flask.request.method == "GET":
        app.logger.debug("loading view_unit for %s Unit", unit.name)
        form.update_from_model(unit)

    elif form.validate():
        unit.update_from_form(form)
        db.session.commit()
        app.logger.debug("posting updates on %s Unit", unit.name)
        flask.flash("unit successfully updated", "alert-success")

    return render_template("view_unit.html", form=form, unit=unit)


@csrf.exempt
@app.route("/return_address", methods=["POST"])
@appkey_required
def return_address():
    """Return the IBP mailing return address."""
    app.logger.debug("loading return_address view")
    address = dict(config["address"])
    return jsonify(address)


@csrf.exempt
@app.route("/request_address/<int:autoid>", methods=["POST"])
@appkey_required
def request_address(autoid):
    """Return the a request address."""

    app.logger.debug("loading request_address view for request %d", autoid)
    request = models.Request.query.filter_by(autoid=autoid).first_or_404()

    inmate_autoid = request.inmate.autoid
    inmate = query_inmates_by_autoid(db.session, inmate_autoid).first()

    if inmate is None:
        return "inmate is no longer in the system", 400

    unit = inmate.unit
    if unit is None:
        return "inmate is not assigned to a unit", 400

    first_name = inmate.first_name.title()
    last_name = inmate.last_name.title()
    inmate_name = f"{first_name} {last_name} #{inmate.id:08d}"

    return jsonify(
        {
            "name": inmate_name,
            "street1": unit.street1,
            "street2": unit.street2,
            "city": unit.city,
            "state": unit.state,
            "zipcode": unit.zipcode,
        }
    )


@csrf.exempt
@app.route("/unit_autoids", methods=["POST"])
@appkey_required
def unit_autoids():
    """Return a list of unit autoids."""
    app.logger.debug("loading unit_autoids view")
    units = db.session.query(models.Unit)
    autoids = {unit.name: unit.autoid for unit in units}
    return jsonify(autoids)


@csrf.exempt
@app.route("/unit_address/<int:autoid>", methods=["POST"])
@appkey_required
def unit_address(autoid):
    """Return a unit address."""
    app.logger.debug("loading unit_address view for unit %d", autoid)
    unit = db.session.query(models.Unit).filter_by(autoid=autoid).first_or_404()
    name = config.get("shipping", "unit_address_name")

    return jsonify(
        {
            "name": name,
            "street1": unit.street1,
            "street2": unit.street2,
            "city": unit.city,
            "state": unit.state,
            "zipcode": unit.zipcode,
        }
    )


@csrf.exempt
@app.route("/request_destination/<int:autoid>", methods=["POST"])
@appkey_required
def request_destination(autoid):
    """Return the destination of a request."""
    app.logger.debug("loading request_destination view for request %d", autoid)
    request = db.session.query(models.Request).filter_by(autoid=autoid).first_or_404()

    inmate_autoid = request.inmate.autoid
    inmate = query_inmates_by_autoid(db.session, inmate_autoid).first()

    if inmate is None:
        return "inmate is no longer in the system.", 400

    unit = inmate.unit
    if unit is None:
        msg = f"inmate '{inmate.autoid}' is not assigned to a unit"
        app.logger.debug(msg)
        return msg, 400

    return jsonify({"name": unit.name})


@csrf.exempt
@app.route("/ship_requests", methods=["POST"])
@appkey_required
def ship_requests():
    """Ship a request."""
    app.logger.debug("loading ship_requests view")

    form = flask_forms.Shipment(data=flask.request.form)
    form.csrf_token.data = form.csrf_token.current_token

    if not form.validate():
        return "form data invalid", 400

    request_ids = set(form.request_ids.data)

    def get_request_from_autoid(autoid):
        return db.session.query(models.Request).filter_by(autoid=autoid).first_or_404()

    requests = list(map(get_request_from_autoid, request_ids))

    unit_autoid = form.unit_autoid.data
    if unit_autoid:
        unit = (
            db.session.query(models.Unit).filter_by(autoid=unit_autoid).first_or_404()
        )
    elif requests:
        unit = requests[0].inmate.unit
    else:
        msg = "Either unit name or or one request ID must be given"
        return msg, 400

    for request in requests:
        inmate_autoid = request.inmate.autoid
        inmate = query_inmates_by_autoid(db.session, inmate_autoid).first()

        if inmate is None:
            msg = f"inmate for request {request.autoid} is no longer in the system"
            app.logger.debug(msg)
            return msg, 400

        if inmate.unit is None:
            msg = f"inmate for request {request.autoid} is not assigned to a unit"
            app.logger.debug(msg)
            return msg, 400

        if inmate.unit.name != unit.name:
            msg = f"inmates are not all assigned to '{unit.name}' unit"
            app.logger.debug(msg)
            return msg, 400

    shipment = models.Shipment(
        requests=requests,
        date_shipped=datetime.date.today(),
        unit=unit,
        weight=form.weight.data,
        postage=form.postage.data,
        tracking_code=form.tracking_code.data,
    )
    db.session.add(shipment)
    db.session.commit()

    app.logger.debug(
        "created %d ounce(s) shipment %d", form.weight.data, shipment.autoid
    )
    return jsonify({})

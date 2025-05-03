"""IBP flask application views."""

from datetime import date, datetime

import flask
from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    render_template_string,
    url_for,
)

import ibp

from . import flask_forms, models, warnings

app = ibp.app
session = ibp.db.session


@app.route("/")
def index():
    """Load the main web page."""
    app.logger.debug("loading index")
    return render_template("index.html")


@app.route("/view_log")
def view_log():
    """Load the server log."""
    app.logger.debug("loading log")
    for handler in ibp.log_handlers:
        handler.flush()
    log = ibp.log_stream.lines
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
            inmates, errors = models.Inmate.query_by_name(session, first, last)
        else:
            id_ = form.id_.data
            inmates, errors = models.Inmate.query_by_inmate_id(session, id_)

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
    inmate = models.Inmate.query_by_autoid(session, autoid).first_or_404()
    app.logger.debug(
        "loading view_inmate for %s inmate #%08d", inmate.jurisdiction, inmate.id
    )

    del inmate.lookups[2:]
    inmate.lookups.append(datetime.now())
    session.commit()

    inmate = models.Inmate.query_by_autoid(session, autoid).one()
    postmarkdate = flask.session.get("postmarkdate")
    comment_form = flask_forms.Comment()

    return render_template(
        "view_inmate.html",
        inmate=inmate,
        postmarkdate=postmarkdate,
        date_today=date.today(),
        comment_form=comment_form,
    )


@app.route("/add_request/<int:inmate_autoid>", methods=["POST"])
def add_request(inmate_autoid):
    """Add a request for a specific inmate."""
    inmate = models.Inmate.query_by_autoid(session, inmate_autoid).first_or_404()

    date_str = flask.request.form.get("postmarkdate", "")
    try:
        postmarkdate = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return "Please enter the USPS postmark date on the envelope.", 400

    flask.session["postmarkdate"] = postmarkdate.strftime("%Y-%m-%d")

    action = flask.request.form.get("action", "Filled")

    request = models.Request(
        action=action,
        date_postmarked=postmarkdate,
        date_processed=date.today(),
        inmate=inmate,
    )
    inmate.requests.append(request)
    session.commit()

    app.logger.debug(
        "adding request #%d with %s postmark for %s inmate #%08d",
        request.autoid,
        postmarkdate,
        inmate.jurisdiction,
        inmate.id,
    )

    request = models.Request.query.filter_by(autoid=request.autoid).one()
    rendered_request = render_template("request.html", request=request)

    return jsonify({"request_autoid": str(request.autoid), "request": rendered_request})


@app.route("/request_warnings/<int:autoid>", methods=["POST"])
def request_warnings(autoid):
    """Return request warnings."""
    inmate = models.Inmate.query_by_autoid(session, autoid).first_or_404()

    date_str = flask.request.form.get("postmarkdate", "")
    try:
        postmarkdate = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return "Please enter the USPS postmark date on the envelope.", 400

    flask.session["postmarkdate"] = postmarkdate.strftime("%Y-%m-%d")

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
    request = models.Request.query.filter_by(autoid=autoid).first_or_404()
    app.logger.debug("rendering label for request #%d", autoid)
    return render_template("request_label.xml", request=request)


@app.route("/request_info/<int:autoid>")
def request_info(autoid):
    """Return info for a request."""
    request = models.Request.query.filter_by(autoid=autoid).first_or_404()
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
    request = models.Request.query.filter_by(autoid=autoid).first_or_404()
    app.logger.debug("deleting request #%d", autoid)
    session.delete(request)
    session.commit()
    return ""


@app.route("/add_comment/<int:inmate_autoid>", methods=["POST"])
def add_comment(inmate_autoid):
    """Create a comment."""
    inmate = models.Inmate.query_by_autoid(inmate_autoid).first_or_404()
    form = flask_forms.Comment()

    if form.validate():
        comment = models.Comment.from_form(form)
        inmate.comments.append(comment)
        session.commit()

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

    comment = models.Comment.query.filter_by(autoid=autoid).first_or_404()
    app.logger.debug("deleting comment #%d", autoid)
    session.delete(comment)
    session.commit()
    return ""


@app.route("/list_units")
def list_units():
    """Return the units view."""
    app.logger.debug("loading list_units")
    return render_template("list_units.html", units=models.Unit.query)


@app.route("/view_unit/<int:autoid>", methods=["GET", "POST"])
def view_unit(autoid):
    """Return a unit view."""
    unit = models.Unit.query.filter_by(autoid=autoid).first_or_404()
    form = flask_forms.Unit()

    if flask.request.method == "GET":
        app.logger.debug("loading view_unit for %s Unit", unit.name)
        form.update_from_model(unit)

    elif form.validate():
        unit.update_from_form(form)
        session.commit()
        app.logger.debug("posting updates on %s Unit", unit.name)
        flask.flash("unit successfully updated", "alert-success")

    return render_template("view_unit.html", form=form, unit=unit)


@ibp.csrf.exempt
@app.route("/return_address", methods=["POST"])
@ibp.appkey_required
def return_address():
    """Return the IBP mailing return address."""
    app.logger.debug("loading return_address view")
    address = dict(ibp.config["address"])
    return jsonify(address)


@ibp.csrf.exempt
@app.route("/request_address/<int:autoid>", methods=["POST"])
@ibp.appkey_required
def request_address(autoid):
    """Return the a request address."""

    app.logger.debug("loading request_address view for request %d", autoid)
    request = models.Request.query.filter_by(autoid=autoid).first_or_404()

    inmate_autoid = request.inmate.autoid
    inmate = models.Inmate.query_by_autoid(session, inmate_autoid).first()

    if inmate is None:
        return "inmate is no longer in the system", 400

    unit = inmate.unit
    if unit is None:
        return "inmate is not assigned to a unit", 400

    inmate_name = (
        f"{inmate.first_name.title()} {inmate.last_name.title} #{inmate.id:08d}"
    )

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


@ibp.csrf.exempt
@app.route("/unit_autoids", methods=["POST"])
@ibp.appkey_required
def unit_autoids():
    """Return a list of unit autoids."""
    app.logger.debug("loading unit_autoids view")
    autoids = {unit.name: unit.autoid for unit in models.Unit.query}
    return jsonify(autoids)


@ibp.csrf.exempt
@app.route("/unit_address/<int:autoid>", methods=["POST"])
@ibp.appkey_required
def unit_address(autoid):
    """Return a unit address."""
    app.logger.debug("loading unit_address view for unit %d", autoid)
    unit = models.Unit.query.filter_by(autoid=autoid).first_or_404()
    name = ibp.config.get("shipping", "unit_address_name")

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


@ibp.csrf.exempt
@app.route("/request_destination/<int:autoid>", methods=["POST"])
@ibp.appkey_required
def request_destination(autoid):
    """Return the destination of a request."""
    app.logger.debug("loading request_destination view for request %d", autoid)
    request = models.Request.query.filter_by(autoid=autoid).first_or_404()

    inmate_autoid = request.inmate.autoid
    inmate = models.Inmate.query_by_autoid(session, inmate_autoid).first()

    if inmate is None:
        return "inmate is no longer in the system.", 400

    unit = inmate.unit
    if unit is None:
        msg = f"inmate '{inmate.autoid}' is not assigned to a unit"
        app.logger.debug(msg)
        return msg, 400

    return jsonify({"name": unit.name})


@ibp.csrf.exempt
@app.route("/ship_requests", methods=["POST"])
@ibp.appkey_required
def ship_requests():
    """Ship a request."""
    app.logger.debug("loading ship_requests view")

    form = flask_forms.Shipment(data=flask.request.form)
    form.csrf_token.data = form.csrf_token.current_token

    if not form.validate():
        return "form data invalid", 400

    request_ids = set(form.request_ids.data)

    def get_request_from_autoid(autoid):
        return models.Request.query.filter_by(autoid=autoid).first_or_404()

    requests = list(map(get_request_from_autoid, request_ids))

    unit_autoid = form.unit_autoid.data
    if unit_autoid:
        unit = models.Unit.query.filter_by(autoid=unit_autoid).first_or_404()
    elif requests:
        unit = requests[0].inmate.unit
    else:
        msg = "Either unit name or or one request ID must be given"
        return msg, 400

    for request in requests:
        inmate_autoid = request.inmate.autoid
        inmate = models.Inmate.query_by_autoid(session, inmate_autoid).first()

        if inmate is None:
            app.logger.debug(
                "Inmate for request %d is no longer in the system", request.autoid
            )
            return msg, 400

        if inmate.unit is None:
            app.logger.debug("Inmate for request '%d' is unassigned", request.autoid)
            return msg, 400

        if inmate.unit.name != unit.name:
            app.logger.debug("Inmates are not all assigned to '%s' unit", unit.name)
            return msg, 400

    shipment = models.Shipment(
        requests=requests,
        date_shipped=date.today(),
        unit=unit,
        weight=form.weight.data,
        postage=form.postage.data,
        tracking_code=form.tracking_code.data,
    )
    session.add(shipment)
    session.commit()

    app.logger.debug(
        "created %d ounce(s) shipment %d", form.weight.data, shipment.autoid
    )
    return jsonify({})

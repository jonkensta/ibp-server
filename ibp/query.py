"""IBP inmate query methods."""

import pymates as providers
import sqlalchemy

from . import models
from .base import config


def _build_inmate_from_response(session, response):
    """Create an Inmate instance from a provider response."""
    kwargs = dict(response)
    kwargs["id"] = int(kwargs["id"].replace("-", ""))
    kwargs["unit"] = session.query(models.Unit).filter_by(name=kwargs["unit"]).first()
    return models.Inmate(**kwargs)


def _update_inmate_from_response(inmate, session, response):
    """Update an Inmate instance from a provider response."""
    kwargs = dict(response)
    kwargs.pop("jurisdiction")
    kwargs.pop("id")
    unit_name = kwargs.pop("unit")
    kwargs["unit"] = session.query(models.Unit).filter_by(name=unit_name).first()
    inmate.update_from_kwargs(**kwargs)


def _build_or_update_inmate_from_response(session, response):
    """Build or update an Inmate instance from a response."""
    jurisdiction = response["jurisdiction"]
    id_ = response["id"]

    inmate = (
        session.query(models.Inmate)
        .filter_by(jurisdiction=jurisdiction, id=id_)
        .first()
    )

    if inmate is None:
        return _build_inmate_from_response(session, response)

    _update_inmate_from_response(inmate, session, response)
    return inmate


def inmates_by_autoid(session, autoid):
    """Query the inmate providers by autoid."""
    inmate = session.query(models.Inmate).filter_by(autoid=autoid).first()

    if inmate is None or inmate.entry_is_fresh():
        return session.query(models.Inmate).filter_by(autoid=autoid)

    timeout = config.getfloat("providers", "timeout")
    responses, _ = providers.query_by_inmate_id(
        inmate.id, jurisdictions=[inmate.jurisdiction], timeout=timeout
    )

    with session.begin_nested():
        for response in responses:
            inmate = _build_or_update_inmate_from_response(session, response)
            session.add(inmate)

    return session.query(models.Inmate).filter_by(autoid=autoid)


def inmates_by_inmate_id(session, id_):
    """Query the inmate providers by inmate id."""
    responses, errors = providers.query_by_inmate_id(id_)

    with session.begin_nested():
        for response in responses:
            inmate = _build_or_update_inmate_from_response(session, response)
            session.add(inmate)

    inmates = session.query(models.Inmate).filter_by(id=id_)
    return inmates, errors


def inmates_by_name(session, first_name, last_name):
    """Query the inmate providers by name."""
    timeout = config.getfloat("providers", "timeout")
    responses, errors = providers.query_by_name(first_name, last_name, timeout=timeout)

    with session.begin_nested():
        for response in responses:
            inmate = _build_or_update_inmate_from_response(session, response)
            session.add(inmate)

    sql_lower = sqlalchemy.func.lower
    inmates = (
        session.query(models.Inmate)
        .filter(sql_lower(models.Inmate.last_name) == sql_lower(last_name))
        .filter(models.Inmate.first_name.ilike(first_name + "%"))
    )
    return inmates, errors

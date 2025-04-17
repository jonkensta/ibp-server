"""Methods for CRUD interactions with database."""

import typing

import sqlalchemy

import pymates

from . import models


async def get_inmates_by_id(
    session: sqlalchemy.orm.Session,
    inmate_id: int,
    jurisdiction: typing.Optional[str] = None,
):
    """Get inmates matching a given inmate ID.

    :param session: `sqlalchemy` session
    :type session: `sqlalchemy` Session

    :param inmate_id: Inmate TDCJ or FBOP ID to search.
    :type inmate_id: int

    :returns: tuple of (:py:data:`inmates`, :py:data:`errors`) where

        - :py:data:`inmates` is a QueryResult for the inmate search.
        - :py:data:`errors` is a list of error strings.

    """
    jurisdictions = None if jurisdiction is None else (jurisdiction,)
    inmates, errors = await pymates.query_by_inmate_id(
        inmate_id, jurisdictions=jurisdictions
    )
    inmates = (models.Inmate.from_response(session, inmate) for inmate in inmates)

    with session.begin_nested():
        for inmate in inmates:
            assert inmate not in session
            session.merge(inmate)

    inmates = session.query(models.Inmate).filter_by(id=inmate_id).all()
    return inmates, errors


async def get_inmate_by_jurisdiction_and_id(
    session: sqlalchemy.orm.Session, jurisdiction: str, inmate_id: int
):
    errors = []
    try:
        inmate = (
            session.query(models.Inmate)
            .filter_by(jurisdiction=jurisdiction, id=inmate_id)
            .one()
        )

    except sqlalchemy.orm.exc.NoResultFound:
        inmates, errors = await get_inmates_by_id(session, inmate_id, jurisdiction)
        inmate = inmates[0] if inmates else None

    if inmate.db_entry_is_stale():
        inmates, errors = await get_inmates_by_id(session, inmate_id, jurisdiction)
        inmate = inmates[0] if inmates else None

    return inmate, errors


async def get_inmates_by_name(
    session: sqlalchemy.orm.Session, first_name: str, last_name: str
):
    """Get inmates matching a given first and last name.

    :param session: `sqlalchemy` session
    :type session: `sqlalchemy` Session

    :param first_name: Inmate first name to search.
    :type first_name: str

    :param last_name: Inmate last name to search.
    :type last_name: str

    :returns: tuple of (:py:data:`inmates`, :py:data:`errors`) where

        - :py:data:`inmates` is a QueryResult for the inmate search.
        - :py:data:`errors` is a list of error strings.

    """
    inmates, errors = await pymates.query_by_name(first_name, last_name)
    inmates = (models.Inmate.from_response(session, inmate) for inmate in inmates)

    with session.begin_nested():
        for inmate in inmates:
            assert inmate not in session
            session.merge(inmate)

    tolower = sqlalchemy.func.lower
    inmates = session.query(models.Inmate)
    inmates = inmates.filter(tolower(models.Inmate.last_name) == tolower(last_name))
    inmates = inmates.filter(models.Inmate.first_name.ilike(first_name + "%"))
    inmates = inmates.all()

    return inmates, errors


async def get_units(session: sqlalchemy.orm.Session) -> list[models.Unit]:
    """Get all units in the database."""
    return session.query(models.Unit).all()


async def get_cls_from_inmate_index(
    cls: typing.Type[models.Base],
    session: sqlalchemy.orm.Session,
    jurisdiction: str,
    inmate_id: int,
    index: int,
):
    """Get a model item from an inmate index."""
    return (
        session.query(cls)
        .filter_by(
            inmate_jurisdiction=jurisdiction,
            inmate_id=inmate_id,
            index=index,
        )
        .first()
    )


async def get_request_from_inmate_index(
    session: sqlalchemy.orm.Session, jurisdiction: str, inmate_id: int, index: int
):
    return get_cls_from_inmate_index(
        models.Request, session, jurisdiction, inmate_id, index
    )


async def get_comment_from_inmate_index(
    session: sqlalchemy.orm.Session, jurisdiction: str, inmate_id: int, index: int
):
    return get_cls_from_inmate_index(
        models.Comment, session, jurisdiction, inmate_id, index
    )

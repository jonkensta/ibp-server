"""FastAPI application."""

import typing

import nameparser

from sqlalchemy.orm import Session

import fastapi
from fastapi import Depends, FastAPI, HTTPException

from . import crud, schemas
from .database import Session as SessionLocal


app = FastAPI()


def session_context():
    """Manage a session context for a `fastapi` route."""
    session = SessionLocal()
    try:
        yield session

    finally:
        session.close()


@app.get("/inmate/{jurisdiction}/{inmate_id}", response_model=schemas.Inmate)
async def read_inmate(
    jurisdiction: schemas.Jurisdiction,
    inmate_id: int,
    session: Session = Depends(session_context),
):
    """:py:mod:`fastapi` route to handle a GET request for an inmate's info.

    This :py:mod:`fastapi` route uses the following parameters extracted from the
    endpoint URL:

    :param jurisdiction: Political system that houses the inmate.
    :type jurisdiction: str

    :param inmate_id: Inmate numeric identifier.
    :type inmate_id: int

    This is used to load the appropriate inmate.

    :returns: :py:mod:`fastapi` JSON response containing the following fields:

        - :py:data:`inmate` JSON encoding of the inmate information.

    """
    inmate, _ = await crud.get_inmate_by_jurisdiction_and_id(
        session, jurisdiction, inmate_id
    )

    if inmate is None:
        raise HTTPException(status_code=404, detail="Inmate page not found")

    return inmate


@app.get("/inmates", response_model=schemas.InmateSearchResults)
async def search_inmates(
    search: typing.Annotated[str, fastapi.Query(min_length=1, max_length=50)],
    session: Session = Depends(session_context),
):
    try:
        inmate_id = int(search.replace("-", ""))

    except ValueError:
        name = nameparser.HumanName(search)
        if not (name.first and name.last):
            raise HTTPException(400, "Need both first and last name for name search")

        inmates, errors = await crud.get_inmates_by_name(session, name.first, name.last)

    else:
        inmates, errors = await crud.get_inmates_by_id(session, inmate_id)

    return {"inmates": inmates, "errors": errors}

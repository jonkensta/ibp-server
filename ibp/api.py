"""IBP API views."""

import datetime
import logging
from typing import List, Optional

import pymates as providers
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from nameparser import HumanName
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from . import models, schemas
from .base import AsyncSessionLocal, app, config

logger = logging.getLogger(__name__)


async def get_db():
    """Dependency that provides an asynchronous SQLAlchemy session."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_api_key(request: Request):
    """
    Dependency to enforce API key authentication.
    Checks for 'X-API-Key' in request headers.
    """
    correct_appkey = config.get("server", "apikey")
    received_appkey = request.headers.get("X-API-Key")

    if not received_appkey or received_appkey != correct_appkey:
        logger.warning("Unauthorized access attempt. Received key: %s", received_appkey)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
    return received_appkey


class InmateSearchResults(BaseModel):
    """Pydantic model for inmate search results, including inmates and errors."""

    inmates: List[schemas.InmateInDB]
    errors: List[str]


@app.get("/inmates", response_model=InmateSearchResults)
async def search_inmates(
    db: AsyncSession = Depends(get_db),
    query: str = Query(..., description="Inmate name or ID."),
):
    """
    Perform an inmate search by name or inmate ID.
    Returns a list of matching inmates and any errors encountered by providers.
    """
    errors = []
    inmates_from_providers = []
    first_name_search: Optional[str] = None
    last_name_search: Optional[str] = None
    inmate_id_search: Optional[int] = None

    # Attempt to parse as name, requiring both first and last name
    name = HumanName(query)
    if name.first and name.last:
        first_name_search = name.first
        last_name_search = name.last
        logger.debug(
            "Attempting to query inmates by full name: %s %s",
            first_name_search,
            last_name_search,
        )
        responses, provider_errors = await providers.query_by_name(
            first_name_search,
            last_name_search,
            timeout=config.getfloat("providers", "timeout"),
        )
        errors.extend(provider_errors)
        inmates_from_providers.extend(responses)

    # If no name search yielded results or was attempted, try as ID
    if not inmates_from_providers:
        try:
            inmate_id_search = int(query.replace("-", ""))  # Clean ID from hyphens
            logger.debug("Attempting to query inmates by ID: %d", inmate_id_search)
            responses, provider_errors = await providers.query_by_inmate_id(
                inmate_id_search, timeout=config.getfloat("providers", "timeout")
            )
            errors.extend(provider_errors)
            inmates_from_providers.extend(responses)
        except ValueError as error:
            # Query is neither a recognizable full name nor an integer ID
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query must be an inmate name or ID.",
            ) from error

    for response in inmates_from_providers:
        jurisdiction = schemas.JurisdictionEnum(response["jurisdiction"])
        inmate_id_parsed = int(str(response["id"]).replace("-", ""))

        stmt = select(models.Inmate).where(
            models.Inmate.jurisdiction == jurisdiction,
            models.Inmate.id == inmate_id_parsed,
        )
        result = await db.execute(stmt)
        inmate = result.scalar_one_or_none()

        new_inmate_data = {
            k: v for k, v in response.items() if k not in ["jurisdiction", "id", "unit"]
        }
        new_inmate_data["jurisdiction"] = jurisdiction
        new_inmate_data["id"] = inmate_id_parsed

        unit_name = response.get("unit")
        if unit_name:
            unit_stmt = select(models.Unit).where(models.Unit.name == unit_name)
            unit_result = await db.execute(unit_stmt)
            unit = unit_result.scalar_one_or_none()
            if unit:
                new_inmate_data["unit_id"] = unit.autoid
            else:
                logger.warning(
                    "Unit '%s' not found for inmate %s %s",
                    unit_name,
                    jurisdiction,
                    inmate_id_parsed,
                )

        if inmate is None:
            new_inmate = models.Inmate(**new_inmate_data)
            db.add(new_inmate)
            logger.debug("Created new inmate: %s", new_inmate)
        else:
            inmate.update_from_kwargs(**new_inmate_data)
            logger.debug("Updated existing inmate: %s", inmate)

    await db.commit()

    # Query inmates from DB based on the search criteria, not just provider results
    query_stmt = select(models.Inmate)
    if first_name_search and last_name_search:
        query_stmt = query_stmt.where(
            func.lower(models.Inmate.first_name) == func.lower(first_name_search),
            func.lower(models.Inmate.last_name) == func.lower(last_name_search),
        )
    elif inmate_id_search is not None:
        query_stmt = query_stmt.where(models.Inmate.id == inmate_id_search)
    else:
        # This case should ideally not be reached if query validation is strict
        # but added for robustness
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid search query provided after provider lookup.",
        )

    result = await db.execute(query_stmt)
    inmates = result.scalars().all()

    # Return both inmates and errors
    return InmateSearchResults(inmates=inmates, errors=errors)


@app.get("/inmates/{jurisdiction}/{inmate_id}", response_model=schemas.InmateInDB)
async def get_inmate(
    jurisdiction: schemas.JurisdictionEnum,
    inmate_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single inmate by jurisdiction and inmate ID."""
    logger.debug("Loading inmate view for %s inmate #%08d", jurisdiction, inmate_id)

    stmt = select(models.Inmate).where(
        models.Inmate.jurisdiction == jurisdiction, models.Inmate.id == inmate_id
    )
    result = await db.execute(stmt)
    inmate = result.scalar_one_or_none()

    if inmate is None or not inmate.entry_is_fresh():
        logger.debug(
            "Inmate not found or not fresh, querying providers for %s inmate #%08d",
            jurisdiction,
            inmate_id,
        )
        responses, provider_errors = await providers.query_by_inmate_id(
            inmate_id,
            jurisdictions=[jurisdiction.value],
            timeout=config.getfloat("providers", "timeout"),
        )

        if provider_errors:
            logger.warning("Provider errors during inmate refresh: %s", provider_errors)

        if responses:
            response = responses[0]
            jurisdiction_parsed = schemas.JurisdictionEnum(response["jurisdiction"])
            inmate_id_parsed = int(str(response["id"]).replace("-", ""))

            new_inmate_data = {
                k: v
                for k, v in response.items()
                if k not in ["jurisdiction", "id", "unit"]
            }
            new_inmate_data["jurisdiction"] = jurisdiction_parsed
            new_inmate_data["id"] = inmate_id_parsed

            unit_name = response.get("unit")
            if unit_name:
                unit_stmt = select(models.Unit).where(models.Unit.name == unit_name)
                unit_result = await db.execute(unit_stmt)
                unit = unit_result.scalar_one_or_none()
                if unit:
                    new_inmate_data["unit_id"] = unit.autoid

            if inmate is None:
                inmate = models.Inmate(**new_inmate_data)
                db.add(inmate)
                logger.debug("Created new inmate from provider: %s", inmate)
            else:
                inmate.update_from_kwargs(**new_inmate_data)
                logger.debug("Updated existing inmate from provider: %s", inmate)

            inmate.lookups.append(datetime.datetime.now())
            await db.commit()

            result = await db.execute(stmt)
            inmate = result.scalar_one_or_none()

    if inmate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inmate not found."
        )

    return inmate


@app.post(
    "/inmates/{jurisdiction}/{inmate_id}/requests", response_model=schemas.RequestInDB
)
async def add_request(
    jurisdiction: schemas.JurisdictionEnum,
    inmate_id: int,
    request_data: schemas.RequestCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Add a new request for a specific inmate.
    """
    inmate_stmt = select(models.Inmate).where(
        models.Inmate.jurisdiction == jurisdiction, models.Inmate.id == inmate_id
    )
    result = await db.execute(inmate_stmt)
    inmate = result.scalar_one_or_none()

    if inmate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inmate not found."
        )

    max_index_stmt = select(func.max(models.Request.index)).where(
        models.Request.inmate_jurisdiction == jurisdiction,
        models.Request.inmate_id == inmate_id,
    )
    max_index_result = await db.execute(max_index_stmt)
    max_index = max_index_result.scalar_one_or_none()
    next_index = (max_index or 0) + 1

    new_request = models.Request(
        **request_data.model_dump(),
        inmate_jurisdiction=jurisdiction,
        inmate_id=inmate_id,
        index=next_index,
    )
    db.add(new_request)
    await db.commit()
    await db.refresh(new_request)

    logger.debug(
        "Adding request #%d with %s postmark for %s inmate #%08d",
        new_request.index,
        new_request.date_postmarked,
        inmate.jurisdiction,
        inmate.id,
    )

    return new_request


@app.delete(
    "/requests/{jurisdiction}/{inmate_id}/{request_index}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_request(
    jurisdiction: schemas.JurisdictionEnum,
    inmate_id: int,
    request_index: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a request by its composite primary key.
    """
    stmt = select(models.Request).where(
        models.Request.inmate_jurisdiction == jurisdiction,
        models.Request.inmate_id == inmate_id,
        models.Request.index == request_index,
    )
    result = await db.execute(stmt)
    request_to_delete = result.scalar_one_or_none()

    if request_to_delete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found."
        )

    logger.debug(
        "Deleting request #%d for inmate %s %d", request_index, jurisdiction, inmate_id
    )
    await db.delete(request_to_delete)
    await db.commit()


@app.post(
    "/inmates/{jurisdiction}/{inmate_id}/comments", response_model=schemas.CommentInDB
)
async def add_comment(
    jurisdiction: schemas.JurisdictionEnum,
    inmate_id: int,
    comment_data: schemas.CommentCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Add a new comment for a specific inmate.
    """
    inmate_stmt = select(models.Inmate).where(
        models.Inmate.jurisdiction == jurisdiction, models.Inmate.id == inmate_id
    )
    result = await db.execute(inmate_stmt)
    inmate = result.scalar_one_or_none()

    if inmate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inmate not found."
        )

    max_index_stmt = select(func.max(models.Comment.index)).where(
        models.Comment.inmate_jurisdiction == jurisdiction,
        models.Comment.inmate_id == inmate_id,
    )
    max_index_result = await db.execute(max_index_stmt)
    max_index = max_index_result.scalar_one_or_none()
    next_index = (max_index or 0) + 1

    new_comment = models.Comment(
        **comment_data.model_dump(),
        inmate_jurisdiction=jurisdiction,
        inmate_id=inmate_id,
        index=next_index,
    )
    db.add(new_comment)
    await db.commit()
    await db.refresh(new_comment)

    logger.debug(
        "Adding comment #%d for %s inmate #%08d",
        new_comment.index,
        inmate.jurisdiction,
        inmate.id,
    )

    return new_comment


@app.delete(
    "/comments/{jurisdiction}/{inmate_id}/{comment_index}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_comment(
    jurisdiction: schemas.JurisdictionEnum,
    inmate_id: int,
    comment_index: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a comment by its composite primary key.
    """
    stmt = select(models.Comment).where(
        models.Comment.inmate_jurisdiction == jurisdiction,
        models.Comment.inmate_id == inmate_id,
        models.Comment.index == comment_index,
    )
    result = await db.execute(stmt)
    comment_to_delete = result.scalar_one_or_none()

    if comment_to_delete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found."
        )

    logger.debug(
        "Deleting comment #%d for inmate %s %d", comment_index, jurisdiction, inmate_id
    )
    await db.delete(comment_to_delete)
    await db.commit()


@app.get("/units", response_model=List[schemas.UnitInDB])
async def get_all_units(db: AsyncSession = Depends(get_db)):
    """
    Retrieve a list of all prison units.
    """
    logger.debug("Retrieving all units")
    result = await db.execute(select(models.Unit))
    units = result.scalars().all()
    return units


@app.get("/units/{unit_id}", response_model=schemas.UnitInDB)
async def get_unit(unit_id: int, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a single unit by its ID.
    """
    logger.debug("Retrieving unit with ID %d", unit_id)
    stmt = select(models.Unit).where(models.Unit.autoid == unit_id)
    result = await db.execute(stmt)
    unit = result.scalar_one_or_none()

    if unit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found."
        )
    return unit


@app.put("/units/{unit_id}", response_model=schemas.UnitInDB)
async def update_unit(
    unit_id: int, unit_data: schemas.UnitUpdate, db: AsyncSession = Depends(get_db)
):
    """
    Update an existing unit by its ID.
    """
    logger.debug("Updating unit with ID %d", unit_id)
    stmt = select(models.Unit).where(models.Unit.autoid == unit_id)
    result = await db.execute(stmt)
    unit = result.scalar_one_or_none()

    if unit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found."
        )

    for field, value in unit_data.model_dump(exclude_unset=True).items():
        setattr(unit, field, value)

    await db.commit()
    await db.refresh(unit)
    logger.debug("Updated unit: %s", unit.name)
    return unit


@app.get("/address/return", dependencies=[Depends(get_api_key)])
async def get_return_address():
    """
    Return the IBP mailing return address.
    Requires API key authentication (X-API-Key header).
    """
    logger.debug("Retrieving return address")
    address = dict(config["address"])
    return address


@app.get("/requests/{request_id}/address", dependencies=[Depends(get_api_key)])
async def get_request_address(request_id: int, db: AsyncSession = Depends(get_db)):
    """
    Return the address for a specific request.
    Requires API key authentication (X-API-Key header).
    """
    logger.debug("Retrieving address for request %d", request_id)
    stmt = select(models.Request).where(models.Request.autoid == request_id)
    result = await db.execute(stmt)
    request = result.scalar_one_or_none()

    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        )

    inmate = request.inmate
    if inmate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request does not have an associated inmate",
        )

    unit = inmate.unit
    if unit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inmate is not assigned to a unit",
        )

    first_name = inmate.first_name.title() if inmate.first_name else ""
    last_name = inmate.last_name.title() if inmate.last_name else ""
    inmate_name = f"{first_name} {last_name} #{inmate.id:08d}"

    return {
        "name": inmate_name,
        "street1": unit.street1,
        "street2": unit.street2,
        "city": unit.city,
        "state": unit.state,
        "zipcode": unit.zipcode,
    }


@app.get("/requests/{request_id}/destination", dependencies=[Depends(get_api_key)])
async def get_request_destination(request_id: int, db: AsyncSession = Depends(get_db)):
    """
    Return the destination unit name of a request.
    Requires API key authentication (X-API-Key header).
    """
    logger.debug("Retrieving destination for request %d", request_id)
    stmt = select(models.Request).where(models.Request.autoid == request_id)
    result = await db.execute(stmt)
    request = result.scalar_one_or_none()

    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        )

    inmate = request.inmate
    if inmate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inmate for request is no longer in the system.",
        )

    unit = inmate.unit
    if unit is None:
        msg = f"Inmate '{inmate.id}' is not assigned to a unit"
        logger.debug(msg)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)

    return {"name": unit.name}

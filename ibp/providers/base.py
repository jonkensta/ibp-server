"""IBP inmate search utility."""

import functools
import logging
import typing

from . import fbop, tdcj

Jurisdiction = typing.Literal["Texas", "Federal"]

PROVIDERS: dict[Jurisdiction, typing.Any] = {
    "Texas": tdcj,
    "Federal": fbop,
}

LOGGERS: dict[Jurisdiction, logging.Logger] = {
    "Texas": tdcj.LOGGER,
    "Federal": fbop.LOGGER,
}

QueryResult = tdcj.QueryResult | fbop.QueryResult


def wrap_query(wrapped):
    """query function."""

    @functools.wraps(wrapped)
    async def wrapper(
        *args,
        jurisdictions: typing.Optional[typing.Iterable[Jurisdiction]] = None,
        timeout: typing.Optional[float] = None,
    ):
        if jurisdictions is None:
            jurisdictions = PROVIDERS.keys()

        jurisdictions = list(set(jurisdictions))
        for jurisdiction in jurisdictions:
            if jurisdiction not in PROVIDERS:
                raise ValueError(f"Invalid jurisdiction '{jurisdiction}' given.")

        inmates = []
        errors = []

        for jurisdiction in jurisdictions:
            logger = LOGGERS[jurisdiction]
            try:
                result = await wrapped(*args, jurisdiction, timeout=timeout)
                inmates.extend(result)
            except Exception as error:  # pylint: disable=broad-exception-caught
                error_name = error.__class__.__name__
                message = f"Query returned '{error_name}: {error}'."
                logger.error(message)
                errors.append(error)

        return inmates, errors

    return wrapper


@wrap_query
async def query_by_inmate_id(
    inmate_id: str | int,
    jurisdiction: Jurisdiction,
    timeout: typing.Optional[float] = 10.0,
):
    """Query jurisdictions with an inmate ID."""
    provider = PROVIDERS[jurisdiction]
    return await provider.query_by_inmate_id(inmate_id=inmate_id, timeout=timeout)


@wrap_query
async def query_by_name(
    first: str,
    last: str,
    jurisdiction: Jurisdiction,
    timeout: typing.Optional[float] = 10.0,
):
    """Query jurisdictions with an inmate name."""
    provider = PROVIDERS[jurisdiction]
    return await provider.query_by_name(first=first, last=last, timeout=timeout)

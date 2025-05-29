"""FBOP inmate query implementation."""

import asyncio
import datetime
import json
import logging
import typing

from .decorators import log_query_by_inmate_id, log_query_by_name

LOGGER = logging.getLogger("PROVIDERS.FBOP")

URL = "https://www.bop.gov/PublicInfo/execute/inmateloc"

TEXAS_UNITS = {
    "BAS",
    "BML",
    "BMM",
    "BMP",
    "BSC",
    "BIG",
    "BRY",
    "CRW",
    "EDN",
    "FTW",
    "DAL",
    "HOU",
    "LAT",
    "REE",
    "RVS",
    "SEA",
    "TEX",
    "TRV",
}


def format_inmate_id(inmate_id: typing.Union[str, int]) -> str:
    """Format FBOP inmate IDs."""
    try:
        inmate_id = int(str(inmate_id).replace("-", ""))
    except ValueError as exc:
        raise ValueError("inmate ID must be a number") from exc

    inmate_id = f"{inmate_id:08d}"

    if len(inmate_id) != 8:
        raise ValueError("inmate ID must be less than 8 digits")

    return inmate_id[0:5] + "-" + inmate_id[5:8]


class QueryResult(typing.TypedDict):
    """Result of a FBOP query."""

    id: str
    jurisdiction: typing.Literal["Federal"]

    first_name: str
    last_name: str

    unit: str

    race: typing.Optional[str]
    sex: typing.Optional[str]

    url: typing.Literal[None]
    release: typing.Optional[str | datetime.date]

    datetime_fetched: datetime.datetime


async def _curl_search_url(
    last_name: str = "",
    first_name: str = "",
    inmate_id: str = "",
    timeout: typing.Optional[float] = None,
) -> dict:
    """Query FBOP using a curl subprocess call."""

    command = ["curl", "-G", "-f", "-s"]

    command.append(URL)

    params = {
        "age": "",
        "nameMiddle": "",
        "output": "json",
        "race": "",
        "sex": "",
        "todo": "query",
        "nameLast": last_name,
        "nameFirst": first_name,
        "inmateNum": inmate_id,
    }

    for key, value in params.items():
        command.append("--data-urlencode")
        command.append(f"{key}={value}")

    if timeout is not None:
        command.extend(["--max-time", str(float(timeout))])

    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    try:
        stdout, *_ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError as error:
        if process.returncode is None:  # Check if process is still running
            process.terminate()
            await process.wait()  # Wait for the process to actually terminate
        message = f"curl command timed out after {timeout} seconds."
        raise TimeoutError(message) from error

    if process.returncode != 0:
        message = f"curl command failed with exit code {process.returncode}"
        raise RuntimeError(message)

    return json.loads(stdout.decode("utf-8").strip())


async def _query(
    last_name: str = "",
    first_name: str = "",
    inmate_id: str = "",
    timeout: typing.Optional[float] = None,
) -> list[QueryResult]:
    """Private helper for querying FBOP."""

    data = await _curl_search_url(last_name, first_name, inmate_id, timeout)

    try:
        data = data["InmateLocator"]
    except KeyError:
        return []

    def data_to_inmate(entry):
        def parse_date(datestr):
            return datetime.datetime.strptime(datestr, "%m/%d/%Y").date()

        try:
            actual_release = parse_date(entry["actRelDate"])
        except ValueError:
            LOGGER.debug(
                "Failed to parse actual release date '%s'", entry["actRelDate"]
            )
            actual_release = None

        try:
            projected_release = parse_date(entry["projRelDate"])
        except ValueError:
            LOGGER.debug(
                "Failed to parse projected release date '%s'", entry["projRelDate"]
            )
            projected_release = None

        release = (
            actual_release
            or projected_release
            or entry["projRelDate"]
            or entry["actRelDate"]
            or None
        )

        if release is None:
            LOGGER.debug("Failed to retrieve any release date.")

        return QueryResult(
            id=entry["inmateNum"],
            jurisdiction="Federal",
            first_name=entry["nameFirst"],
            last_name=entry["nameLast"],
            unit=entry["faclCode"],
            race=entry.get("race", None),
            sex=entry.get("gender", None),
            url=None,
            release=release,
            datetime_fetched=datetime.datetime.now(),
        )

    inmates = map(data_to_inmate, data)

    def is_in_texas(inmate):
        return inmate["unit"] in TEXAS_UNITS

    inmates = filter(is_in_texas, inmates)  # type: ignore

    def has_not_been_released(inmate):
        try:
            released = datetime.date.today() >= inmate["release"]
        except TypeError:
            # release can be a string for life sentence, etc
            released = False

        return not released

    inmates = filter(has_not_been_released, inmates)  # type: ignore

    return list(inmates)


@log_query_by_name(LOGGER)
async def query_by_name(first, last, **kwargs):
    """Query the FBOP database with an inmate name."""
    return await _query(first_name=first, last_name=last, **kwargs)


@log_query_by_inmate_id(LOGGER)
async def query_by_inmate_id(inmate_id: str | int, **kwargs):
    """Query the FBOP database with an inmate id."""
    try:
        inmate_id = format_inmate_id(inmate_id)
    except ValueError as exc:
        msg = f"'{inmate_id}' is not a valid Texas inmate number"
        raise ValueError(msg) from exc

    return await _query(inmate_id=inmate_id, **kwargs)

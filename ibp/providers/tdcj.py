"""TDCJ inmate query implementation."""

import asyncio
import datetime
import logging
import typing
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from nameparser import HumanName

from .decorators import log_query_by_inmate_id, log_query_by_name

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://inmate.tdcj.texas.gov"
SEARCH_PATH = "InmateSearch/search.action"
SEARCH_URL = urljoin(BASE_URL, SEARCH_PATH)


def format_inmate_id(inmate_id: typing.Union[int, str]) -> str:
    """Format a TDCJ inmate ID."""
    inmate_id = int(inmate_id)
    return f"{inmate_id:08d}"


class QueryResult(typing.TypedDict):
    """Result of a TDCJ query."""

    id: str
    jurisdiction: typing.Literal["Texas"]

    first_name: str
    last_name: str

    unit: str

    race: typing.Optional[str]
    sex: typing.Optional[str]

    url: str
    release: typing.Optional[str | datetime.date]

    datetime_fetched: datetime.datetime


async def _curl_search_url(
    last_name: str = "",
    first_name: str = "",
    inmate_id: str = "",
    timeout: float | None = None,
):
    command = [
        "curl",
        "--ipv4",
        "-d",
        "btnSearch=Search",
        "-d",
        "gender=ALL",
        "-d",
        "race=ALL",
        "-d",
        f"tdcj={inmate_id}",
        "-d",
        f"lastName={last_name}",
        "-d",
        f"firstName={first_name}",
        "-d",
        "page=index",
        "-d",
        "sid=",
        SEARCH_URL,
    ]

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

    return stdout


async def _query(  # pylint: disable=too-many-locals
    last_name: str = "",
    first_name: str = "",
    inmate_id: str = "",
    timeout: float | None = None,
) -> list[QueryResult]:
    """Private helper for querying TDCJ."""

    html = await _curl_search_url(last_name, first_name, inmate_id, timeout)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"class": "tdcj_table"})

    if table is None or not isinstance(table, Tag):
        return []

    for linebreak in table.find_all("br"):
        linebreak.replace_with(" ")

    rows = iter(table.find_all("tr"))

    try:
        next(rows)  # First row contains nothing.
        header = next(rows)
    except StopIteration:
        return []

    # Second row contains the column names.
    keys = [ele.text.strip() for ele in header.find_all("th")]

    def row_to_entry(row):
        values = [ele.get_text().strip() for ele in row.find_all("td")]
        if not values:
            return None
        entry = dict(zip(keys, values))
        anchor = row.find("a")
        entry["href"] = anchor.get("href") if anchor is not None else None
        return entry

    entries = filter(None, map(row_to_entry, rows))

    def entry_to_inmate(entry: dict):
        """Convert TDCJ inmate entry to inmate dictionary."""

        name = HumanName(entry.get("Name", ""))

        def build_url(href):
            return urljoin(BASE_URL, href)

        url = build_url(str(entry["href"])) if "href" in entry else None

        def parse_release_date(release):
            return datetime.datetime.strptime(release, "%Y-%m-%d").date()

        release = entry["Projected Release Date"]

        try:
            release = parse_release_date(release)
        except ValueError:
            LOGGER.debug("Failed to parse release date '%s'", release)

        return QueryResult(
            id=entry["TDCJ Number"],
            jurisdiction="Texas",
            first_name=name.first,
            last_name=name.last,
            unit=entry["Unit of Assignment"],
            race=entry.get("Race", None),
            sex=entry.get("Gender", None),
            url=url,
            release=release,
            datetime_fetched=datetime.datetime.now(),
        )

    return list(map(entry_to_inmate, entries))


@log_query_by_name(LOGGER)
async def query_by_name(first, last, **kwargs):
    """Query the TDCJ database with an inmate name."""
    return await _query(first_name=first, last_name=last, **kwargs)


@log_query_by_inmate_id(LOGGER)
async def query_by_inmate_id(inmate_id: str | int, **kwargs):
    """Query the TDCJ database with an inmate id."""
    try:
        inmate_id = format_inmate_id(inmate_id)
    except ValueError as exc:
        msg = f"'{inmate_id}' is not a valid Texas inmate number"
        raise ValueError(msg) from exc

    return await _query(inmate_id=inmate_id, **kwargs)

"""Methods for generating warnings for inmates and requests."""

import logging
from datetime import date, datetime, timedelta

from .base import config

logger = logging.getLogger("warnings")


def _inmate_entry_age_warning(inmate_):
    """Return an entry age warning for an inmate if any."""
    jurisdiction = inmate_.jurisdiction
    id_ = inmate_.id

    try:
        age = datetime.now() - inmate_.datetime_fetched
    except TypeError:
        msg = f"Data entry for {jurisdiction} inmate #{id_:08d} has never been verified"
        logger.debug(msg)
        return msg

    inmates_cache_ttl = config.getint("warnings", "inmates_cache_ttl")
    ttl = timedelta(hours=inmates_cache_ttl)
    if age > ttl:
        msg = (
            f"Data entry for {jurisdiction} inmate #{id_:08d} is {age.days} day(s) old"
        )
        logger.debug(msg)
        return msg

    return None


def _inmate_release_warning(inmate_):
    """Return a release warning for an inmate if any."""
    try:
        to_release = inmate_.release - date.today()
    except TypeError:
        return None

    days = config.getint("warnings", "min_release_timedelta")
    min_timedelta = timedelta(days=days)

    jurisdiction = inmate_.jurisdiction
    id_ = inmate_.id

    if to_release <= timedelta(0):
        msg = f"{jurisdiction} inmate #{id_:08d} is marked as released"
        logger.debug(msg)
        return msg

    if to_release <= min_timedelta:
        msg = (
            f"{jurisdiction} inmate #{id_:08d} is {to_release.days} days from release."
        )
        logger.debug(msg)
        return msg

    return None


def inmate(inmate_):
    """Generate warnings about a given inmate."""
    messages = []
    messages.append(_inmate_entry_age_warning(inmate_))
    messages.append(_inmate_release_warning(inmate_))
    messages = filter(None, messages)
    return messages


def request(inmate_, postmarkdate):
    """Generate warnings about a given request."""
    messages = []

    def was_filled(request_):
        return request_.action == "Filled"

    requests = filter(was_filled, inmate_.requests)

    try:
        last_filled_request = next(requests)
    except StopIteration:
        return messages

    td = postmarkdate - last_filled_request.date_postmarked
    days = config.getint("warnings", "min_postmark_timedelta")
    min_td = timedelta(days=days)

    msg = None

    if td.days < 0:
        msg = "There is a request with a postmark after this one."
        messages.append(msg)
    elif td.days == 0:
        msg = "No time has transpired since the last postmark."
        messages.append(msg)
    elif td < min_td:
        msg = f"Only {td.days} days since last postmark."
        messages.append(msg)

    if msg is not None:
        logger.debug(msg)

    return messages

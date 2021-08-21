import logging
from datetime import date, datetime, timedelta

import ibp

logger = logging.getLogger("warnings")


def _inmate_entry_age_warning(inmate):
    try:
        age = datetime.now() - inmate.datetime_fetched
    except TypeError:
        msg = "Data entry for {} inmate #{:08d} has never been verified".format(
            inmate.jurisdiction, inmate.id
        )
        logger.debug(msg)
        return msg

    inmates_cache_ttl = ibp.config.getint("warnings", "inmates_cache_ttl")
    ttl = timedelta(hours=inmates_cache_ttl)
    if age > ttl:
        msg = "Data entry for {} inmate #{:08d} is {} day(s) old".format(
            inmate.jurisdiction, inmate.id, age.days
        )
        logger.debug(msg)
        return msg
    else:
        return None


def _inmate_release_warning(inmate):
    try:
        to_release = inmate.release - date.today()
    except TypeError:
        return None

    days = ibp.config.getint("warnings", "min_release_timedelta")
    min_timedelta = timedelta(days=days)

    if to_release <= timedelta(0):
        msg = "{} inmate #{:08d} is marked as released".format(
            inmate.jurisdiction, inmate.id
        )
        logger.debug(msg)
        return msg
    elif to_release <= min_timedelta:
        msg = "{} inmate #{:08d} is {} days from release.".format(
            inmate.jurisdiction, inmate.id, to_release.days
        )
        logger.debug(msg)
        return msg
    else:
        return None


def inmate(inmate):
    messages = []
    messages.append(_inmate_entry_age_warning(inmate))
    messages.append(_inmate_release_warning(inmate))
    messages = filter(None, messages)
    return messages


def request(inmate, postmarkdate):
    messages = []

    def was_filled(request):
        return request.action == "Filled"

    requests = filter(was_filled, inmate.requests)

    try:
        last_filled_request = next(requests)
    except StopIteration:
        return messages

    td = postmarkdate - last_filled_request.date_postmarked
    days = ibp.config.getint("warnings", "min_postmark_timedelta")
    min_td = timedelta(days=days)

    msg = None

    if td.days < 0:
        msg = "There is a request with a postmark after this one."
        messages.append(msg)
    elif td.days == 0:
        msg = "No time has transpired since the last postmark."
        messages.append(msg)
    elif td < min_td:
        msg = "Only {} days since last postmark.".format(td.days)
        messages.append(msg)

    if msg is not None:
        logger.debug(msg)

    return messages

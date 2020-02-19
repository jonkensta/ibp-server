"""Helpers for generating warnings for inmates and requests."""


from datetime import date, datetime, timedelta

from .base import config


def _inmate_entry_age_warnings(inmate):
    try:
        age = datetime.now() - inmate.datetime_fetched
    except TypeError:
        yield (
            f"Data entry for {inmate.jurisdiction} inmate #{inmate.id:08d}"
            f" has never been verified."
        )
    else:
        inmates_cache_ttl = config.getint("warnings", "inmates_cache_ttl")
        ttl = timedelta(hours=inmates_cache_ttl)
        if age > ttl:
            yield (
                f"Data entry for {inmate.jurisdiction} inmate #{inmate.id:08d}"
                f" is {age.days} old."
            )


def _inmate_release_warnings(inmate):
    try:
        to_release = inmate.release - date.today()
    except TypeError:
        return

    min_release_days = config.getint("warnings", "min_release_timedelta")
    min_timedelta = timedelta(days=min_release_days)

    if to_release <= timedelta(0):
        yield f"{inmate.jurisdiction} inmate #{inmate.id:08d} is marked as released"

    elif to_release <= min_timedelta:
        yield (
            f"{inmate.jurisdiction} inmate #{inmate.id:08d} is "
            f" {to_release.days} days from release."
        )


def for_inmate(inmate):
    yield from _inmate_entry_age_warnings(inmate)
    yield from _inmate_release_warnings(inmate)


def for_request(inmate, postmarkdate):
    def was_filled(req):
        return req.action == "Filled"

    requests = filter(was_filled, inmate.requests)

    try:
        last_filled_request = next(requests)
    except StopIteration:
        return

    delta = postmarkdate - last_filled_request.date_postmarked
    days = ibp.config.getint("warnings", "min_postmark_timedelta")
    min_delta = timedelta(days=days)

    if delta.days < 0:
        yield "There is a request with a postmark after this one."
    elif delta.days == 0:
        yield "No time has transpired since the last postmark."
    elif delta < min_delta:
        yield f"Only {delta.days} days since last postmark."

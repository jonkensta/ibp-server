"""Helpers for generating warnings for inmates and requests."""


from datetime import date, datetime, timedelta

from .base import config


def inmate_entry_age(inmate):
    """Get a warning for the age of an inmate's data entry."""
    try:
        age = datetime.now() - inmate.datetime_fetched
    except TypeError:
        return (
            f"Data entry for {inmate.jurisdiction} inmate #{inmate.id:08d}"
            f" has never been verified."
        )
    else:
        inmates_cache_ttl = config.getint("warnings", "inmates_cache_ttl")
        ttl = timedelta(hours=inmates_cache_ttl)
        if age > ttl:
            return (
                f"Data entry for {inmate.jurisdiction} inmate #{inmate.id:08d}"
                f" is {age.days} old."
            )

    return None


def inmate_pending_release(inmate):
    """Get a warning for an inmate's pending release date."""
    try:
        to_release = inmate.release - date.today()
    except TypeError:
        return None

    min_release_days = config.getint("warnings", "min_release_timedelta")
    min_timedelta = timedelta(days=min_release_days)

    if to_release <= timedelta(0):
        return f"{inmate.jurisdiction} inmate #{inmate.id:08d} is marked as released"

    if to_release <= min_timedelta:
        return (
            f"{inmate.jurisdiction} inmate #{inmate.id:08d} is "
            f" {to_release.days} days from release."
        )

    return None

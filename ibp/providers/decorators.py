"""Utility decorators for query functions."""

import functools
import logging


def log_query_by_inmate_id(logger: logging.Logger):
    """Log the results of an ID query."""

    def decorator(wrapped):
        @functools.wraps(wrapped)
        async def wrapper(inmate_id, **kwargs):
            logger.debug("Querying with ID '%s'", inmate_id)
            matches = await wrapped(inmate_id, **kwargs)

            if not matches:
                logger.debug("No results returned")
                return []

            if len(matches) > 1:
                logger.error("Multiple results were returned for an ID query")
                return matches

            logger.debug("A single result was returned")
            return matches

        return wrapper

    return decorator


def log_query_by_name(logger: logging.Logger):
    """Log the results of a name query."""

    def decorator(wrapped):
        @functools.wraps(wrapped)
        async def wrapper(first, last, **kwargs):
            logger.debug("Querying with name '%s, %s'", last, first)
            matches = await wrapped(first, last, **kwargs)

            if not matches:
                logger.debug("No results were returned")
                return []

            for inmate in matches:
                logger.debug(
                    "%s, %s #%s: MATCHES",
                    inmate["last_name"],
                    inmate["first_name"],
                    inmate["id"],
                )

            logger.debug("%d result(s) returned", len(matches))
            return matches

        return wrapper

    return decorator

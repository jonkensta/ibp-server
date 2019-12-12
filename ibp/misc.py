"""Miscellaneous utility functions."""

import itertools


def available_indices(items):
    """Iterate through indices of given items."""
    used_indices = set(item.index for item in items)
    for index in itertools.count():
        if index not in used_indices:
            yield index

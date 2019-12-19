"""Miscellaneous utility functions."""

import itertools


def get_next_available_index(items):
    """Get next available index from a set of items."""
    used_indices = sorted(item.index for item in items)
    enumerated = itertools.zip_longest(itertools.count(), used_indices)
    return next(
        index
        for index, used_index in enumerated
        if used_index is None or index != used_index
    )

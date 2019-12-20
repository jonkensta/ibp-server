"""Miscellaneous utility functions."""

import typing
import itertools


def get_next_available_index(indices: typing.List[int]) -> int:
    """Get next available index from an iterable of indices."""
    used_indices = sorted(indices)
    enumerated = itertools.zip_longest(itertools.count(), used_indices)
    return next(
        index
        for index, used_index in enumerated
        if used_index is None or index != used_index
    )

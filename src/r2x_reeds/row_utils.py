"""Utilities for working with data rows in various formats (dict, SimpleNamespace, etc).

This module provides helper functions for extracting fields from rows that may be
represented as either dictionaries or object instances. It eliminates the repetitive
pattern found throughout getters.py:

    getattr(row, "field", None) if hasattr(row, "__dict__") else row.get("field")

which is duplicated approximately 38 times across the codebase.
"""

from __future__ import annotations

from typing import Any, TypeVar, overload

T = TypeVar("T")


@overload
def get_row_field(row: Any, field: str) -> Any:
    """Extract field from row, returning None if missing."""


@overload
def get_row_field(row: Any, field: str, default: T) -> T | Any:
    """Extract field from row, returning default if missing."""


def get_row_field(row: Any, field: str, default: Any = None) -> Any:
    """Extract field from row supporting both dict and SimpleNamespace/objects.

    Handles both dictionary and object attribute access transparently.

    Parameters
    ----------
    row : Any
        Data row (dict, SimpleNamespace, or object with __dict__)
    field : str
        Field/attribute name to extract
    default : Any, optional
        Default value if field missing, by default None

    Returns
    -------
    Any
        Field value or default

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> row_dict = {"name": "test", "value": 42}
    >>> get_row_field(row_dict, "name")
    'test'
    >>> get_row_field(row_dict, "missing", "default")
    'default'

    >>> row_ns = SimpleNamespace(name="test", value=42)
    >>> get_row_field(row_ns, "name")
    'test'
    >>> get_row_field(row_ns, "missing", "default")
    'default'
    """
    if hasattr(row, "__dict__"):
        # Object attribute access for SimpleNamespace, dataclasses, custom objects
        return getattr(row, field, default)
    # Dictionary access
    return row.get(field, default)


def has_row_field(row: Any, field: str) -> bool:
    """Check if row has a field/attribute.

    Parameters
    ----------
    row : Any
        Data row (dict, SimpleNamespace, or object)
    field : str
        Field/attribute name to check

    Returns
    -------
    bool
        True if field exists, False otherwise

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> row_dict = {"name": "test", "value": None}
    >>> has_row_field(row_dict, "name")
    True
    >>> has_row_field(row_dict, "missing")
    False

    >>> row_ns = SimpleNamespace(name="test", value=None)
    >>> has_row_field(row_ns, "name")
    True
    >>> has_row_field(row_ns, "missing")
    False
    """
    if hasattr(row, "__dict__"):
        # Object attribute check
        return hasattr(row, field)
    # Dictionary key check
    return field in row

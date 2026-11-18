"""Immutable local Bronze storage and the object-store boundary."""

from .contracts import ObjectStore
from .local import LocalObjectStore

__all__ = ["LocalObjectStore", "ObjectStore"]

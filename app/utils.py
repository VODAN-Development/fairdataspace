"""Shared utility functions for the fairdataspace application."""

import hashlib


def get_uri_hash(uri: str) -> str:
    """Generate MD5 hash of URI for use as identifier.

    Args:
        uri: The URI to hash.

    Returns:
        Hex digest of the MD5 hash.
    """
    return hashlib.md5(uri.encode()).hexdigest()

"""Shared error for E21 Realtime Control Plane contracts.

A ``ValueError`` subtype so callers can catch either ``ControlContractError`` or the
broader ``ValueError`` (consistent with the role/skill loaders). Raised whenever a
RuntimeEvent / RuntimeCommand / RuntimeCheckpoint / Permission fails contract
validation — an invalid object must never be constructed or published.
"""
from __future__ import annotations


class ControlContractError(ValueError):
    """A control-plane contract (event/command/checkpoint/permission) failed validation."""

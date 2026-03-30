"""Reusable UI helpers extracted in Sprint 1.

This module is intentionally lightweight in Sprint 1. It prepares the project
for a later extraction of repeated Streamlit rendering blocks without changing
current app behavior.
"""

from __future__ import annotations

from typing import Any


def identity(value: Any) -> Any:
    return value

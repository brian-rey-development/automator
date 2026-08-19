"""Shared formatting of Pydantic validation errors."""

from __future__ import annotations

from pydantic import ValidationError
from pydantic_core import ErrorDetails

_FIELD_LABELS = {
    "cuit": "CUIT",
    "name": "Razon social",
    "legal_name": "Razon social",
    "trade_name": "Nombre de fantasia",
}


def format_validation_error(exc: ValidationError, *, include_field: bool = False) -> str:
    return "\n".join(_error_text(error, include_field) for error in exc.errors())


def first_validation_error(exc: ValidationError) -> str:
    return _error_text(exc.errors()[0], include_field=True)


def _error_text(error: ErrorDetails, include_field: bool) -> str:
    message = str(error["msg"]).removeprefix("Value error, ")
    if not include_field or not error["loc"]:
        return message
    loc = str(error["loc"][0])
    return f"{_FIELD_LABELS.get(loc, loc)}: {message}"

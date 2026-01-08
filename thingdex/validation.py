import datetime as dt
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class SchemaValidationError(Exception):
    errors: list[str]

    def __str__(self) -> str:
        return "; ".join(self.errors)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)


def _is_date_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        dt.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _is_datetime_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        dt.datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def _validate_field(key: str, definition: dict[str, Any], value: Any) -> list[str]:
    errors: list[str] = []
    field_type = definition.get("type")
    if field_type == "string":
        if not isinstance(value, str):
            errors.append(f"{key}: expected string")
    elif field_type == "integer":
        if not _is_integer(value):
            errors.append(f"{key}: expected integer")
    elif field_type == "number":
        if not _is_number(value):
            errors.append(f"{key}: expected number")
    elif field_type == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{key}: expected boolean")
    elif field_type == "date":
        if not _is_date_string(value):
            errors.append(f"{key}: expected ISO date string")
    elif field_type == "date-time":
        if not _is_datetime_string(value):
            errors.append(f"{key}: expected ISO datetime string")
    elif field_type is None:
        errors.append(f"{key}: missing type in schema")
    else:
        errors.append(f"{key}: unknown type '{field_type}'")

    if "enum" in definition and value not in definition["enum"]:
        errors.append(f"{key}: value not in enum")

    if field_type in ("integer", "number"):
        if "min" in definition and _is_number(value) and value < definition["min"]:
            errors.append(f"{key}: below min")
        if "max" in definition and _is_number(value) and value > definition["max"]:
            errors.append(f"{key}: above max")

    if field_type == "string" and "pattern" in definition and isinstance(value, str):
        if not re.fullmatch(definition["pattern"], value):
            errors.append(f"{key}: pattern mismatch")

    return errors


def validate_props(
    schema: dict[str, Any],
    props: dict[str, Any] | None,
    *,
    partial: bool,
    apply_defaults: bool = False,
) -> dict[str, Any]:
    if props is None:
        props = {}
    fields = schema.get("fields", {}) if isinstance(schema, dict) else {}
    allow_additional = bool(schema.get("allow_additional")) if isinstance(schema, dict) else False

    result = dict(props)
    errors: list[str] = []

    if apply_defaults:
        for key, definition in fields.items():
            if key not in result and "default" in definition:
                result[key] = definition["default"]

    if not partial:
        for key, definition in fields.items():
            if definition.get("required") and key not in result:
                errors.append(f"{key}: required field missing")

    for key, value in result.items():
        if key not in fields:
            if not allow_additional:
                errors.append(f"{key}: unexpected field")
            continue
        errors.extend(_validate_field(key, fields[key], value))

    if errors:
        raise SchemaValidationError(errors)

    return result


def track_history_for(schema: dict[str, Any], key: str) -> bool:
    fields = schema.get("fields", {}) if isinstance(schema, dict) else {}
    definition = fields.get(key, {})
    return bool(definition.get("track_history"))

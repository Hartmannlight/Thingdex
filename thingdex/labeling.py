from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_PRINTHUB_API_BASE = "http://printhub.xn--jahnstrae-n1a.de"
DEFAULT_CONTAINER_TEMPLATE_ID = "container-name"


class LabelServiceError(RuntimeError):
    pass


def label_printing_enabled() -> bool:
    value = os.getenv("LABEL_PRINTING_ENABLED", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _label_api_base() -> str:
    legacy_override = os.getenv("LABEL_API_BASE")
    if legacy_override:
        return legacy_override.rstrip("/")
    return f"{_printhub_api_base()}/v1"


def _printhub_api_base() -> str:
    return os.getenv("PRINTHUB_API_BASE", DEFAULT_PRINTHUB_API_BASE).rstrip("/")


def container_template_id() -> str:
    return os.getenv("LABEL_CONTAINER_TEMPLATE_ID", DEFAULT_CONTAINER_TEMPLATE_ID)


def fetch_template(template_id: str) -> dict[str, Any]:
    url = f"{_label_api_base()}/templates/{template_id}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LabelServiceError(f"Template '{template_id}' not found") from exc
    except httpx.HTTPError as exc:
        raise LabelServiceError("Label service unavailable") from exc
    return resp.json()


def required_template_variables(template: dict[str, Any]) -> list[str]:
    variables = template.get("variables", [])
    required = []
    for entry in variables:
        if isinstance(entry, dict) and entry.get("mode") == "required":
            name = entry.get("name")
            if isinstance(name, str):
                required.append(name)
    return required


def validate_template_against_schema(
    template: dict[str, Any],
    schema: dict[str, Any],
    *,
    bindings: dict[str, str] | None = None,
) -> list[str]:
    variables = template.get("variables", [])
    fields = schema.get("fields", {}) if isinstance(schema, dict) else {}
    missing: list[str] = []
    for entry in variables:
        if not isinstance(entry, dict) or entry.get("mode") != "required":
            continue
        name = entry.get("name")
        if not isinstance(name, str) or name == "internal_uuid":
            continue
        source_hint = (bindings or {}).get(name) or entry.get("source_hint")
        schema_field = name
        if isinstance(source_hint, str):
            root, _, path = source_hint.partition(".")
            if root in {"entity", "item", "location"}:
                continue
            if root == "props" and path:
                schema_field = path.split(".", 1)[0]
        definition = fields.get(schema_field)
        if not isinstance(definition, dict):
            missing.append(name)
            continue
        if not definition.get("required", False):
            missing.append(name)
    return missing


def _resolve_source_hint(context: dict[str, Any], source_hint: str) -> Any:
    value: Any = context
    for segment in source_hint.split("."):
        if not isinstance(value, dict) or segment not in value:
            return None
        value = value[segment]
    return value


def build_template_variables(
    template: dict[str, Any],
    props: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
    bindings: dict[str, str] | None = None,
) -> dict[str, Any]:
    variables = template.get("variables", [])
    result: dict[str, Any] = {}
    source_context = {"props": props, **(context or {})}
    for entry in variables:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        name = entry["name"]
        if name in props:
            result[name] = props[name]
            continue
        source_hint = (bindings or {}).get(name) or entry.get("source_hint")
        if isinstance(source_hint, str):
            value = _resolve_source_hint(source_context, source_hint)
            if value is not None:
                result[name] = value
                continue
        if "default" in entry:
            result[name] = entry["default"]
    return result

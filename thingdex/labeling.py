from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_LABEL_API_BASE = "http://label.xn--jahnstrae-n1a.de/api/v1"
DEFAULT_PRINTHUB_API_BASE = "http://printhub.xn--jahnstrae-n1a.de"
DEFAULT_CONTAINER_TEMPLATE_ID = "container-name"


class LabelServiceError(RuntimeError):
    pass


def label_printing_enabled() -> bool:
    value = os.getenv("LABEL_PRINTING_ENABLED", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _label_api_base() -> str:
    return os.getenv("LABEL_API_BASE", DEFAULT_LABEL_API_BASE).rstrip("/")


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


def validate_template_against_schema(template: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    required = required_template_variables(template)
    fields = schema.get("fields", {}) if isinstance(schema, dict) else {}
    missing: list[str] = []
    for name in required:
        definition = fields.get(name)
        if not isinstance(definition, dict):
            missing.append(name)
            continue
        if not definition.get("required", False):
            missing.append(name)
    return missing


def build_template_variables(template: dict[str, Any], props: dict[str, Any]) -> dict[str, Any]:
    variables = template.get("variables", [])
    names = []
    for entry in variables:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
    return {name: props[name] for name in names if name in props}


def print_label(
    *,
    printer_id: str,
    template: dict[str, Any],
    variables: dict[str, Any],
    return_preview: bool | None = None,
) -> dict[str, Any]:
    url = f"{_printhub_api_base()}/v1/printers/{printer_id}/prints/template"
    payload: dict[str, Any] = {"template": template}
    if variables:
        payload["variables"] = variables
    if return_preview is not None:
        payload["return_preview"] = return_preview
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()
        message = detail or f"Print request failed ({exc.response.status_code})"
        raise LabelServiceError(message) from exc
    except httpx.HTTPError as exc:
        raise LabelServiceError("Print request failed") from exc
    return resp.json()

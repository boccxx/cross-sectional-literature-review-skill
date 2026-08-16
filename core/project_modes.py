"""Canonical project-mode policy shared by the four-skill suite."""
from __future__ import annotations


CANONICAL_PROJECT_MODES = {"research", "applied_methods", "workflow_methods"}
LEGACY_PROJECT_MODE_ALIASES = {
    "simulation": "applied_methods",
    "methods_demo": "workflow_methods",
}
ACCEPTED_PROJECT_MODES = CANONICAL_PROJECT_MODES | set(LEGACY_PROJECT_MODE_ALIASES)


def normalize_project_mode(value: object, *, default: str = "research") -> str:
    """Return a canonical project mode or raise a clear validation error."""
    raw = str(value or default).strip()
    canonical = LEGACY_PROJECT_MODE_ALIASES.get(raw, raw)
    if canonical not in CANONICAL_PROJECT_MODES:
        allowed = ", ".join(sorted(ACCEPTED_PROJECT_MODES))
        raise ValueError(f"project_mode '{raw}' is not valid; expected one of: {allowed}")
    return canonical


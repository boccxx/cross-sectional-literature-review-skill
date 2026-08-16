#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def first_n_lines(text: str, n: int = 25) -> str:
    return "\n".join(text.splitlines()[:n])


def normalize(text: str) -> str:
    return text.lower().replace("_", " ").replace("-", " ")


def contains_token(text: str, token: str) -> bool:
    return normalize(token) in normalize(text)


def find_missing_sections(text: str, sections: list[str]) -> list[str]:
    norm = normalize(text)
    return [section for section in sections if normalize(section) not in norm]


def path_exists(base: Path, names: list[str]) -> list[str]:
    missing = []
    for name in names:
        if not (base / name).exists():
            missing.append(name)
    return missing


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize_status(errors: list[str], warnings: list[str]) -> str:
    if errors:
        return "fail"
    if warnings:
        return "warn"
    return "pass"


# ---------------------------------------------------------------------------
# Content quality helpers (new in v2)
# ---------------------------------------------------------------------------

def word_count(text: str) -> int:
    """Count words in text, stripping YAML frontmatter if present."""
    body = strip_yaml_frontmatter(text)
    return len(body.split())


def strip_yaml_frontmatter(text: str) -> str:
    """Remove YAML frontmatter block delimited by --- ... --- at the start."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def strip_references_section(text: str) -> str:
    """Remove a trailing References or Bibliography section for word-count purposes."""
    pattern = re.compile(
        r"\n#+\s*(References|Bibliography|参考文献)\b.*$",
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.sub("", text)


def body_word_count(text: str) -> int:
    """Word count of narrative body: strips YAML frontmatter and References section."""
    body = strip_yaml_frontmatter(text)
    body = strip_references_section(body)
    return len(body.split())


def check_prohibited_in_body(text: str, phrases: list[str]) -> list[str]:
    """Return prohibited phrases that appear anywhere in the text body."""
    body = strip_yaml_frontmatter(text)
    norm_body = normalize(body)
    found = []
    for phrase in phrases:
        if normalize(phrase) in norm_body:
            found.append(phrase)
    return found


def extract_section(text: str, section_name: str) -> str:
    """
    Extract the content of a named Markdown section (heading + body until next
    same-or-higher-level heading).  Returns empty string if not found.
    """
    lines = text.splitlines()
    # Allow optional numeric prefix in headings, e.g. "## 6.5 Sample-size Planning".
    pattern = re.compile(
        r"^(#{1,4})\s+(?:\d+(?:\.\d+)*\s+)?"
        + re.escape(section_name.strip())
        + r"\s*$",
        re.IGNORECASE,
    )
    candidates = [(index, len(match.group(1))) for index, line in enumerate(lines) if (match := pattern.match(line))]
    if not candidates:
        return ""
    # A structured abstract may contain "## Methods" and "## Results" before
    # the full top-level sections. Prefer the highest-level matching heading.
    section_level = min(level for _, level in candidates)
    start = next(index for index, level in candidates if level == section_level)
    collected: list[str] = [lines[start]]
    for line in lines[start + 1:]:
        heading_match = re.match(r"^(#{1,4})\s+", line)
        if heading_match and len(heading_match.group(1)) <= section_level:
            break
        collected.append(line)

    return "\n".join(collected)


def has_numbers_in_section(section_text: str) -> bool:
    """Return True if the section contains at least one explicit integer (for count checks)."""
    return bool(re.search(r"\b\d+\b", section_text))


def check_inline_screening_numbers(text: str) -> bool:
    """
    Heuristic: the Search and Screening section must contain at least 3 distinct
    integers (retrieved, screened, retained counts).
    """
    section = extract_section(text, "Search and Screening")
    if not section:
        return False
    numbers = re.findall(r"\b\d+\b", section)
    return len(numbers) >= 3


def check_explicit_estimand(text: str) -> bool:
    """Return True if the text contains an explicit labelled primary estimand statement."""
    patterns = [
        r"primary estimand",
        r"primary.*estimand",
        r"estimand.*primary",
    ]
    norm = normalize(text)
    return any(re.search(p, norm) for p in patterns)


def check_numeric_sample_size(text: str) -> bool:
    """
    Return True if the sample-size section contains at least 4 integers,
    suggesting explicit numeric inputs rather than narrative description only.
    """
    section = (
        extract_section(text, "Sample-size Planning")
        or extract_section(text, "Sample-size Inputs")
        or extract_section(text, "Sample Size")
        or extract_section(text, "Sample")
        or extract_section(text, "sample-size")
        or extract_section(text, "Bias Control")
    )
    numbers = re.findall(r"\b\d+[\.,]?\d*\b", section)
    return len(numbers) >= 4


def check_disclosure_in_permitted_sections_only(
    text: str,
    disclosure_tokens: list[str],
    permitted_sections: list[str],
    forbidden_section_names: list[str],
) -> list[str]:
    """
    For applied_methods mode: check that disclosure tokens do not appear in
    forbidden sections (Introduction, title area, main Discussion paragraphs).
    Returns a list of violation descriptions.
    """
    violations = []
    for section_name in forbidden_section_names:
        section_text = extract_section(text, section_name)
        if not section_text:
            continue
        for token in disclosure_tokens:
            if contains_token(section_text, token):
                violations.append(
                    f"disclosure token '{token}' found in forbidden section '{section_name}'"
                )
    return violations


def _section_body_paragraphs(section_text: str) -> list[str]:
    lines = section_text.splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("#")):
        lines.pop(0)
    return [part.strip() for part in "\n".join(lines).split("\n\n") if part.strip()]


def check_applied_methods_disclosure_exact(
    text: str,
    disclosure_tokens: list[str],
) -> list[str]:
    """Enforce the suite's two-location disclosure policy.

    Each disclosure token must occur in the final sentence of Abstract Methods
    and the first paragraph of Limitations, and nowhere else.
    """
    violations: list[str] = []
    abstract = extract_section(text, "Abstract")
    abstract_methods = extract_section(abstract, "Methods") if abstract else ""
    limitations = extract_section(text, "Limitations")
    if not abstract_methods:
        return ["Abstract Methods subsection is missing"]
    if not limitations:
        return ["Limitations subsection is missing"]

    abstract_parts = _section_body_paragraphs(abstract_methods)
    abstract_body = " ".join(abstract_parts)
    abstract_sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?。！？])\s+", abstract_body)
        if item.strip()
    ]
    abstract_last_sentence = abstract_sentences[-1] if abstract_sentences else abstract_body
    limitation_parts = _section_body_paragraphs(limitations)
    limitation_first_paragraph = limitation_parts[0] if limitation_parts else ""
    allowed_text = f"{abstract_last_sentence}\n{limitation_first_paragraph}"

    for token in disclosure_tokens:
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", re.IGNORECASE)
        if not pattern.search(abstract_last_sentence):
            violations.append(f"'{token}' missing from the final sentence of Abstract Methods")
        if not pattern.search(limitation_first_paragraph):
            violations.append(f"'{token}' missing from the first Limitations paragraph")
        total_count = len(pattern.findall(text))
        allowed_count = len(pattern.findall(allowed_text))
        if total_count != allowed_count:
            violations.append(f"'{token}' appears outside the two permitted disclosure locations")
    return violations


def check_discussion_contribution(
    text: str,
    forbidden_contribution_phrases: list[str],
) -> list[str]:
    """
    Check that the Discussion section does not open with workflow-validation
    as the primary contribution.
    """
    section = extract_section(text, "Discussion")
    if not section:
        return []
    found = []
    for phrase in forbidden_contribution_phrases:
        if contains_token(section, phrase):
            found.append(phrase)
    return found

import re
from dataclasses import dataclass

from app.llm.schemas import ScenarioGenerationResult


@dataclass
class ValidationIssue:
    code: str
    detail: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _names_match(first: str, second: str) -> bool:
    normalized_first = _normalize(first)
    normalized_second = _normalize(second)
    return normalized_first in normalized_second or normalized_second in normalized_first


def validate_scenario(
    generation: ScenarioGenerationResult,
    *,
    profile_investigations: list[str],
    profile_red_flags: list[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not generation.hpi:
        issues.append(ValidationIssue("STATE_INCOMPLETE", "The HPI is empty."))
    elif "onset" not in generation.hpi:
        issues.append(ValidationIssue("STATE_INCOMPLETE", "The HPI does not establish onset."))

    if not generation.examinations:
        issues.append(
            ValidationIssue("EXAM_MISSING", "No physical examination findings were generated.")
        )

    if profile_investigations:
        matched = any(
            _names_match(investigation.test_name, profile_name)
            for investigation in generation.investigations
            for profile_name in profile_investigations
        )
        if not matched:
            issues.append(
                ValidationIssue(
                    "INVESTIGATION_MISMATCH",
                    "None of the scenario investigations match the investigations "
                    "established by the disease profile.",
                )
            )

    scenario_flag_keys = {_normalize(key) for key in generation.red_flags}
    missing_flags = [
        flag for flag in profile_red_flags if _normalize(flag) not in scenario_flag_keys
    ]
    if missing_flags:
        issues.append(
            ValidationIssue(
                "RED_FLAG_COVERAGE",
                "Red flags not covered by the scenario state: "
                + ", ".join(missing_flags[:5])
                + ".",
            )
        )

    return issues

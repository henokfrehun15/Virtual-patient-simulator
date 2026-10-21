from dataclasses import dataclass

from app.llm.schemas import DiseaseProfileResult, RubricItemDraft


@dataclass
class ValidationIssue:
    code: str
    detail: str


def validate_disease_content(
    *,
    profile: DiseaseProfileResult,
    rubric_items: list[RubricItemDraft],
    evidence_count: int,
    page_count: int,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    clinically_empty = (
        not profile.symptoms and not profile.exam_findings and not profile.investigations
    )
    if clinically_empty:
        issues.append(
            ValidationIssue(
                "PROFILE_EMPTY",
                "Profile contains no symptoms, exam findings, or investigations.",
            )
        )

    if evidence_count == 0:
        issues.append(
            ValidationIssue("EVIDENCE_MISSING", "No source evidence chunks were used.")
        )

    if not rubric_items:
        issues.append(
            ValidationIssue("RUBRIC_ITEMS_MISSING", "No rubric items were generated.")
        )

    if page_count > 0:
        for page in profile.source_pages:
            if not 1 <= page <= page_count:
                issues.append(
                    ValidationIssue(
                        "SOURCE_PAGE_INVALID",
                        f"Source page {page} is outside the document page range.",
                    )
                )
                break

    questions = [item.question_text.strip().lower() for item in rubric_items]
    if len(questions) != len(set(questions)):
        issues.append(
            ValidationIssue(
                "RUBRIC_DUPLICATE_QUESTIONS",
                "Rubric items contain duplicate questions.",
            )
        )

    if profile.red_flags and not any(item.critical for item in rubric_items):
        issues.append(
            ValidationIssue(
                "CRITICAL_RUBRIC_MISSING",
                "Red flags are present but no rubric item is marked critical.",
            )
        )

    return issues

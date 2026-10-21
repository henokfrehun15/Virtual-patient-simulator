from app.llm.schemas import (
    Demographics,
    DiseaseProfileResult,
    InvestigationFinding,
    RubricCategory,
    RubricItemDraft,
    SymptomFinding,
)
from app.services.content_validation import validate_disease_content


def make_profile(**overrides) -> DiseaseProfileResult:
    defaults = dict(
        name="Pneumonia",
        aliases=[],
        demographics=Demographics(),
        symptoms=[SymptomFinding(name="cough", frequency="common")],
        exam_findings=[SymptomFinding(name="crackles", frequency="common")],
        investigations=[InvestigationFinding(name="chest x-ray", typical_result="consolidation")],
        differentials=[],
        red_flags=[],
        history_checklist=[],
        source_pages=[1],
    )
    defaults.update(overrides)
    return DiseaseProfileResult(**defaults)


def make_rubrics() -> list[RubricItemDraft]:
    return [
        RubricItemDraft(
            category=RubricCategory.CHIEF_COMPLAINT,
            question_text="What brings you in today?",
            rationale="Opens the encounter",
            weight=2,
            critical=False,
        ),
        RubricItemDraft(
            category=RubricCategory.RED_FLAG_SCREEN,
            question_text="Are you having trouble breathing at rest?",
            rationale="Screens respiratory distress",
            weight=5,
            critical=True,
        ),
    ]


def test_valid_content_has_no_issues() -> None:
    issues = validate_disease_content(
        profile=make_profile(), rubric_items=make_rubrics(), evidence_count=2, page_count=3
    )
    assert issues == []


def test_empty_profile_is_flagged() -> None:
    issues = validate_disease_content(
        profile=make_profile(symptoms=[], exam_findings=[], investigations=[]),
        rubric_items=make_rubrics(),
        evidence_count=2,
        page_count=3,
    )
    assert [issue.code for issue in issues] == ["PROFILE_EMPTY"]


def test_missing_evidence_is_flagged() -> None:
    issues = validate_disease_content(
        profile=make_profile(), rubric_items=make_rubrics(), evidence_count=0, page_count=3
    )
    assert [issue.code for issue in issues] == ["EVIDENCE_MISSING"]


def test_missing_rubrics_are_flagged() -> None:
    issues = validate_disease_content(
        profile=make_profile(), rubric_items=[], evidence_count=2, page_count=3
    )
    assert [issue.code for issue in issues] == ["RUBRIC_ITEMS_MISSING"]


def test_invalid_source_page_is_flagged() -> None:
    issues = validate_disease_content(
        profile=make_profile(source_pages=[99]),
        rubric_items=make_rubrics(),
        evidence_count=2,
        page_count=3,
    )
    assert [issue.code for issue in issues] == ["SOURCE_PAGE_INVALID"]


def test_duplicate_rubric_questions_are_flagged() -> None:
    rubrics = make_rubrics() + [
        RubricItemDraft(
            category=RubricCategory.HPI,
            question_text="what brings you in today?",
            rationale="Duplicate",
            weight=1,
            critical=False,
        )
    ]
    issues = validate_disease_content(
        profile=make_profile(), rubric_items=rubrics, evidence_count=2, page_count=3
    )
    assert "RUBRIC_DUPLICATE_QUESTIONS" in [issue.code for issue in issues]


def test_red_flags_without_critical_rubric_are_flagged() -> None:
    rubrics = [
        RubricItemDraft(
            category=RubricCategory.HPI,
            question_text="When did the cough start?",
            rationale="Onset",
            weight=3,
            critical=False,
        )
    ]
    issues = validate_disease_content(
        profile=make_profile(red_flags=["severe respiratory distress"]),
        rubric_items=rubrics,
        evidence_count=2,
        page_count=3,
    )
    assert "CRITICAL_RUBRIC_MISSING" in [issue.code for issue in issues]

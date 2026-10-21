from app.llm.schemas import (
    ScenarioDemographics,
    ScenarioExamination,
    ScenarioGenerationResult,
    ScenarioInvestigation,
)
from app.services.scenario_validation import validate_scenario


def make_generation(**overrides) -> ScenarioGenerationResult:
    defaults = dict(
        demographics=ScenarioDemographics(name="Sarah Johnson", age=34, sex="female"),
        chief_complaint="cough and fever",
        hpi={"onset": "3 days ago", "severity": 6},
        pmh=[],
        medications=[],
        allergies=[],
        family_history=[],
        social_history={},
        ros={},
        red_flags={"severe respiratory distress": False},
        communication_style="cooperative but worried",
        emotional_state="anxious",
        examinations=[
            ScenarioExamination(
                exam_name="respiratory examination",
                findings={"auscultation": "crackles in the right lower zone"},
            )
        ],
        investigations=[
            ScenarioInvestigation(
                test_name="chest x-ray",
                result={"finding": "right lower lobe consolidation"},
            )
        ],
    )
    defaults.update(overrides)
    return ScenarioGenerationResult(**defaults)


def test_valid_scenario_has_no_issues() -> None:
    issues = validate_scenario(
        make_generation(),
        profile_investigations=["chest x-ray"],
        profile_red_flags=["severe respiratory distress"],
    )
    assert issues == []


def test_empty_hpi_is_flagged() -> None:
    issues = validate_scenario(
        make_generation(hpi={}),
        profile_investigations=["chest x-ray"],
        profile_red_flags=["severe respiratory distress"],
    )
    assert [issue.code for issue in issues] == ["STATE_INCOMPLETE"]


def test_hpi_without_onset_is_flagged() -> None:
    issues = validate_scenario(
        make_generation(hpi={"severity": 5}),
        profile_investigations=["chest x-ray"],
        profile_red_flags=["severe respiratory distress"],
    )
    assert [issue.code for issue in issues] == ["STATE_INCOMPLETE"]


def test_missing_examinations_are_flagged() -> None:
    issues = validate_scenario(
        make_generation(examinations=[]),
        profile_investigations=["chest x-ray"],
        profile_red_flags=["severe respiratory distress"],
    )
    assert [issue.code for issue in issues] == ["EXAM_MISSING"]


def test_investigation_mismatch_is_flagged() -> None:
    generation = make_generation(
        investigations=[
            ScenarioInvestigation(test_name="urinalysis", result={"finding": "normal"})
        ]
    )
    issues = validate_scenario(
        generation,
        profile_investigations=["chest x-ray"],
        profile_red_flags=["severe respiratory distress"],
    )
    assert [issue.code for issue in issues] == ["INVESTIGATION_MISMATCH"]


def test_investigation_name_containment_matches() -> None:
    generation = make_generation(
        investigations=[
            ScenarioInvestigation(
                test_name="Chest X-Ray (PA view)",
                result={"finding": "right lower lobe consolidation"},
            )
        ]
    )
    issues = validate_scenario(
        generation,
        profile_investigations=["chest x-ray"],
        profile_red_flags=["severe respiratory distress"],
    )
    assert issues == []


def test_red_flag_coverage_gap_is_flagged() -> None:
    issues = validate_scenario(
        make_generation(),
        profile_investigations=["chest x-ray"],
        profile_red_flags=["severe respiratory distress", "new confusion"],
    )
    assert [issue.code for issue in issues] == ["RED_FLAG_COVERAGE"]
    assert "new confusion" in issues[0].detail

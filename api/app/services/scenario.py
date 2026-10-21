import uuid

import redis
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.llm.prompts import scenario as scenario_prompts
from app.llm.router import LLMRequest, get_llm_router
from app.llm.schemas import ScenarioGenerationResult
from app.models.disease import DiseaseSourceEvidence, DiseaseVersion
from app.models.material import DocumentChunk, MaterialVersion
from app.models.scenario import (
    Scenario,
    ScenarioExamination,
    ScenarioInvestigation,
    ScenarioPatientState,
)
from app.services.scenario_validation import validate_scenario

logger = get_logger("app.scenario")

SCENARIO_LOCK_TTL_SECONDS = 1800
DIFFICULTIES = ("easy", "medium", "hard")


def configured_difficulties() -> list[str]:
    settings = get_settings()
    return [
        difficulty.strip()
        for difficulty in settings.scenario_difficulties.split(",")
        if difficulty.strip() in DIFFICULTIES
    ]


def published_disease_version_ids_for_material(
    material_version_id: uuid.UUID,
) -> list[uuid.UUID]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(DiseaseVersion.id)
            .join(
                DiseaseSourceEvidence,
                DiseaseSourceEvidence.disease_version_id == DiseaseVersion.id,
            )
            .join(DocumentChunk, DocumentChunk.id == DiseaseSourceEvidence.chunk_id)
            .join(MaterialVersion, MaterialVersion.id == DocumentChunk.material_version_id)
            .where(
                MaterialVersion.id == material_version_id,
                DiseaseVersion.status == "published",
            )
        ).all()
    return list(rows)


def scenario_title(state: dict) -> str:
    demographics = state.get("demographics") or {}
    age = demographics.get("age")
    sex = demographics.get("sex")
    complaint = state.get("chief_complaint") or "presenting complaint"
    if isinstance(age, int) and sex:
        return f"{age}-year-old {sex} with {complaint}"
    return f"Patient with {complaint}"


def run_scenario_generation(disease_version_id: uuid.UUID, difficulty: str) -> None:
    if difficulty not in DIFFICULTIES:
        logger.error("scenario_invalid_difficulty", difficulty=difficulty)
        return

    settings = get_settings()
    lock_client = redis.Redis.from_url(settings.redis_url)
    lock_key = f"lock:scenario:{disease_version_id}:{difficulty}"
    if not lock_client.set(lock_key, "1", nx=True, ex=SCENARIO_LOCK_TTL_SECONDS):
        logger.info(
            "scenario_skipped_locked",
            disease_version_id=str(disease_version_id),
            difficulty=difficulty,
        )
        return

    try:
        with SessionLocal() as db:
            disease_version = db.get(DiseaseVersion, disease_version_id)
            if disease_version is None:
                logger.error(
                    "scenario_disease_version_missing",
                    disease_version_id=str(disease_version_id),
                )
                return
            if disease_version.status != "published":
                logger.info(
                    "scenario_skipped_not_published",
                    disease_version_id=str(disease_version_id),
                    status=disease_version.status,
                )
                return

            existing = db.scalar(
                select(Scenario).where(
                    Scenario.disease_version_id == disease_version.id,
                    Scenario.difficulty == difficulty,
                )
            )
            if existing is not None:
                logger.info("scenario_skipped_exists", scenario_id=str(existing.id))
                return

            router = get_llm_router()
            seed = uuid.uuid4().hex
            generation = router.generate(
                "scenario_generation",
                LLMRequest(
                    system=scenario_prompts.SYSTEM_PROMPT,
                    user=scenario_prompts.build_user_content(disease_version, difficulty, seed),
                    schema_model=ScenarioGenerationResult,
                    max_tokens=scenario_prompts.MAX_TOKENS,
                    prompt_version=scenario_prompts.PROMPT_VERSION,
                ),
            )

            next_version = (
                db.scalar(
                    select(func.max(Scenario.version)).where(
                        Scenario.disease_version_id == disease_version.id
                    )
                )
                or 0
            ) + 1

            scenario = Scenario(
                disease_version_id=disease_version.id,
                version=next_version,
                difficulty=difficulty,
                scenario_seed=seed,
                generator_model=router.model_for_task("scenario_generation"),
                generator_prompt_version=scenario_prompts.PROMPT_VERSION,
                status="draft",
            )
            db.add(scenario)
            db.flush()

            state = _build_state(generation, disease_version, difficulty)
            db.add(ScenarioPatientState(scenario_id=scenario.id, state=state))

            for examination in generation.examinations:
                db.add(
                    ScenarioExamination(
                        scenario_id=scenario.id,
                        exam_name=examination.exam_name,
                        available=True,
                        findings=examination.findings,
                    )
                )
            for investigation in generation.investigations:
                db.add(
                    ScenarioInvestigation(
                        scenario_id=scenario.id,
                        test_name=investigation.test_name,
                        available=investigation.available,
                        result=investigation.result,
                        cost_weight=investigation.cost_weight,
                    )
                )

            profile_investigations = [
                item.get("name", "")
                for item in (disease_version.investigations or [])
                if isinstance(item, dict) and item.get("name")
            ]
            issues = validate_scenario(
                generation,
                profile_investigations=profile_investigations,
                profile_red_flags=disease_version.red_flags or [],
            )

            state["_meta"]["validation"] = {
                "passed": not issues,
                "issues": [{"code": issue.code, "detail": issue.detail} for issue in issues],
            }
            scenario.status = "published" if not issues else "draft"
            db.commit()

            logger.info(
                "scenario_generated",
                scenario_id=str(scenario.id),
                disease_version_id=str(disease_version.id),
                difficulty=difficulty,
                status=scenario.status,
                issues=len(issues),
            )
    finally:
        lock_client.delete(lock_key)


def _build_state(
    generation: ScenarioGenerationResult, disease_version: DiseaseVersion, difficulty: str
) -> dict:
    return {
        "demographics": generation.demographics.model_dump(),
        "chief_complaint": generation.chief_complaint,
        "hpi": generation.hpi,
        "pmh": generation.pmh,
        "medications": generation.medications,
        "allergies": generation.allergies,
        "family_history": generation.family_history,
        "social_history": generation.social_history,
        "ros": generation.ros,
        "red_flags": generation.red_flags,
        "physical_exam": {
            item.exam_name: item.findings for item in generation.examinations
        },
        "investigation_results": {
            item.test_name: item.result for item in generation.investigations
        },
        "communication_style": generation.communication_style,
        "emotional_state": generation.emotional_state,
        "_meta": {
            "disease_version_id": str(disease_version.id),
            "difficulty": difficulty,
        },
    }

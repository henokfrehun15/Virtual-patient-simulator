import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import AppError
from app.core.idempotency import load_result, store_result
from app.core.logging import get_logger
from app.llm.prompts import diagnosis as diagnosis_prompts
from app.llm.router import LLMRequest, get_llm_router
from app.llm.schemas import DiagnosisNormalization
from app.models.rubric import DiagnosisOption
from app.models.scenario import Scenario
from app.models.session import DiagnosisAttempt, Session as SessionModel
from app.services.session import ensure_session_active, record_session_event

logger = get_logger("app.diagnosis")

MATCH_VERDICTS = {"exact": "correct", "synonym": "correct", "partial": "partial"}


def _normalize(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9 ]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _match_option(
    guess_norm: str, options: list[DiagnosisOption]
) -> tuple[str, DiagnosisOption | None]:
    for match_type in ("exact", "synonym", "partial"):
        for option in options:
            if option.match_type != match_type:
                continue
            option_norm = _normalize(option.label)
            if option_norm and guess_norm == option_norm:
                return match_type, option

    guess_words = set(guess_norm.split())
    for match_type in ("exact", "synonym", "partial"):
        for option in options:
            if option.match_type != match_type:
                continue
            option_norm = _normalize(option.label)
            if not option_norm:
                continue
            if len(option_norm) < 6:
                if option_norm in guess_words:
                    return match_type, option
            elif option_norm in guess_norm or guess_norm in option_norm:
                return match_type, option

    return "incorrect", None


def submit_diagnosis(
    db: DbSession,
    session: SessionModel,
    guess: str,
    idempotency_key: str | None,
) -> DiagnosisAttempt:
    ensure_session_active(db, session)

    if idempotency_key:
        stored = load_result(f"idem:dx:{session.id}:{idempotency_key}")
        if stored is not None:
            existing = db.get(DiagnosisAttempt, uuid.UUID(stored["attempt_id"]))
            if existing is not None and existing.session_id == session.id:
                return existing

    scenario = db.get(Scenario, session.scenario_id)
    if scenario is None:
        raise AppError("SCENARIO_INVALID", "Scenario not found.", status_code=404)
    options = (
        db.scalars(
            select(DiagnosisOption).where(
                DiagnosisOption.disease_version_id == scenario.disease_version_id
            )
        )
        .unique()
        .all()
    )

    guess_clean = guess.strip()
    match_type, option = _match_option(_normalize(guess_clean), options)

    normalized_label: str | None = None
    if option is None:
        try:
            router = get_llm_router(session.user_id)
            result = router.generate(
                "diagnosis_normalization",
                LLMRequest(
                    system=diagnosis_prompts.SYSTEM_PROMPT,
                    user=diagnosis_prompts.build_user_content(guess_clean),
                    schema_model=DiagnosisNormalization,
                    max_tokens=diagnosis_prompts.MAX_TOKENS,
                    prompt_version=diagnosis_prompts.PROMPT_VERSION,
                    session_id=session.id,
                ),
            )
            normalized_label = result.name.strip()
            match_type, option = _match_option(_normalize(normalized_label), options)
        except AppError as exc:
            logger.info("diagnosis_normalization_unavailable", code=exc.code)

    verdict = MATCH_VERDICTS.get(match_type, "incorrect")
    explanation = (
        f"Matched accepted answer '{option.label}' ({option.match_type})."
        if option is not None
        else "No accepted answer matched the submission."
    )

    attempt = DiagnosisAttempt(
        session_id=session.id,
        guess=guess_clean,
        normalized_label=normalized_label,
        verdict=verdict,
        matched_option_id=option.id if option is not None else None,
        explanation=explanation,
    )
    db.add(attempt)
    db.flush()
    record_session_event(
        db,
        session.id,
        "diagnosis_submitted",
        {"attempt_id": str(attempt.id), "verdict": verdict},
    )
    db.commit()
    db.refresh(attempt)

    if idempotency_key:
        store_result(
            f"idem:dx:{session.id}:{idempotency_key}", {"attempt_id": str(attempt.id)}
        )
    return attempt

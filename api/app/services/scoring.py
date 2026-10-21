import math
import uuid

import redis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.llm.embeddings import embed_texts
from app.llm.prompts import scorer as scorer_prompts
from app.llm.router import LLMRequest, get_llm_router
from app.llm.schemas import RubricMatchResult
from app.models.message import Message
from app.models.rubric import RubricItem
from app.models.score import SessionRubricResult
from app.models.scenario import Scenario
from app.models.session import Session as SessionModel
from app.services.session import record_session_event

logger = get_logger("app.scoring")

STATUS_MULTIPLIERS = {
    "satisfied": 1.0,
    "partially_satisfied": 0.5,
    "attempted": 0.25,
    "poorly_asked": 0.0,
    "unsafe": 0.0,
    "not_attempted": 0.0,
    "not_applicable": 0.0,
}

STATUS_RANK = {
    "satisfied": 6,
    "partially_satisfied": 5,
    "attempted": 4,
    "poorly_asked": 3,
    "unsafe": 2,
    "not_applicable": 1,
    "not_attempted": 0,
}


def pending_scoring_key(session_id: uuid.UUID) -> str:
    return f"scoring:pending:{session_id}"


def enqueue_message_scoring(
    session_id: uuid.UUID, doctor_message_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    from app.tasks.scoring import score_message

    client = redis.Redis.from_url(get_settings().redis_url)
    try:
        client.incr(pending_scoring_key(session_id))
    except Exception:
        logger.warning("scoring_counter_incr_failed", session_id=str(session_id))
    score_message.delay(str(session_id), str(doctor_message_id), str(user_id))


def run_message_scoring(
    session_id: uuid.UUID, doctor_message_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        session = db.get(SessionModel, session_id)
        message = db.get(Message, doctor_message_id)
        if (
            session is None
            or message is None
            or message.role != "doctor"
            or message.session_id != session_id
        ):
            return

        scenario = db.get(Scenario, session.scenario_id)
        if scenario is None:
            return
        items = (
            db.scalars(
                select(RubricItem)
                .where(RubricItem.disease_version_id == scenario.disease_version_id)
                .order_by(RubricItem.category, RubricItem.created_at)
            )
            .unique()
            .all()
        )
        if not items:
            return

        candidates = _prefilter(items, message.content)
        if not candidates:
            return

        transcript_rows = (
            db.scalars(
                select(Message)
                .where(
                    Message.session_id == session_id,
                    Message.created_at <= message.created_at,
                )
                .order_by(Message.created_at.desc())
                .limit(8)
            )
            .all()
        )
        transcript_rows.reverse()
        transcript = [f"[{row.role}]: {row.content}" for row in transcript_rows]

        router = get_llm_router(user_id)
        result = router.generate(
            "rubric_matching",
            LLMRequest(
                system=scorer_prompts.SYSTEM_PROMPT,
                user=scorer_prompts.build_user_content(transcript, message.content, candidates),
                schema_model=RubricMatchResult,
                max_tokens=scorer_prompts.MAX_TOKENS,
                prompt_version=scorer_prompts.PROMPT_VERSION,
                session_id=session_id,
            ),
        )

        grader_model = router.model_for_task("rubric_matching")
        matched = 0
        for match in result.matches:
            if not 1 <= match.rubric_index <= len(candidates):
                continue
            item = candidates[match.rubric_index - 1]
            _upsert_result(
                db,
                session_id=session_id,
                item=item,
                status=match.status.value,
                quality_score=match.quality_score,
                confidence=match.confidence,
                reason=match.reason,
                message_id=message.id,
                grader_model=grader_model,
                prompt_version=scorer_prompts.PROMPT_VERSION,
            )
            matched += 1

        db.commit()
        record_session_event(
            db,
            session_id,
            "rubric_scored",
            {"message_id": str(message.id), "matched": matched},
        )
        db.commit()
        logger.info(
            "message_scored",
            session_id=str(session_id),
            message_id=str(doctor_message_id),
            matched=matched,
        )


def _prefilter(items: list[RubricItem], content: str) -> list[RubricItem]:
    settings = get_settings()
    vectors = embed_texts([content])
    with_embeddings = [item for item in items if item.embedding is not None]
    if vectors is not None and len(with_embeddings) >= 3:
        query_vector = vectors[0]
        ranked = sorted(
            with_embeddings,
            key=lambda item: -_cosine_similarity(query_vector, item.embedding),
        )
        return ranked[: settings.scoring_candidate_count]
    return items[: settings.scoring_max_items_per_call]


def _cosine_similarity(first: list[float], second: list[float]) -> float:
    if not first or not second or len(first) != len(second):
        return 0.0
    dot = sum(a * b for a, b in zip(first, second))
    norm_a = math.sqrt(sum(a * a for a in first))
    norm_b = math.sqrt(sum(b * b for b in second))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _upsert_result(
    db,
    *,
    session_id: uuid.UUID,
    item: RubricItem,
    status: str,
    quality_score: float,
    confidence: float,
    reason: str,
    message_id: uuid.UUID,
    grader_model: str,
    prompt_version: str,
) -> None:
    existing = db.scalar(
        select(SessionRubricResult).where(
            SessionRubricResult.session_id == session_id,
            SessionRubricResult.rubric_item_id == item.id,
        )
    )
    new_rank = STATUS_RANK.get(status, 0)
    if existing is not None and STATUS_RANK.get(existing.status, 0) >= new_rank:
        return

    values = {
        "status": status,
        "quality_score": quality_score,
        "confidence": confidence,
        "evidence_message_id": message_id,
        "grader_reason": reason or None,
        "grader_model": grader_model,
        "grader_prompt_version": prompt_version,
        "weight": item.weight,
    }
    if existing is None:
        db.add(
            SessionRubricResult(session_id=session_id, rubric_item_id=item.id, **values)
        )
    else:
        for key, value in values.items():
            setattr(existing, key, value)

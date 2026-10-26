import re
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

import redis
from sqlalchemy import func, or_, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.llm.embeddings import embed_texts
from app.llm.prompts import disease_discovery, disease_profile
from app.llm.prompts import rubric as rubric_prompts
from app.llm.router import LLMRequest, get_llm_router
from app.llm.schemas import (
    DiscoveredDisease,
    DiseaseDiscoveryResult,
    DiseaseProfileResult,
    RubricExtractionResult,
)
from app.models.disease import Disease, DiseaseSourceEvidence, DiseaseVersion
from app.models.material import DocumentChunk, DocumentPage, ExtractionJob, Material, MaterialVersion
from app.models.rubric import DiagnosisOption, RubricItem
from app.services.content_validation import validate_disease_content

logger = get_logger("app.clinical_content")

CLINICAL_LOCK_TTL_SECONDS = 3600
EMBEDDING_VERSION = "v1"


def normalize_disease_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


def run_clinical_content(material_version_id: uuid.UUID) -> None:
    settings = get_settings()
    lock_client = redis.Redis.from_url(settings.redis_url)
    lock_key = f"lock:clinical:{material_version_id}"
    if not lock_client.set(lock_key, "1", nx=True, ex=CLINICAL_LOCK_TTL_SECONDS):
        logger.info("clinical_content_skipped_locked", material_version_id=str(material_version_id))
        return

    try:
        with SessionLocal() as db:
            version = db.get(MaterialVersion, material_version_id)
            if version is None:
                logger.error(
                    "clinical_content_version_missing",
                    material_version_id=str(material_version_id),
                )
                return
            if version.status != "extracted":
                logger.error(
                    "clinical_content_version_not_extracted",
                    material_version_id=str(material_version_id),
                    status=version.status,
                )
                return

            job = _get_or_create_clinical_job(db, version.id)
            if job.status == "succeeded":
                logger.info(
                    "clinical_content_skipped_completed",
                    material_version_id=str(material_version_id),
                )
                return

            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.attempts += 1
            db.commit()

            try:
                _run_pipeline(db, version, job)
            except Exception as exc:
                _fail_job(db, job, repr(exc))
                raise
    finally:
        lock_client.delete(lock_key)


def _run_pipeline(db, version: MaterialVersion, job: ExtractionJob) -> None:
    settings = get_settings()
    material = db.get(Material, version.material_id)
    owner_user_id = material.created_by if material is not None else None

    chunks = (
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.material_version_id == version.id)
            .order_by(DocumentChunk.chunk_index)
        )
        .unique()
        .all()
    )
    if not chunks:
        _fail_job(db, job, "No document chunks found for material version.")
        return

    page_count = (
        db.scalar(
            select(func.max(DocumentPage.page_number)).where(
                DocumentPage.material_version_id == version.id
            )
        )
        or 0
    )

    _backfill_chunk_embeddings(db, chunks)

    discovered = _discover_diseases(chunks, owner_user_id)
    if not discovered:
        job.status = "succeeded"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "clinical_content_no_diseases", material_version_id=str(version.id)
        )
        return

    capped = discovered[: settings.max_diseases_per_material]
    if len(capped) < len(discovered):
        logger.warning(
            "discovery_capped",
            material_version_id=str(version.id),
            found=len(discovered),
            cap=settings.max_diseases_per_material,
        )

    errors: list[str] = []
    for disease_draft in capped:
        try:
            _process_disease(db, version, disease_draft, page_count, owner_user_id)
        except Exception as exc:
            logger.exception(
                "disease_processing_failed",
                material_version_id=str(version.id),
                disease=disease_draft.name,
            )
            errors.append(f"{disease_draft.name}: {exc!r}")

    if errors:
        _fail_job(db, job, "; ".join(errors))
    else:
        job.status = "succeeded"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "clinical_content_completed",
            material_version_id=str(version.id),
            diseases=len(capped),
        )


def _get_or_create_clinical_job(db, material_version_id: uuid.UUID) -> ExtractionJob:
    job = db.scalar(
        select(ExtractionJob).where(
            ExtractionJob.material_version_id == material_version_id,
            ExtractionJob.job_type == "clinical_content",
        )
    )
    if job is None:
        job = ExtractionJob(
            material_version_id=material_version_id,
            job_type="clinical_content",
            status="pending",
        )
        db.add(job)
        db.commit()
    return job


def _fail_job(db, job: ExtractionJob, message: str) -> None:
    job.status = "failed"
    job.error_message = message[:2000]
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    logger.error("clinical_content_failed", error=message[:2000])


def _batched(items: list, size: int) -> Iterator[list]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _batched_within_budget(
    chunks: list[DocumentChunk], max_count: int, max_chars: int
) -> Iterator[list[DocumentChunk]]:
    """Yield batches that respect both a chunk-count and a character budget.

    The character budget keeps each LLM request inside provider
    tokens-per-minute limits (Groq returns 413 when a single request
    exceeds the account's TPM allowance).
    """
    batch: list[DocumentChunk] = []
    chars = 0
    for chunk in chunks:
        chunk_chars = len(chunk.text)
        if batch and (len(batch) >= max_count or chars + chunk_chars > max_chars):
            yield batch
            batch = []
            chars = 0
        batch.append(chunk)
        chars += chunk_chars
    if batch:
        yield batch


def _backfill_chunk_embeddings(db, chunks: list[DocumentChunk]) -> None:
    settings = get_settings()
    missing = [chunk for chunk in chunks if chunk.embedding is None]
    if not missing:
        return
    for batch in _batched(missing, 64):
        vectors = embed_texts([chunk.text for chunk in batch])
        if vectors is None:
            return
        for chunk, vector in zip(batch, vectors):
            chunk.embedding = vector
            chunk.embedding_model = settings.embedding_model
            chunk.embedding_version = EMBEDDING_VERSION
        db.commit()
    logger.info("chunk_embeddings_backfilled", count=len(missing))


def _discover_diseases(
    chunks: list[DocumentChunk], owner_user_id: uuid.UUID | None
) -> list[DiscoveredDisease]:
    settings = get_settings()
    router = get_llm_router(owner_user_id)
    merged: dict[str, DiscoveredDisease] = {}

    for batch in _batched_within_budget(
        chunks,
        max_count=settings.discovery_chunks_per_call,
        max_chars=settings.discovery_batch_max_chars,
    ):
        result = router.generate(
            "disease_extraction",
            LLMRequest(
                system=disease_discovery.SYSTEM_PROMPT,
                user=disease_discovery.build_user_content(batch),
                schema_model=DiseaseDiscoveryResult,
                max_tokens=disease_discovery.MAX_TOKENS,
                prompt_version=disease_discovery.PROMPT_VERSION,
            ),
        )
        for disease in result.diseases:
            key = normalize_disease_name(disease.name)
            if not key:
                continue
            if key in merged:
                existing = merged[key]
                existing.source_pages = sorted(
                    set(existing.source_pages) | set(disease.source_pages)
                )
                if not existing.mention_context:
                    existing.mention_context = disease.mention_context
            else:
                merged[key] = disease

    return list(merged.values())


def _search_terms(name: str) -> list[str]:
    terms = [name.strip()]
    terms.extend(word for word in re.findall(r"[A-Za-z]{4,}", name) if word.lower() != "acute")
    return [term for term in dict.fromkeys(terms) if term]


def _relevant_chunks(
    db, material_version_id: uuid.UUID, discovered: DiscoveredDisease
) -> list[DocumentChunk]:
    settings = get_settings()
    limit = settings.profile_chunks_per_disease

    base = select(DocumentChunk).where(DocumentChunk.material_version_id == material_version_id)

    vectors = embed_texts([discovered.name])
    if vectors is not None:
        chunks = (
            db.scalars(
                base.where(DocumentChunk.embedding.is_not(None))
                .order_by(DocumentChunk.embedding.cosine_distance(vectors[0]))
                .limit(limit)
            )
            .unique()
            .all()
        )
        if chunks:
            return chunks

    conditions = [DocumentChunk.text.ilike(f"%{term}%") for term in _search_terms(discovered.name)]
    if conditions:
        chunks = (
            db.scalars(
                base.where(or_(*conditions))
                .order_by(DocumentChunk.chunk_index)
                .limit(limit)
            )
            .unique()
            .all()
        )
        if chunks:
            return chunks

    if discovered.source_pages:
        chunks = (
            db.scalars(
                base.where(DocumentChunk.page_start.in_(discovered.source_pages))
                .order_by(DocumentChunk.chunk_index)
                .limit(limit)
            )
            .unique()
            .all()
        )
        if chunks:
            return chunks

    return (
        db.scalars(base.order_by(DocumentChunk.chunk_index).limit(limit)).unique().all()
    )


def _process_disease(
    db,
    material_version: MaterialVersion,
    discovered: DiscoveredDisease,
    page_count: int,
    owner_user_id: uuid.UUID | None,
) -> DiseaseVersion:
    settings = get_settings()
    router = get_llm_router(owner_user_id)

    chunks = _relevant_chunks(db, material_version.id, discovered)

    profile = router.generate(
        "disease_extraction",
        LLMRequest(
            system=disease_profile.SYSTEM_PROMPT,
            user=disease_profile.build_user_content(discovered.name, chunks),
            schema_model=DiseaseProfileResult,
            max_tokens=disease_profile.MAX_TOKENS,
            prompt_version=disease_profile.PROMPT_VERSION,
        ),
    )

    canonical = normalize_disease_name(profile.name or discovered.name)
    disease = db.scalar(
        select(Disease).where(func.lower(Disease.canonical_name) == canonical)
    )
    if disease is None:
        disease = Disease(canonical_name=canonical)
        db.add(disease)
        db.flush()

    next_version = (
        db.scalar(
            select(func.max(DiseaseVersion.version)).where(
                DiseaseVersion.disease_id == disease.id
            )
        )
        or 0
    ) + 1

    aliases = sorted(
        {
            alias.strip()
            for alias in profile.aliases
            if alias.strip() and normalize_disease_name(alias) != canonical
        }
    )

    disease_version = DiseaseVersion(
        disease_id=disease.id,
        version=next_version,
        name=profile.name or discovered.name,
        aliases=aliases or None,
        demographics=profile.demographics.model_dump(),
        symptoms=[item.model_dump() for item in profile.symptoms] or None,
        exam_findings=[item.model_dump() for item in profile.exam_findings] or None,
        investigations=[item.model_dump() for item in profile.investigations] or None,
        differentials=profile.differentials or None,
        red_flags=profile.red_flags or None,
        history_checklist=[item.model_dump() for item in profile.history_checklist] or None,
        status="draft",
        source_summary={
            "material_version_id": str(material_version.id),
            "discovery": {
                "source_pages": discovered.source_pages,
                "mention_context": discovered.mention_context,
            },
            "profile_source_pages": profile.source_pages,
            "prompt_versions": {
                "discovery": disease_discovery.PROMPT_VERSION,
                "profile": disease_profile.PROMPT_VERSION,
                "rubric": rubric_prompts.PROMPT_VERSION,
            },
            "models": {
                "disease_extraction": router.model_for_task("disease_extraction"),
                "rubric_extraction": router.model_for_task("rubric_extraction"),
            },
        },
    )
    db.add(disease_version)
    db.flush()

    for chunk in chunks:
        db.add(
            DiseaseSourceEvidence(
                disease_version_id=disease_version.id,
                chunk_id=chunk.id,
                page_number=chunk.page_start,
                evidence_text=chunk.text[: settings.max_evidence_text_chars],
            )
        )

    db.add(
        DiagnosisOption(
            disease_version_id=disease_version.id,
            label=disease_version.name,
            match_type="exact",
        )
    )
    for alias in aliases:
        db.add(
            DiagnosisOption(
                disease_version_id=disease_version.id,
                label=alias,
                match_type="synonym",
            )
        )
    db.flush()

    rubric_result = router.generate(
        "rubric_extraction",
        LLMRequest(
            system=rubric_prompts.SYSTEM_PROMPT,
            user=rubric_prompts.build_user_content(disease_version, chunks),
            schema_model=RubricExtractionResult,
            max_tokens=rubric_prompts.MAX_TOKENS,
            prompt_version=rubric_prompts.PROMPT_VERSION,
        ),
    )
    _create_rubric_items(db, disease_version.id, rubric_result.items)

    issues = validate_disease_content(
        profile=profile,
        rubric_items=rubric_result.items,
        evidence_count=len(chunks),
        page_count=page_count,
    )

    source_summary = dict(disease_version.source_summary or {})
    source_summary["validation"] = {
        "passed": not issues,
        "issues": [{"code": issue.code, "detail": issue.detail} for issue in issues],
    }
    disease_version.source_summary = source_summary
    disease_version.status = "published" if not issues else "draft"

    db.commit()
    logger.info(
        "disease_version_processed",
        disease_version_id=str(disease_version.id),
        disease=canonical,
        status=disease_version.status,
        rubric_items=len(rubric_result.items),
        evidence=len(chunks),
    )
    return disease_version


def _create_rubric_items(db, disease_version_id: uuid.UUID, drafts) -> list[RubricItem]:
    settings = get_settings()
    seen: set[str] = set()
    items: list[RubricItem] = []
    for draft in drafts:
        question = draft.question_text.strip()
        key = question.lower()
        if not question or key in seen:
            continue
        seen.add(key)
        items.append(
            RubricItem(
                disease_version_id=disease_version_id,
                category=draft.category.value,
                question_text=question,
                rationale=draft.rationale or None,
                weight=draft.weight,
                critical=draft.critical,
            )
        )

    if items:
        vectors = embed_texts([item.question_text for item in items])
        if vectors is not None:
            for item, vector in zip(items, vectors):
                item.embedding = vector
                item.embedding_model = settings.embedding_model
                item.embedding_version = EMBEDDING_VERSION

    for item in items:
        db.add(item)
    db.flush()
    return items

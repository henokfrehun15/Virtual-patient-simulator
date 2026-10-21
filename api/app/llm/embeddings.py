import httpx

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger("app.llm.embeddings")

BATCH_SIZE = 64
REQUEST_TIMEOUT_SECONDS = 60


class EmbeddingProvider:
    provider_name = "openai_compatible"

    def __init__(self, *, base_url: str, api_key: str, model: str, dimensions: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            try:
                response = httpx.post(
                    f"{self._base_url}/embeddings",
                    json={"model": self._model, "input": batch},
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPError as exc:
                raise AppError(
                    "EMBEDDING_PROVIDER_ERROR",
                    f"Embedding provider request failed: {exc!r}",
                    status_code=502,
                ) from exc

            data = payload.get("data") or []
            if len(data) != len(batch):
                raise AppError(
                    "EMBEDDING_PROVIDER_ERROR",
                    "Embedding provider returned a mismatched number of vectors.",
                    status_code=502,
                )
            for item in sorted(data, key=lambda entry: entry.get("index", 0)):
                embedding = item.get("embedding")
                if not isinstance(embedding, list) or len(embedding) != self._dimensions:
                    raise AppError(
                        "EMBEDDING_DIMENSION_MISMATCH",
                        (
                            f"Embedding provider returned {len(embedding) if isinstance(embedding, list) else 'unknown'} "
                            f"dimensions, expected {self._dimensions}."
                        ),
                        status_code=502,
                    )
                results.append(embedding)
        return results


def get_embedding_provider() -> EmbeddingProvider | None:
    settings = get_settings()
    if (
        not settings.embedding_base_url
        or not settings.embedding_api_key
        or not settings.embedding_model
    ):
        return None
    return EmbeddingProvider(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    if not texts:
        return []
    provider = get_embedding_provider()
    if provider is None:
        logger.info("embeddings_skipped_not_configured", count=len(texts))
        return None
    return provider.embed_texts(texts)

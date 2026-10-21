from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Virtual Patient Simulator"
    app_env: str = "development"

    database_url: str = "postgresql+psycopg://vps:vps@localhost:5432/vps"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 2592000

    anthropic_api_key: str = "replace-me"
    llm_extraction_model: str = ""
    llm_scenario_model: str = ""
    llm_patient_model: str = ""
    llm_scoring_model: str = ""
    llm_feedback_model: str = ""
    llm_timeout_seconds: float = 120
    llm_max_retries: int = 2

    embedding_model: str = ""
    embedding_dimensions: int = 1536
    embedding_base_url: str = ""
    embedding_api_key: str = ""

    cors_origins: str = "http://localhost:5173"

    max_pdf_size_mb: int = 50
    max_pdf_pages: int = 300
    max_session_turns: int = 40

    storage_root: str = "storage"
    upload_rate_limit_count: int = 5
    upload_rate_limit_window_seconds: int = 3600
    chunk_target_chars: int = 1200
    chunk_overlap_chars: int = 150
    ocr_min_text_chars: int = 40
    ocr_dpi: int = 150
    discovery_chunks_per_call: int = 40
    max_diseases_per_material: int = 50
    profile_chunks_per_disease: int = 20
    max_evidence_text_chars: int = 2000
    scenario_difficulties: str = "easy,medium,hard"
    scenario_estimated_duration_minutes: int = 15

    object_storage_endpoint: str = ""
    object_storage_bucket: str = ""
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

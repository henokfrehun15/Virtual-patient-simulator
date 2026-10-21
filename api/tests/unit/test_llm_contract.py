import pytest

from app.core.errors import AppError
from app.llm.router import LLMRequest, LLMRouter, build_json_schema, extract_json
from app.llm.schemas import DiseaseDiscoveryResult, DiscoveredDisease


class StubProvider:
    provider_name = "stub"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict] = []

    def complete(self, *, model, system, user, max_tokens, json_schema):
        self.calls.append(
            {
                "model": model,
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "json_schema": json_schema,
            }
        )
        return self.text, 10, 20


def test_extract_json_plain() -> None:
    assert extract_json('{"diseases": []}') == {"diseases": []}


def test_extract_json_fenced() -> None:
    text = 'Here is the result:\n```json\n{"diseases": [{"name": "Pneumonia"}]}\n```\nDone.'
    assert extract_json(text) == {"diseases": [{"name": "Pneumonia"}]}


def test_extract_json_with_surrounding_text() -> None:
    text = 'The model replied with {"diseases": []} as requested.'
    assert extract_json(text) == {"diseases": []}


def test_extract_json_invalid_raises() -> None:
    with pytest.raises(AppError) as exc_info:
        extract_json("no json here at all")
    assert exc_info.value.code == "LLM_SCHEMA_INVALID"


def test_build_json_schema_is_strict() -> None:
    schema = build_json_schema(DiseaseDiscoveryResult)

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"diseases"}
    disease_schema = schema["$defs"]["DiscoveredDisease"]
    assert disease_schema["additionalProperties"] is False
    assert set(disease_schema["required"]) == {"name", "source_pages", "mention_context"}


def test_router_generate_parses_and_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.llm import router as router_module

    monkeypatch.setattr(router_module, "_record_llm_request", lambda **kwargs: None)
    monkeypatch.setattr(
        router_module, "get_settings", lambda: type("S", (), {
            "llm_extraction_model": "test-model",
            "llm_scenario_model": "",
            "llm_patient_model": "",
            "llm_scoring_model": "",
            "llm_feedback_model": "",
        })(),
    )

    provider = StubProvider('{"diseases": [{"name": "Pneumonia", "source_pages": [1]}]}')
    router = LLMRouter(provider)  # type: ignore[arg-type]

    result = router.generate(
        "disease_extraction",
        LLMRequest(
            system="system",
            user="user",
            schema_model=DiseaseDiscoveryResult,
            prompt_version="disease_discovery:v1",
        ),
    )

    assert isinstance(result, DiseaseDiscoveryResult)
    assert result.diseases[0].name == "Pneumonia"
    assert provider.calls[0]["model"] == "test-model"
    assert provider.calls[0]["json_schema"]["additionalProperties"] is False


def test_router_rejects_schema_invalid_output(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.llm import router as router_module

    monkeypatch.setattr(router_module, "_record_llm_request", lambda **kwargs: None)
    monkeypatch.setattr(
        router_module, "get_settings", lambda: type("S", (), {
            "llm_extraction_model": "test-model",
            "llm_scenario_model": "",
            "llm_patient_model": "",
            "llm_scoring_model": "",
            "llm_feedback_model": "",
        })(),
    )

    provider = StubProvider('{"diseases": [{"bogus": true}]}')
    router = LLMRouter(provider)  # type: ignore[arg-type]

    with pytest.raises(AppError) as exc_info:
        router.generate(
            "disease_extraction",
            LLMRequest(
                system="system",
                user="user",
                schema_model=DiseaseDiscoveryResult,
                prompt_version="disease_discovery:v1",
            ),
        )
    assert exc_info.value.code == "LLM_SCHEMA_INVALID"


def test_router_requires_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.llm import router as router_module

    class EmptySettings:
        llm_extraction_model = ""
        llm_scenario_model = ""
        llm_patient_model = ""
        llm_scoring_model = ""
        llm_feedback_model = ""

    monkeypatch.setattr(router_module, "get_settings", lambda: EmptySettings())

    router = LLMRouter(StubProvider("{}"))  # type: ignore[arg-type]
    with pytest.raises(AppError) as exc_info:
        router.model_for_task("disease_extraction")
    assert exc_info.value.code == "LLM_NOT_CONFIGURED"

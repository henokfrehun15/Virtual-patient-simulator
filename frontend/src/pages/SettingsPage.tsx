import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getLLMSettings,
  testLLMConnection,
  updateLLMSettings,
  type LLMProvider,
  type LLMSettings,
  type ModelTestResult,
} from "../api/settings";

const MODEL_FIELDS: Array<{ key: keyof LLMSettings; label: string; hint: string }> = [
  { key: "extraction_model", label: "Extraction model", hint: "disease profiles, rubrics, scoring" },
  { key: "scenario_model", label: "Scenario model", hint: "patient case generation" },
  { key: "patient_model", label: "Patient model", hint: "patient roleplay responses" },
  { key: "scoring_model", label: "Scoring model", hint: "rubric matching, diagnosis normalization" },
  { key: "feedback_model", label: "Feedback model", hint: "report narratives" },
];

const PROVIDER_INFO: Record<
  LLMProvider,
  {
    name: string;
    blurb: string;
    keyLabel: string;
    keyPlaceholder: string;
    keyHint: string;
    modelPlaceholder: string;
    recommended: Record<string, string>;
    alternatives: string;
  }
> = {
  anthropic: {
    name: "Anthropic",
    blurb: "Claude models — strongest reasoning for clinical extraction",
    keyLabel: "Anthropic API key",
    keyPlaceholder: "sk-ant-…",
    keyHint: "console.anthropic.com",
    modelPlaceholder: "e.g. claude-sonnet-4-5",
    recommended: {
      extraction_model: "claude-sonnet-4-5",
      scenario_model: "claude-sonnet-4-5",
      patient_model: "claude-sonnet-4-5",
      scoring_model: "claude-sonnet-4-5",
      feedback_model: "claude-sonnet-4-5",
    },
    alternatives: "claude-haiku-4-5 (faster, cheaper)",
  },
  groq: {
    name: "Groq",
    blurb: "LPU inference — extremely fast streaming, generous free tier",
    keyLabel: "Groq API key",
    keyPlaceholder: "gsk_…",
    keyHint: "console.groq.com",
    modelPlaceholder: "e.g. openai/gpt-oss-120b",
    recommended: {
      extraction_model: "openai/gpt-oss-120b",
      scenario_model: "openai/gpt-oss-120b",
      patient_model: "openai/gpt-oss-120b",
      scoring_model: "openai/gpt-oss-120b",
      feedback_model: "openai/gpt-oss-120b",
    },
    alternatives: "openai/gpt-oss-20b (faster), qwen/qwen3.8-27b, allam-2-7b",
  },
};

export function SettingsPage() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["settings", "llm"],
    queryFn: getLLMSettings,
  });

  const [provider, setProvider] = useState<LLMProvider>("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [models, setModels] = useState<Record<string, string>>({});
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<ModelTestResult[] | null>(null);

  useEffect(() => {
    if (settingsQuery.data !== undefined) {
      setProvider(settingsQuery.data.provider);
      const initial: Record<string, string> = {};
      for (const field of MODEL_FIELDS) {
        initial[field.key] = (settingsQuery.data[field.key] as string) ?? "";
      }
      setModels(initial);
    }
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const update: Record<string, string | boolean> = { provider };
      for (const [key, value] of Object.entries(models)) {
        update[key] = value;
      }
      if (apiKey.trim() !== "") {
        update.api_key = apiKey.trim();
      }
      return updateLLMSettings(update);
    },
    onSuccess: () => {
      setApiKey("");
      setSaveMessage("Settings saved.");
      setTestResults(null);
      void queryClient.invalidateQueries({ queryKey: ["settings", "llm"] });
    },
    onError: (err) =>
      setSaveMessage(err instanceof Error ? err.message : "Failed to save settings."),
  });

  const testMutation = useMutation({
    mutationFn: testLLMConnection,
    onSuccess: (data) => setTestResults(data.results),
    onError: (err) =>
      setSaveMessage(err instanceof Error ? err.message : "Connection test failed."),
  });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    saveMutation.mutate();
  };

  if (settingsQuery.isLoading) {
    return (
      <main className="page">
        <p className="muted">Loading…</p>
      </main>
    );
  }
  if (settingsQuery.isError || settingsQuery.data === undefined) {
    return (
      <main className="page">
        <p className="error">Could not load settings.</p>
      </main>
    );
  }

  const settings = settingsQuery.data;
  const info = PROVIDER_INFO[provider];
  const providerChanged = provider !== settings.provider;

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1>AI provider settings</h1>
          <p className="muted">
            Pick a provider, paste your API key, and set model names. Your key is
            encrypted at rest and never sent back to the browser.
          </p>
        </div>
      </header>

      <form className="card settings-card" onSubmit={handleSubmit}>
        <h2>Provider</h2>
        <div className="provider-picker">
          {(Object.keys(PROVIDER_INFO) as LLMProvider[]).map((key) => {
            const item = PROVIDER_INFO[key];
            const selected = provider === key;
            return (
              <button
                type="button"
                key={key}
                className={`provider-option${selected ? " provider-option-selected" : ""}`}
                onClick={() => setProvider(key)}
              >
                <span className="provider-name">{item.name}</span>
                <span className="provider-blurb">{item.blurb}</span>
              </button>
            );
          })}
        </div>
        {providerChanged && (
          <p className="callout">
            Switching provider clears your saved key — paste a {info.name} key below.
          </p>
        )}

        <h2>API key</h2>
        <p className="muted">
          {settings.api_key_set && !providerChanged
            ? `A ${info.name} key is configured (${
                settings.api_key_source === "user" ? "your saved key" : "server environment"
              }). Enter a new key to replace it.`
            : providerChanged
              ? `No ${info.name} key saved yet for this provider.`
              : "No key configured yet."}
        </p>
        <label>
          {info.keyLabel}
          <span className="muted"> {info.keyHint}</span>
          <input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder={
              settings.api_key_set && !providerChanged
                ? `${info.keyPlaceholder} (saved — leave blank to keep)`
                : info.keyPlaceholder
            }
            autoComplete="off"
          />
        </label>

        <div className="models-header">
          <h2>Models</h2>
          <button
            type="button"
            className="btn-ghost"
            onClick={() => setModels({ ...info.recommended })}
          >
            Use recommended
          </button>
        </div>
        {MODEL_FIELDS.map((field) => (
          <label key={field.key}>
            {field.label}
            <span className="muted"> {field.hint}</span>
            <input
              value={models[field.key] ?? ""}
              onChange={(event) =>
                setModels((previous) => ({ ...previous, [field.key]: event.target.value }))
              }
              placeholder={info.modelPlaceholder}
            />
          </label>
        ))}
        <p className="muted">
          Popular {info.name} models: {info.recommended.patient_model}, {info.alternatives}
        </p>

        {saveMessage !== null && <p className="muted">{saveMessage}</p>}

        <div className="settings-actions">
          <button type="submit" disabled={saveMutation.isPending}>
            {saveMutation.isPending ? "Saving…" : "Save settings"}
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={testMutation.isPending}
            onClick={() => testMutation.mutate()}
          >
            {testMutation.isPending ? "Testing…" : "Test connection"}
          </button>
        </div>

        {testResults !== null && (
          <div className="test-results">
            {testResults.map((result) => (
              <div key={result.model} className="test-result">
                <span className={`badge ${result.ok ? "badge-published" : "badge-failed"}`}>
                  {result.ok ? "OK" : "FAILED"}
                </span>
                <span>{result.model}</span>
                {result.error !== null && <span className="muted">{result.error}</span>}
              </div>
            ))}
          </div>
        )}
      </form>

      <p className="muted settings-footer-note">
        Keys are encrypted with Fernet before storage. Need a Groq key? Create one free at{" "}
        <a href="https://console.groq.com/keys" target="_blank" rel="noreferrer">
          console.groq.com
        </a>
        .{" "}
        <Link to="/progress">Back to progress</Link>
      </p>
    </main>
  );
}

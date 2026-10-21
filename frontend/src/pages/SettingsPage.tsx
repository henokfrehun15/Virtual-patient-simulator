import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getLLMSettings,
  testLLMConnection,
  updateLLMSettings,
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

export function SettingsPage() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["settings", "llm"],
    queryFn: getLLMSettings,
  });

  const [apiKey, setApiKey] = useState("");
  const [models, setModels] = useState<Record<string, string>>({});
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<ModelTestResult[] | null>(null);

  useEffect(() => {
    if (settingsQuery.data !== undefined) {
      const initial: Record<string, string> = {};
      for (const field of MODEL_FIELDS) {
        initial[field.key] = (settingsQuery.data[field.key] as string) ?? "";
      }
      setModels(initial);
    }
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const update: Record<string, string | boolean> = {};
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

  return (
    <main className="page">
      <nav className="top-nav">
        <Link to="/">Dashboard</Link>
        <span>Settings</span>
      </nav>
      <header className="page-header">
        <div>
          <h1>AI provider settings</h1>
          <p className="muted">
            Create an API key in the Anthropic Console, paste it here, and set the model
            names. Your key is encrypted at rest and never sent back to the browser.
          </p>
        </div>
      </header>

      <form className="card settings-card" onSubmit={handleSubmit}>
        <h2>API key</h2>
        <p className="muted">
          {settings.api_key_set
            ? `A key is configured (${settings.api_key_source === "user" ? "your saved key" : "server environment"}). Enter a new key to replace it.`
            : "No key configured yet."}
        </p>
        <label>
          Anthropic API key
          <input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder={
              settings.api_key_set ? "sk-ant-… (saved — leave blank to keep)" : "sk-ant-…"
            }
            autoComplete="off"
          />
        </label>

        <h2>Models</h2>
        {MODEL_FIELDS.map((field) => (
          <label key={field.key}>
            {field.label}
            <span className="muted"> {field.hint}</span>
            <input
              value={models[field.key] ?? ""}
              onChange={(event) =>
                setModels((previous) => ({ ...previous, [field.key]: event.target.value }))
              }
              placeholder="e.g. claude-sonnet-4-5"
            />
          </label>
        ))}

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
    </main>
  );
}

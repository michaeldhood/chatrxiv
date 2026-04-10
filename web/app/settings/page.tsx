"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchSettings,
  postIngest,
  type IngestMode,
  type IngestionSourceInfo,
  type SettingsResponse,
} from "@/lib/api";
import { useToast } from "@/components/toast";

const SOURCE_LABELS: Record<string, string> = {
  cursor: "Cursor",
  "claude.ai": "Claude.ai",
  chatgpt: "ChatGPT",
  "claude-code": "Claude Code",
};

function formatBytes(bytes?: number | null): string {
  if (bytes == null) return "Not available";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatTimestamp(value?: string | null): string {
  if (!value) return "Never";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function SourceStatusCard({ source }: { source: IngestionSourceInfo }) {
  const label = SOURCE_LABELS[source.source] || source.source;

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-foreground">{label}</h3>
        <span className="rounded-full bg-primary/10 px-2 py-1 text-[11px] font-medium text-primary">
          {source.stats_ingested} ingested
        </span>
      </div>

      <dl className="space-y-2 text-sm">
        <div className="flex justify-between gap-4">
          <dt className="text-muted-foreground">Last run</dt>
          <dd className="text-right text-foreground">
            {formatTimestamp(source.last_run_at)}
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-muted-foreground">Skipped</dt>
          <dd className="text-right text-foreground">{source.stats_skipped}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-muted-foreground">Errors</dt>
          <dd className="text-right text-foreground">{source.stats_errors}</dd>
        </div>
      </dl>
    </div>
  );
}

export default function SettingsPage() {
  const { showToast } = useToast();
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [ingestMode, setIngestMode] = useState<IngestMode>("incremental");
  const [selectedSources, setSelectedSources] = useState<string[]>([
    "cursor",
    "claude-code",
  ]);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchSettings();
      setSettings(response);
    } catch (error) {
      showToast({
        variant: "error",
        title: "Settings unavailable",
        description:
          error instanceof Error ? error.message : "Failed to load settings.",
      });
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    if (!settings?.runtime.manual_ingest.running) return;

    const interval = window.setInterval(() => {
      void loadSettings();
    }, 2500);

    return () => window.clearInterval(interval);
  }, [loadSettings, settings?.runtime.manual_ingest.running]);

  const availableSources = useMemo(() => {
    return settings?.ingestion.map((source) => source.source) ?? [
      "cursor",
      "claude-code",
      "claude.ai",
      "chatgpt",
    ];
  }, [settings?.ingestion]);

  const toggleSource = (source: string) => {
    setSelectedSources((current) =>
      current.includes(source)
        ? current.filter((item) => item !== source)
        : [...current, source]
    );
  };

  const handleIngest = async () => {
    const sources = selectedSources.length > 0 ? selectedSources : ["cursor"];

    try {
      const response = await postIngest({ mode: ingestMode, sources });
      showToast({
        variant: "success",
        title: "Ingestion started",
        description: `${response.sources.join(", ")} (${response.mode})`,
      });
      await loadSettings();
    } catch (error) {
      showToast({
        variant: "error",
        title: "Ingestion failed to start",
        description:
          error instanceof Error ? error.message : "Unable to trigger ingestion.",
      });
    }
  };

  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <p className="text-muted-foreground">Loading settings...</p>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <p className="text-muted-foreground">Settings could not be loaded.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-border bg-card p-6">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Database</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-border bg-muted/30 p-4">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              chats.db
            </p>
            <p className="break-all font-mono text-sm text-foreground">
              {settings.database.chats_db_path}
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              Size: {formatBytes(settings.database.chats_db_size_bytes)}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-muted/30 p-4">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              raw.db
            </p>
            <p className="break-all font-mono text-sm text-foreground">
              {settings.database.raw_db_path}
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              Size: {formatBytes(settings.database.raw_db_size_bytes)}
            </p>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-border bg-card p-6">
        <div className="mb-4 flex items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-foreground">Manual ingestion</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Trigger a background refresh from the configured sources.
            </p>
          </div>
          <button
            onClick={handleIngest}
            disabled={settings.runtime.manual_ingest.running}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {settings.runtime.manual_ingest.running ? "Ingestion running..." : "Run ingestion"}
          </button>
        </div>

        <div className="mb-4 flex flex-wrap gap-4">
          <label className="text-sm text-foreground">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Mode
            </span>
            <select
              value={ingestMode}
              onChange={(event) => setIngestMode(event.target.value as IngestMode)}
              className="rounded-md border border-border bg-muted px-3 py-2 text-sm text-foreground"
            >
              <option value="incremental">Incremental</option>
              <option value="full">Full</option>
            </select>
          </label>
        </div>

        <div className="mb-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Sources
          </p>
          <div className="flex flex-wrap gap-2">
            {availableSources.map((source) => {
              const active = selectedSources.includes(source);
              return (
                <button
                  key={source}
                  onClick={() => toggleSource(source)}
                  className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                    active
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {SOURCE_LABELS[source] || source}
                </button>
              );
            })}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-muted/30 p-4 text-sm">
          <p className="font-medium text-foreground">
            Runtime state:{" "}
            {settings.runtime.manual_ingest.running ? "Running" : "Idle"}
          </p>
          <p className="mt-1 text-muted-foreground">
            Started: {formatTimestamp(settings.runtime.manual_ingest.started_at)}
          </p>
          <p className="mt-1 text-muted-foreground">
            Finished: {formatTimestamp(settings.runtime.manual_ingest.finished_at)}
          </p>
          {settings.runtime.manual_ingest.last_error && (
            <p className="mt-2 text-destructive">
              Error: {settings.runtime.manual_ingest.last_error}
            </p>
          )}
        </div>
      </section>

      <section className="rounded-xl border border-border bg-card p-6">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Configured source paths</h2>
        <div className="space-y-3">
          {settings.settings.map(({ key, value }) => (
            <div
              key={key}
              className="rounded-lg border border-border bg-muted/30 p-4"
            >
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {key}
              </p>
              <p className="break-all font-mono text-sm text-foreground">
                {typeof value === "string" ? value : JSON.stringify(value)}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="text-xl font-semibold text-foreground">Source status</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Last known ingestion timestamps and counts for each source.
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {settings.ingestion.map((source) => (
            <SourceStatusCard key={source.source} source={source} />
          ))}
        </div>
      </section>
    </div>
  );
}

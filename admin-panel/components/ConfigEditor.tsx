"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowCounterClockwise, DownloadSimple, Eye, FloppyDisk, UploadSimple,
} from "@phosphor-icons/react";
import {
  downloadConfigJson, fetchConfig, saveConfig, uploadConfigFile,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const DOWNLOAD_NAMES: Record<string, string> = {
  "goal-options": "goal_options.json",
  "meal-plan-templates": "meal_plan_templates.json",
  "workout-plan-rules": "workout_plan_rules.json",
  "alternative-meals": "alternative_meals.json",
};

type ConfigEditorProps = {
  configKey: string;
  title: string;
  subtitle: string;
  toast: (message: string) => void;
  onPreview?: (data: Record<string, unknown>) => void;
};

export default function ConfigEditor({
  configKey,
  title,
  subtitle,
  toast,
  onPreview,
}: ConfigEditorProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [savedText, setSavedText] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [lastModifiedAt, setLastModifiedAt] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetchConfig(configKey);
      const formatted = JSON.stringify(response.data, null, 2);
      setText(formatted);
      setSavedText(formatted);
      setLastModifiedAt(response.lastModifiedAt);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load config");
    } finally {
      setLoading(false);
    }
  }, [configKey]);

  useEffect(() => {
    load();
  }, [load]);

  const parseJson = () => {
    try {
      return JSON.parse(text) as Record<string, unknown>;
    } catch {
      throw new Error("Invalid JSON — fix syntax errors before saving");
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      const data = parseJson();
      const result = await saveConfig(configKey, data);
      const formatted = JSON.stringify(data, null, 2);
      setText(formatted);
      setSavedText(formatted);
      setLastModifiedAt(result.lastModifiedAt);
      toast(`${title} saved`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handlePreview = () => {
    setError("");
    try {
      const data = parseJson();
      onPreview?.(data);
      toast("Preview updated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preview failed");
    }
  };

  const handleDownload = () => {
    setError("");
    try {
      const data = parseJson();
      downloadConfigJson(DOWNLOAD_NAMES[configKey] ?? `${configKey}.json`, data);
      toast("JSON downloaded");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    }
  };

  const handleUpload = async (file: File | null) => {
    if (!file) return;
    if (!file.name.endsWith(".json")) {
      setError("Please upload a .json file");
      return;
    }

    setUploading(true);
    setError("");
    try {
      await uploadConfigFile(configKey, file);
      await load();
      toast(`Replaced with ${file.name}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const dirty = text !== savedText;

  return (
    <section className="card config-editor">
      <div className="config-head">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        <div className="config-actions">
          {lastModifiedAt && (
            <span className="config-modified">Last modified {formatDateTime(lastModifiedAt)}</span>
          )}
          <button className="secondary" type="button" onClick={load} disabled={loading || uploading}>
            <ArrowCounterClockwise /> Reload
          </button>
          <button className="secondary" type="button" onClick={handleDownload} disabled={loading}>
            <DownloadSimple /> Download
          </button>
          {onPreview && (
            <button className="secondary" type="button" onClick={handlePreview}>
              <Eye /> Preview
            </button>
          )}
          <button
            className="primary"
            type="button"
            onClick={handleSave}
            disabled={saving || loading || uploading || !dirty}
          >
            <FloppyDisk /> {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>

      <label className="config-upload-zone">
        <UploadSimple />
        <strong>{uploading ? "Uploading…" : "Replace entire config from JSON file"}</strong>
        <span>Drop or click to upload — overwrites {DOWNLOAD_NAMES[configKey] ?? "config"} on disk</span>
        <input
          ref={fileInputRef}
          type="file"
          accept=".json,application/json"
          disabled={uploading}
          onChange={(e) => handleUpload(e.target.files?.[0] ?? null)}
        />
      </label>

      {error && <div className="config-error">{error}</div>}

      {loading ? (
        <div className="config-loading">Loading {title.toLowerCase()}…</div>
      ) : (
        <textarea
          className="config-textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
        />
      )}

      {dirty && <p className="config-dirty">Unsaved changes</p>}
    </section>
  );
}

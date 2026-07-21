"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  ArrowRight, Barbell, Bell, Brain, Check, DownloadSimple, FileArrowUp, ForkKnife,
  ListChecks, MagnifyingGlass, ShieldCheck, SidebarSimple, Sparkle, SquaresFour,
  UploadSimple, X,
} from "@phosphor-icons/react";
import ExercisesPage from "@/components/ExercisesPage";
import MealPlansPage from "@/components/MealPlansPage";
import MealsPage from "@/components/MealsPage";
import OverviewPage from "@/components/OverviewPage";
import {
  downloadModel, fetchModels, formatBytes, uploadModel,
  type ModelInfo,
} from "@/lib/api";

const nav = [
  ["Overview", SquaresFour],
  ["Exercises", Barbell],
  ["Models", Brain],
  ["Meals", ForkKnife],
  ["Meal plans", ListChecks],
] as const;

export default function AdminShell() {
  const [active, setActive] = useState("Overview");
  const [sidebar, setSidebar] = useState(false);
  const [notice, setNotice] = useState("");

  const toast = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(""), 2600);
  };

  const renderPage = () => {
    if (active === "Overview") {
      return <OverviewPage toast={toast} onNavigate={setActive} />;
    }
    if (active === "Exercises") return <ExercisesPage toast={toast} />;
    if (active === "Models") return <ModelsPage toast={toast} />;
    if (active === "Meals") return <MealsPage toast={toast} />;
    if (active === "Meal plans") return <MealPlansPage toast={toast} />;
    return null;
  };

  return (
    <div className="app-shell">
      <aside className={sidebar ? "sidebar open" : "sidebar"}>
        <div className="brand"><div className="brand-mark"><Sparkle weight="fill" /></div><span>FitVision</span><b>CONTROL</b></div>
        <button className="mobile-close" onClick={() => setSidebar(false)}><X /></button>
        <p className="nav-label">Workspace</p>
        <nav>{nav.map(([label, Icon]) => <button key={label} className={active === label ? "active" : ""} onClick={() => {setActive(label); setSidebar(false)}}><Icon weight={active === label ? "fill" : "regular"}/><span>{label}</span></button>)}</nav>
        <div className="sidebar-foot">
          <div className="profile"><div className="avatar">AK</div><div><strong>Ali Khan</strong><span>Administrator</span></div><button>•••</button></div>
        </div>
      </aside>

      <main>
        <header>
          <button className="menu" onClick={() => setSidebar(true)}><SidebarSimple /></button>
          <div className="search"><MagnifyingGlass/><input aria-label="Search" placeholder="Search models, meals, users..."/><kbd>⌘ K</kbd></div>
          <div className="header-actions"><button className="icon-btn"><Bell/><i /></button><span className="env"><i/>Production</span></div>
        </header>
        <div className="content">{renderPage()}</div>
      </main>
      {notice && <div className="toast"><Check weight="bold"/>{notice}</div>}
    </div>
  );
}

type ModelSlot = "exercise-rep" | "equipment";

const SLOT_LABELS: Record<ModelSlot, string> = {
  "exercise-rep": "Exercise Rep",
  equipment: "Equipment",
};

function ModelsPage({ toast }: { toast: (s: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [slot, setSlot] = useState<ModelSlot>("exercise-rep");
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const loadModels = async () => {
    setLoading(true);
    try {
      const result = await fetchModels();
      setModels(result.models);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to load models");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadModels();
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) {
      toast("Choose a model file to upload");
      return;
    }
    setUploading(true);
    try {
      await uploadModel(slot, file);
      setFile(null);
      const input = document.getElementById("model-file") as HTMLInputElement | null;
      if (input) input.value = "";
      toast(`${SLOT_LABELS[slot]} model uploaded to backend`);
      await loadModels();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const modelMap = Object.fromEntries(models.map((m) => [m.slot, m]));

  return <>
    <div className="page-title compact"><div><span className="eyebrow">MODEL DEPLOYMENT</span><h1>Production model slots</h1><p>Upload replaces the artifact on the backend server. Download fetches the current deployed file.</p></div></div>
    <div className="models-workspace">
      <form className="card upload-panel" onSubmit={submit}>
        <div className="form-heading"><div className="empty-icon"><FileArrowUp weight="fill"/></div><div><h2>Replace a model</h2><p>Files are saved to the backend <code>weights/</code> directory.</p></div></div>
        <label><span>Model type *</span><select value={slot} onChange={e => setSlot(e.target.value as ModelSlot)}><option value="exercise-rep">Exercise Rep</option><option value="equipment">Equipment</option></select></label>
        <label className="drop-zone" htmlFor="model-file"><UploadSimple/><strong>{file ? file.name : "Choose model artifact"}</strong><span>{file ? formatBytes(file.size) : ".keras, .pt, .tflite, .task, .pkl, .onnx"}</span><input id="model-file" type="file" accept=".tflite,.pkl,.pt,.pth,.onnx,.zip,.task,.keras" onChange={e => setFile(e.target.files?.[0] || null)}/></label>
        <button className="primary submit-model" type="submit" disabled={uploading || !file}><UploadSimple/>{uploading ? "Uploading…" : `Replace ${SLOT_LABELS[slot]} model`}</button>
      </form>

      <section className="card registry-panel">
        <CardHead title="Current production models" subtitle="Deployed artifacts on the backend server"/>
        {loading ? <div className="config-loading">Loading models…</div> : (["exercise-rep", "equipment"] as ModelSlot[]).map((modelSlot, index) => {
          const item = modelMap[modelSlot];
          return <article className="artifact-row model-slot" key={modelSlot}>
            <div className="slot-heading"><span className="slot-name">{SLOT_LABELS[modelSlot]}</span><span className={`pill ${item?.size_bytes ? "live" : "draft"}`}><i/>{item?.size_bytes ? "Deployed" : "Missing"}</span></div>
            <div className="artifact-top"><div className={`model-icon m${index + 1}`}><Brain weight="fill"/></div><div><strong>{item?.label ?? SLOT_LABELS[modelSlot]}</strong><span>{item?.filename ?? "No file"} · {item?.size_bytes ? formatBytes(item.size_bytes) : "—"}</span></div>
              {item?.size_bytes ? <button type="button" className="download-btn" onClick={async () => {
                try {
                  await downloadModel(modelSlot, item.filename);
                } catch {
                  toast("Download failed — check admin key");
                }
              }}><DownloadSimple/>Download</button> : null}
            </div>
          </article>;
        })}
        <div className="replacement-note"><ShieldCheck/><div><strong>Backend storage</strong><span>Uploads go to <code>weights/</code> on the FastAPI server.</span></div></div>
      </section>
    </div>
  </>;
}

function CardHead({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="card-head">
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
    </div>
  );
}

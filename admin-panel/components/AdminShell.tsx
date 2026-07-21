"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  ArrowRight, Barbell, Bell, Brain, Check, DownloadSimple, FileArrowUp, ForkKnife, Gauge, Key,
  ListChecks, MagnifyingGlass, Plus, RocketLaunch, ShieldCheck, SidebarSimple, Sparkle,
  SquaresFour, UploadSimple, X,
} from "@phosphor-icons/react";
import { meals, models } from "@/lib/data";
import ExercisesPage from "@/components/ExercisesPage";
import MealPlansPage from "@/components/MealPlansPage";
import MealsPage from "@/components/MealsPage";
import {
  downloadModel, fetchModels, formatBytes, getAdminKey, setAdminKey, uploadModel,
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
  const [adminKey, setAdminKeyState] = useState("");

  useEffect(() => {
    setAdminKeyState(getAdminKey());
  }, []);

  const toast = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(""), 2600);
  };

  const saveKey = () => {
    setAdminKey(adminKey);
    toast("Admin API key saved");
  };

  const renderPage = () => {
    if (active === "Overview") return <Overview toast={toast} />;
    if (active === "Exercises") return <ExercisesPage toast={toast} />;
    if (active === "Models") return <ModelsPage toast={toast} adminKey={adminKey} />;
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
          <div className="admin-key-box">
            <label><Key weight="fill" /><span>Admin API key</span></label>
            <input
              type="password"
              value={adminKey}
              onChange={(e) => setAdminKeyState(e.target.value)}
              placeholder="fitvision-admin-dev"
            />
            <button type="button" onClick={saveKey}>Save key</button>
          </div>
          <div className="system-status"><i /><div><strong>All systems operational</strong><span>Last checked just now</span></div></div>
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

function ModelsPage({ toast, adminKey }: { toast: (s: string) => void; adminKey: string }) {
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
        <div className="replacement-note"><ShieldCheck/><div><strong>Backend storage</strong><span>Uploads go to <code>weights/</code> on the FastAPI server. Set your admin key in the sidebar before uploading.</span></div></div>
      </section>
    </div>
  </>;
}

function Overview({toast}: {toast: (s:string)=>void}) {
  return <>
    <div className="page-title"><div><span className="eyebrow">Tuesday, July 21</span><h1>Good afternoon, Ali.</h1><p>Here’s what’s happening across FitVision today.</p></div><div className="title-actions"><button className="secondary" onClick={() => toast("Open Models to upload") }><UploadSimple/>Upload model</button><button className="primary" onClick={() => toast("Open Meal plans to edit configs")}><Plus weight="bold"/>Edit meal plans</button></div></div>
    <section className="metrics">
      <Metric icon={<Brain/>} tone="violet" label="Active models" value="2" change="Backend slots" />
      <Metric icon={<ForkKnife/>} tone="green" label="Meal configs" value="4" change="JSON-driven" />
      <Metric icon={<Gauge/>} tone="orange" label="Avg. inference" value="148ms" change="8.2% faster" />
      <Metric icon={<ListChecks/>} tone="blue" label="Plan templates" value="3" change="loss / gain / general" />
    </section>
    <div className="grid-main">
      <section className="card models-card"><CardHead title="Model health" subtitle="Production performance over the last 24 hours" action="Manage models"/><div className="model-list">{models.map((m, i) => <div className="model-row" key={m.name}><div className={`model-icon m${i}`}><Brain weight="fill"/></div><div className="model-name"><strong>{m.name}</strong><span>{m.version} · {m.task}</span></div><div className="model-stat"><span>Accuracy</span><strong>{m.accuracy}</strong></div><div className="model-stat"><span>Latency</span><strong>{m.latency}</strong></div><span className={`pill ${m.status.toLowerCase()}`}><i/>{m.status}</span><button className="row-more">•••</button></div>)}</div></section>
      <section className="card activity"><CardHead title="Recent activity" subtitle="Latest workspace changes"/><div className="timeline"><Activity icon={<RocketLaunch/>} tone="violet" title="Meal plan configs moved to JSON" meta="Admin panel · Today"/><Activity icon={<ForkKnife/>} tone="green" title="Alternative meals editable" meta="Admin panel · Today"/><Activity icon={<ShieldCheck/>} tone="blue" title="Admin API connected" meta="Backend · Today"/></div><button className="text-action">View audit log <ArrowRight/></button></section>
    </div>
    <div className="grid-bottom">
      <section className="card"><CardHead title="Meals library" subtitle="Recently added and updated" action="View all meals"/><div className="meal-list">{meals.map((m, i) => <div className="meal-row" key={m.name}><div className={`meal-thumb food${i}`}>{m.image}</div><div><strong>{m.name}</strong><span>{m.category} · {m.calories} kcal · {m.protein} protein</span></div><span className={`pill ${m.status.toLowerCase()}`}>{m.status}</span></div>)}</div></section>
    </div>
  </>
}

function Metric({icon,tone,label,value,change}:{icon:React.ReactNode,tone:string,label:string,value:string,change:string}) { return <div className="metric card"><div className={`metric-icon ${tone}`}>{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{change}</small></div><div className="spark">▁▂▂▃▅▄▆▇</div></div> }
function CardHead({title,subtitle,action}:{title:string,subtitle:string,action?:string}) { return <div className="card-head"><div><h2>{title}</h2><p>{subtitle}</p></div>{action && <button>{action}<ArrowRight/></button>}</div> }
function Activity({icon,tone,title,meta}:{icon:React.ReactNode,tone:string,title:string,meta:string}) { return <div className="activity-row"><div className={`activity-icon ${tone}`}>{icon}</div><div><strong>{title}</strong><span>{meta}</span></div></div> }

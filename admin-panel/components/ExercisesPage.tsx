"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { FloppyDisk, PencilSimple, Plus, Trash } from "@phosphor-icons/react";
import {
  createExercise, deleteExercise, fetchExercises, updateExercise, type Exercise,
} from "@/lib/api";

const EMPTY_FORM = {
  title: "",
  primary_muscle: "",
  exercise_type: "Home",
  difficulty_level: "Beginner",
  equipment_required: "None",
  location_type: "Home",
  video_url: "",
  image_url: "",
  suggested_workouts: "",
  instructions: "",
  safety_tips: "",
};

export default function ExercisesPage({ toast }: { toast: (message: string) => void }) {
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setExercises(await fetchExercises());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load exercises");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const resetForm = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
  };

  const startEdit = (exercise: Exercise) => {
    setEditingId(exercise.id);
    setForm({
      title: exercise.title,
      primary_muscle: exercise.primary_muscle,
      exercise_type: exercise.exercise_type,
      difficulty_level: exercise.difficulty_level ?? "Beginner",
      equipment_required: exercise.equipment_required ?? "None",
      location_type: exercise.location_type ?? "Home",
      video_url: exercise.video_url ?? "",
      image_url: exercise.image_url ?? "",
      suggested_workouts: (exercise.suggested_workouts ?? []).join(", "),
      instructions: (exercise.instructions ?? []).join("\n"),
      safety_tips: (exercise.safety_tips ?? []).join("\n"),
    });
  };

  const buildPayload = () => ({
    title: form.title.trim(),
    primary_muscle: form.primary_muscle.trim(),
    exercise_type: form.exercise_type,
    difficulty_level: form.difficulty_level,
    equipment_required: form.equipment_required,
    location_type: form.location_type,
    video_url: form.video_url.trim() || null,
    image_url: form.image_url.trim() || null,
    suggested_workouts: form.suggested_workouts
      .split(",").map((s) => s.trim()).filter(Boolean),
    instructions: form.instructions
      .split("\n").map((s) => s.trim()).filter(Boolean),
    safety_tips: form.safety_tips
      .split("\n").map((s) => s.trim()).filter(Boolean),
  });

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.title.trim() || !form.primary_muscle.trim()) {
      setError("Title and primary muscle are required");
      return;
    }

    setSaving(true);
    setError("");
    try {
      const payload = buildPayload();
      if (editingId) {
        await updateExercise(editingId, payload);
        toast("Exercise updated");
      } else {
        await createExercise(payload);
        toast("Exercise created");
      }
      resetForm();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (exercise: Exercise) => {
    if (!confirm(`Delete "${exercise.title}"?`)) return;
    setError("");
    try {
      await deleteExercise(exercise.id);
      toast("Exercise deleted");
      if (editingId === exercise.id) resetForm();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const filtered = exercises.filter((e) => {
    const q = search.toLowerCase();
    return (
      e.title.toLowerCase().includes(q) ||
      e.primary_muscle.toLowerCase().includes(q) ||
      e.exercise_type.toLowerCase().includes(q)
    );
  });

  return (
    <>
      <div className="page-title compact">
        <div>
          <span className="eyebrow">EXERCISE CATALOG</span>
          <h1>Exercises</h1>
          <p>Manage the exercise library used in workout plans.</p>
        </div>
        <button className="secondary" type="button" onClick={resetForm}>
          <Plus /> New exercise
        </button>
      </div>

      <div className="exercises-layout">
        <section className="card exercises-list-panel">
          <div className="config-head">
            <div>
              <h2>All exercises</h2>
              <p>{loading ? "Loading…" : `${filtered.length} shown`}</p>
            </div>
            <input
              className="exercise-search"
              placeholder="Search exercises…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {error && <div className="config-error">{error}</div>}

          {loading ? (
            <div className="config-loading">Loading exercises…</div>
          ) : (
            <div className="exercise-table-wrap">
              <table className="exercise-table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Muscle</th>
                    <th>Type</th>
                    <th>Equipment</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((exercise) => (
                    <tr key={exercise.id} className={editingId === exercise.id ? "active" : ""}>
                      <td><strong>{exercise.title}</strong></td>
                      <td>{exercise.primary_muscle}</td>
                      <td>{exercise.exercise_type}</td>
                      <td>{exercise.equipment_required ?? "None"}</td>
                      <td className="exercise-actions">
                        <button type="button" onClick={() => startEdit(exercise)}><PencilSimple /></button>
                        <button type="button" onClick={() => handleDelete(exercise)}><Trash /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!filtered.length && <div className="config-loading">No exercises found.</div>}
            </div>
          )}
        </section>

        <form className="card upload-panel exercise-form" onSubmit={handleSubmit}>
          <div className="form-heading">
            <div className="empty-icon"><FloppyDisk weight="fill" /></div>
            <div>
              <h2>{editingId ? "Edit exercise" : "Add exercise"}</h2>
              <p>{editingId ? "Update fields and save." : "Create a new catalog entry."}</p>
            </div>
          </div>

          <div className="form-grid">
            <label><span>Title *</span><input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required /></label>
            <label><span>Primary muscle *</span><input value={form.primary_muscle} onChange={(e) => setForm({ ...form, primary_muscle: e.target.value })} required /></label>
          </div>
          <div className="form-grid">
            <label><span>Type</span><select value={form.exercise_type} onChange={(e) => setForm({ ...form, exercise_type: e.target.value })}><option>Home</option><option>Gym</option><option>Cardio</option><option>Bodyweight</option></select></label>
            <label><span>Difficulty</span><select value={form.difficulty_level} onChange={(e) => setForm({ ...form, difficulty_level: e.target.value })}><option>Beginner</option><option>Intermediate</option><option>Advanced</option></select></label>
          </div>
          <div className="form-grid">
            <label><span>Equipment</span><input value={form.equipment_required} onChange={(e) => setForm({ ...form, equipment_required: e.target.value })} placeholder="None, Dumbbells, Barbell…" /></label>
            <label><span>Location</span><select value={form.location_type ?? "Home"} onChange={(e) => setForm({ ...form, location_type: e.target.value })}><option>Home</option><option>Gym</option><option>Both</option></select></label>
          </div>
          <label><span>Video URL</span><input value={form.video_url} onChange={(e) => setForm({ ...form, video_url: e.target.value })} placeholder="https://…" /></label>
          <label><span>Image URL</span><input value={form.image_url} onChange={(e) => setForm({ ...form, image_url: e.target.value })} placeholder="https://…" /></label>
          <label><span>Suggested workouts</span><input value={form.suggested_workouts} onChange={(e) => setForm({ ...form, suggested_workouts: e.target.value })} placeholder="Upper Body, Full Body" /><small>Comma-separated</small></label>
          <label><span>Instructions</span><textarea className="exercise-textarea" value={form.instructions} onChange={(e) => setForm({ ...form, instructions: e.target.value })} placeholder="One step per line" /></label>
          <label><span>Safety tips</span><textarea className="exercise-textarea" value={form.safety_tips} onChange={(e) => setForm({ ...form, safety_tips: e.target.value })} placeholder="One tip per line" /></label>
          <button className="primary submit-model" type="submit" disabled={saving}>
            <FloppyDisk /> {saving ? "Saving…" : editingId ? "Update exercise" : "Create exercise"}
          </button>
        </form>
      </div>
    </>
  );
}

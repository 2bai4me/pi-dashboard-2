// TaskDraft.tsx — Iterativer Task-Refinement-Workflow (User-Direktive 18.06.2026)
//
// Workflow:
//   1. User beschreibt Task
//   2. KI generiert vollstaendigen Entwurf (Title, Description, success_criteria)
//   3. User passt an (editiert Felder oder schreibt Feedback)
//   4. KI optimiert auf Basis des Feedbacks
//   5. ... (mehrfach wiederholen)
//   6. User klickt "Freigeben" -> echter Task wird erstellt
//
// Diese Page unterstuetzt BEIDE Modi:
//   - /tasks/draft (Liste aller Entwuerfe)
//   - /tasks/draft/:id (Iterativer Workflow fuer einen Entwurf)
//   - /tasks/draft/new (Neuen Entwurf starten)

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles, Send, Check, Trash2, ArrowLeft, RefreshCw, Lightbulb, X } from "lucide-react";
import { api } from "../api";

interface DraftCurrent {
  title?: string;
  description?: string;
  priority?: number;
  category?: string;
  success_criteria?: string[];
  assigned_role?: string;
  project_id?: string;
  tags?: string[];
  acceptance_criteria_explanation?: string;
}

interface DraftIteration {
  iteration: number;
  user_input: string;
  ai_output: any;
  timestamp: string;
}

interface Draft {
  id: string;
  user_input: string;
  current: DraftCurrent;
  iterations: DraftIteration[];
  status: string;
  final_task_id?: string;
  iteration_count: number;
  created_at?: string;
  updated_at?: string;
}

export default function TaskDraft() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // === Liste-Modus ===
  if (!id || id === "new") {
    return <DraftList navigate={navigate} />;
  }

  // === Edit-Modus (id vorhanden) ===
  return <DraftEdit draftId={id} navigate={navigate} queryClient={queryClient} />;
}

// =====================================================================
// DraftList — Liste aller Entwuerfe
// =====================================================================
function DraftList({ navigate }: { navigate: any }) {
  const [statusFilter, setStatusFilter] = useState<string | undefined>("draft");
  const { data, isLoading } = useQuery({
    queryKey: ["task-drafts", statusFilter],
    queryFn: () => api.taskDrafts.list(statusFilter),
  });

  return (
    <div style={{ padding: 20, maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: "0 0 4px", display: "flex", alignItems: "center", gap: 8 }}>
            <Sparkles size={20} /> Iterativer Task-Refinement
          </h2>
          <p style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12, margin: 0 }}>
            User beschreibt → KI generiert → User passt an → KI optimiert → ... → Freigeben.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate("/tasks/draft/new")}>
          <Sparkles size={14} /> Neuen Entwurf starten
        </button>
      </div>

      <div style={{ marginBottom: 16, display: "flex", gap: 6 }}>
        {[
          { value: undefined, label: "Alle" },
          { value: "draft", label: "Entwurf" },
          { value: "published", label: "Veroeffentlicht" },
          { value: "abandoned", label: "Verworfen" },
        ].map((f) => (
          <button
            key={String(f.value)}
            className={statusFilter === f.value ? "btn btn-sm btn-primary" : "btn btn-sm"}
            onClick={() => setStatusFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div style={{ color: "var(--color-hermes-text-secondary)", padding: 20 }}>Lade Entwuerfe...</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {(data?.items || []).map((d: Draft) => (
            <div
              key={d.id}
              style={{
                background: "var(--color-hermes-surface)",
                border: "1px solid var(--color-hermes-border)",
                borderRadius: 8,
                padding: 12,
                cursor: "pointer",
              }}
              onClick={() => navigate(`/tasks/draft/${d.id}`)}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>
                    {d.current?.title || d.user_input.slice(0, 80)}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>
                    {d.user_input.slice(0, 100)}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <span className={`badge ${d.status === "draft" ? "badge-blue" : d.status === "published" ? "badge-green" : "badge-gray"}`}>
                    {d.status}
                  </span>
                  <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
                    {d.iteration_count} Iter · {d.updated_at?.slice(0, 10)}
                  </div>
                </div>
              </div>
            </div>
          ))}
          {(!data?.items || data.items.length === 0) && (
            <div style={{ padding: 30, textAlign: "center", color: "var(--color-hermes-text-secondary)", fontStyle: "italic" }}>
              Keine Entwuerfe. Klicke "Neuen Entwurf starten" um zu beginnen.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// =====================================================================
// DraftEdit — Iterativer Workflow fuer einen Entwurf
// =====================================================================
function DraftEdit({ draftId, navigate, queryClient }: { draftId: string; navigate: any; queryClient: any }) {
  const { data: draft, isLoading, refetch } = useQuery({
    queryKey: ["task-draft", draftId],
    queryFn: () => api.taskDrafts.get(draftId),
  });

  const [userFeedback, setUserFeedback] = useState("");
  const [editingField, setEditingField] = useState<string | null>(null);

  const refineMutation = useMutation({
    mutationFn: (feedback: string) => api.taskDrafts.refine(draftId, feedback),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-draft", draftId] });
      setUserFeedback("");
    },
  });

  const publishMutation = useMutation({
    mutationFn: () => api.taskDrafts.publish(draftId),
    onSuccess: (resp) => {
      queryClient.invalidateQueries({ queryKey: ["task-draft", draftId] });
      queryClient.invalidateQueries({ queryKey: ["task-drafts"] });
      // Zum echten Task navigieren
      setTimeout(() => navigate(`/kanban?task=${resp.task_id}`), 500);
    },
  });

  const abandonMutation = useMutation({
    mutationFn: () => api.taskDrafts.abandon(draftId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-drafts"] });
      navigate("/tasks/draft");
    },
  });

  if (isLoading) {
    return <div style={{ padding: 20, color: "var(--color-hermes-text-secondary)" }}>Lade Entwurf...</div>;
  }
  if (!draft) {
    return <div style={{ padding: 20, color: "var(--color-hermes-danger)" }}>Draft nicht gefunden.</div>;
  }

  const cur = draft.current || {};

  return (
    <div style={{ padding: 20, maxWidth: 1000, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <button className="btn btn-sm" onClick={() => navigate("/tasks/draft")}>
          <ArrowLeft size={14} /> Zurueck zur Liste
        </button>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className={`badge ${draft.status === "draft" ? "badge-blue" : draft.status === "published" ? "badge-green" : "badge-gray"}`}>
            {draft.status}
          </span>
          <span style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
            Iteration {draft.iteration_count}
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 20 }}>
        {/* === Linke Spalte: Entwurf-Felder === */}
        <div>
          <div style={{ background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)", borderRadius: 8, padding: 16, marginBottom: 16 }}>
            <h3 style={{ margin: "0 0 12px", fontSize: 14, display: "flex", alignItems: "center", gap: 6 }}>
              <Sparkles size={14} color="#7c3aed" /> Aktueller Entwurf
            </h3>

            <DraftField
              label="Title"
              value={cur.title || ""}
              onChange={(v) => updateField(draftId, queryClient, { title: v })}
              disabled={draft.status !== "draft"}
              large
            />

            <DraftField
              label="Description"
              value={cur.description || ""}
              onChange={(v) => updateField(draftId, queryClient, { description: v })}
              disabled={draft.status !== "draft"}
              multiline
              rows={6}
            />

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
              <DraftField
                label="Priority (1-100)"
                value={String(cur.priority || 50)}
                onChange={(v) => updateField(draftId, queryClient, { priority: Number(v) })}
                disabled={draft.status !== "draft"}
                type="number"
              />
              <DraftSelect
                label="Category"
                value={cur.category || "new_request"}
                options={["new_request", "change", "bugfix", "ticket"]}
                onChange={(v) => updateField(draftId, queryClient, { category: v })}
                disabled={draft.status !== "draft"}
              />
              <DraftSelect
                label="Role"
                value={cur.assigned_role || "pi-coder"}
                options={["pi-coder", "pi-tester", "pi-fixer", "pi-reviewer", "CIO", "CEO-digital"]}
                onChange={(v) => updateField(draftId, queryClient, { assigned_role: v })}
                disabled={draft.status !== "draft"}
              />
            </div>

            {/* Success Criteria */}
            <div style={{ marginTop: 12 }}>
              <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4, display: "block" }}>
                Erfolgskriterien ({cur.success_criteria?.length || 0})
              </label>
              {(cur.success_criteria || []).map((crit, i) => (
                <div key={i} style={{ display: "flex", gap: 4, marginBottom: 4 }}>
                  <input
                    className="input"
                    value={crit}
                    onChange={(e) => {
                      const newArr = [...(cur.success_criteria || [])];
                      newArr[i] = e.target.value;
                      updateField(draftId, queryClient, { success_criteria: newArr });
                    }}
                    disabled={draft.status !== "draft"}
                    style={{ flex: 1, fontSize: 12 }}
                  />
                  <button
                    className="btn btn-sm"
                    onClick={() => {
                      const newArr = (cur.success_criteria || []).filter((_, idx) => idx !== i);
                      updateField(draftId, queryClient, { success_criteria: newArr });
                    }}
                    disabled={draft.status !== "draft"}
                    style={{ padding: "2px 6px", color: "var(--color-hermes-danger)" }}
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
              <button
                className="btn btn-sm"
                onClick={() => {
                  const newArr = [...(cur.success_criteria || []), ""];
                  updateField(draftId, queryClient, { success_criteria: newArr });
                }}
                disabled={draft.status !== "draft"}
                style={{ marginTop: 4, fontSize: 11 }}
              >
                + Kriterium hinzufuegen
              </button>
            </div>
          </div>

          {/* KI-Feedback Box */}
          {draft.status === "draft" && (
            <div style={{ background: "rgba(124, 58, 237, 0.05)", border: "1px solid rgba(124, 58, 237, 0.3)", borderRadius: 8, padding: 14 }}>
              <h3 style={{ margin: "0 0 8px", fontSize: 13, color: "#7c3aed", display: "flex", alignItems: "center", gap: 6 }}>
                <Lightbulb size={14} /> KI-Feedback (verfeinert den Entwurf)
              </h3>
              <p style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", margin: "0 0 8px" }}>
                Schreibe hier dein Feedback. Die KI analysiert deinen aktuellen Entwurf und dein Feedback und generiert eine verbesserte Version.
                <br />
                <strong>Tipp:</strong> Du kannst auch direkt sagen <code>title: Mein neuer Titel</code> oder <code>criteria: Neues Kriterium</code>.
              </p>
              <textarea
                className="input"
                value={userFeedback}
                onChange={(e) => setUserFeedback(e.target.value)}
                placeholder="z.B. 'description: Bitte genauer auf Mobile-UX eingehen. criteria: Login-Button ist auch auf kleinen Screens (375px) bedienbar.'"
                style={{ minHeight: 80, fontSize: 12 }}
                disabled={refineMutation.isPending}
              />
              <div style={{ marginTop: 8, display: "flex", gap: 6 }}>
                <button
                  className="btn btn-primary"
                  onClick={() => userFeedback && refineMutation.mutate(userFeedback)}
                  disabled={!userFeedback || refineMutation.isPending}
                >
                  {refineMutation.isPending ? (
                    <><RefreshCw size={14} className="spin" /> Verfeinere...</>
                  ) : (
                    <><Send size={14} /> An KI senden</>
                  )}
                </button>
                <button
                  className="btn btn-sm"
                  onClick={() => setUserFeedback("")}
                  disabled={!userFeedback}
                >
                  Clear
                </button>
              </div>
              {refineMutation.isError && (
                <div style={{ marginTop: 8, color: "var(--color-hermes-danger)", fontSize: 11 }}>
                  Fehler: {String(refineMutation.error)}
                </div>
              )}
            </div>
          )}

          {/* Actions: Publish / Abandon */}
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            {draft.status === "draft" ? (
              <>
                <button
                  className="btn btn-primary"
                  onClick={() => publishMutation.mutate()}
                  disabled={publishMutation.isPending}
                  style={{ flex: 1 }}
                >
                  <Check size={14} /> Freigeben (Task erstellen)
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => abandonMutation.mutate()}
                  disabled={abandonMutation.isPending}
                >
                  <Trash2 size={14} /> Verwerfen
                </button>
              </>
            ) : draft.status === "published" ? (
              <div style={{ padding: 12, background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.3)", borderRadius: 6, color: "var(--color-hermes-accent)", fontSize: 12 }}>
                ✅ Veroeffentlicht als Task: <code>{draft.final_task_id}</code>
              </div>
            ) : (
              <div style={{ padding: 12, background: "var(--color-hermes-muted)", border: "1px solid var(--color-hermes-border)", borderRadius: 6, fontSize: 12 }}>
                Verworfen
              </div>
            )}
          </div>
        </div>

        {/* === Rechte Spalte: Iteration-History === */}
        <div>
          <h3 style={{ fontSize: 14, marginBottom: 12 }}>Iterations-Verlauf</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {(draft.iterations || []).slice().reverse().map((it) => (
              <div
                key={it.iteration}
                style={{
                  background: "var(--color-hermes-surface)",
                  border: "1px solid var(--color-hermes-border)",
                  borderRadius: 6,
                  padding: 10,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                  <strong style={{ fontSize: 12 }}>Iteration {it.iteration}</strong>
                  <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                    {it.timestamp?.slice(11, 19)}
                  </span>
                </div>
                <div style={{ fontSize: 11, marginBottom: 4 }}>
                  <strong>User:</strong> {it.user_input.slice(0, 120)}{it.user_input.length > 120 ? "..." : ""}
                </div>
                <details style={{ fontSize: 11 }}>
                  <summary style={{ cursor: "pointer", color: "var(--color-hermes-text-secondary)" }}>KI-Output anzeigen</summary>
                  <pre style={{ fontSize: 10, background: "var(--color-hermes-bg)", padding: 6, borderRadius: 3, overflow: "auto", maxHeight: 200, marginTop: 4 }}>
                    {JSON.stringify(it.ai_output, null, 2).slice(0, 500)}
                    {JSON.stringify(it.ai_output, null, 2).length > 500 ? "..." : ""}
                  </pre>
                </details>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// Helper-Komponenten
// =====================================================================
function DraftField({ label, value, onChange, disabled, multiline, rows = 3, type = "text", large }: any) {
  return (
    <div style={{ marginBottom: 10 }}>
      <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4, display: "block" }}>
        {label}
      </label>
      {multiline ? (
        <textarea
          className="input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          rows={rows}
          style={{ fontSize: large ? 14 : 12, fontWeight: large ? 600 : 400, width: "100%" }}
        />
      ) : (
        <input
          className="input"
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          style={{ fontSize: large ? 14 : 12, fontWeight: large ? 600 : 400, width: "100%" }}
        />
      )}
    </div>
  );
}

function DraftSelect({ label, value, options, onChange, disabled }: any) {
  return (
    <div style={{ marginBottom: 10 }}>
      <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4, display: "block" }}>
        {label}
      </label>
      <select
        className="select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        style={{ width: "100%", fontSize: 12 }}
      >
        {options.map((o: string) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  );
}

// Helper: Direktes Update via PATCH (ohne KI-Aufruf, schneller)
async function updateField(draftId: string, queryClient: any, updates: any) {
  // Direkter PATCH statt /refine (kein LLM-Call noetig fuer User-Edits)
  // Felder werden flach gesendet (nicht unter "current")
  const res = await fetch(`http://127.0.0.1:5181/api/task-drafts/${draftId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (res.ok) {
    queryClient.invalidateQueries({ queryKey: ["task-draft", draftId] });
  }
}
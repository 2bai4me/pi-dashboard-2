// components/QuickTaskModal.tsx — Schnell-Task-Erstellung (FIX 23.06.2026: Modul fehlte)
// Vereinfachte Variante der NewTaskModal, ohne KI-Validierung.
// Verwendet von GatewayStatusBar fuer globale "Quick-Task"-Erstellung.

import { useState } from "react"
import { X, Send } from "lucide-react"
import { useMutation } from "@tanstack/react-query"
import { api } from "../api"
import { getCurrentScreenContext } from "../utils/screenContext"

export interface QuickTaskModalProps {
  onClose: () => void
  onCreated: (taskId: string) => void
}

export function QuickTaskModal({ onClose, onCreated }: QuickTaskModalProps) {
  const ctx = getCurrentScreenContext()
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [priority, setPriority] = useState(50)
  const [error, setError] = useState<string | null>(null)

  const createMut = useMutation({
    mutationFn: () =>
      api.post("/api/kanban/tasks", {
        project_id: ctx.projectId || null,
        title: title.trim() || "Quick Task",
        description: description.trim() || null,
        priority,
        category: "new_request",
        status: "triage",
      }),
    onSuccess: (resp: any) => onCreated(resp.id || ""),
    onError: (e: any) => {
      let detail = e?.message || String(e)
      if (e?.detail) detail = e.detail
      if (e?.status) detail = `HTTP ${e.status}: ${detail}`
      setError(`Erstellung fehlgeschlagen: ${detail}`)
    },
  })

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1100,
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        style={{
          background: "var(--color-hermes-bg, #0f0f0f)",
          border: "1px solid var(--color-hermes-accent, #7c3aed)",
          borderRadius: 10, padding: 24, maxWidth: 520, width: "92%",
        }}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
          <h2 style={{ flex: 1, margin: 0, fontSize: 18 }}>Quick Task</h2>
          <button onClick={onClose} style={{ background: "transparent", border: "none", color: "#999", cursor: "pointer" }}>
            <X size={18} />
          </button>
        </div>
        {error && (
          <div style={{ background: "rgba(220,38,38,0.15)", border: "1px solid #dc2626", padding: 10, borderRadius: 6, marginBottom: 12, fontSize: 12, color: "#fca5a5" }}>
            {error}
          </div>
        )}
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, display: "block", marginBottom: 4 }}>Titel</label>
          <input
            className="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="z.B. Bug im Login"
            autoFocus
            style={{ width: "100%", padding: "6px 8px" }}
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, display: "block", marginBottom: 4 }}>Beschreibung (optional)</label>
          <textarea
            className="input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            style={{ width: "100%", padding: "6px 8px", resize: "vertical" }}
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, display: "block", marginBottom: 4 }}>Prio: {priority}</label>
          <input
            type="range" min={0} max={100} value={priority}
            onChange={(e) => setPriority(parseInt(e.target.value))}
            style={{ width: "100%" }}
          />
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn-sm" onClick={onClose} disabled={createMut.isPending}>
            Abbrechen
          </button>
          <button
            className="btn btn-sm btn-primary"
            onClick={() => {
              setError(null)
              if (!title.trim()) {
                setError("Titel ist erforderlich")
                return
              }
              createMut.mutate()
            }}
            disabled={createMut.isPending}
          >
            <Send size={12} /> {createMut.isPending ? "Erstelle..." : "Erstellen"}
          </button>
        </div>
      </div>
    </div>
  )
}

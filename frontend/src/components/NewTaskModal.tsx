// NewTaskModal — User-Direktive 17.06.2026 (Redesign)
//
// Reduziert auf 1 Eingabefeld ("Idee"). KI (minimax-m3) generiert daraus:
// - Titel, Description, Priority, Category, Success-Criteria, Assigned-Role
// - TTS-Button liest die Idee vor
// - Schnellere LLM-Validierung (temperature 0.3, max_tokens 2000)
//
// Ablauf:
// 1. User gibt Idee ein (mehrzeilig)
// 2. Klick auf "KI generiert" -> /api/kanban/tasks/validate-with-llm
// 3. Generierte Felder werden als Preview angezeigt
// 4. User klickt "Task erstellen" -> POST /api/kanban/tasks
import { useState, useRef, useEffect } from "react"
import { X, Sparkles, Loader2, Volume2, Square, CheckCircle2, Wand2, Send, Edit3 } from "lucide-react"
import { useMutation } from "@tanstack/react-query"
import { api } from "../api"
import { useTTS } from "../hooks/useTTS"

export interface NewTaskModalProps {
  projectId: string
  onClose: () => void
  onCreated: (taskId: string) => void
}

interface ValidationResult {
  ok: boolean
  score: number
  quality_issues: string[]
  suggested_criteria: string[]
  suggested_title?: string
  suggested_category?: string
  suggested_priority?: number
  refinement_questions: string[]
  ready_to_create: boolean
}

export function NewTaskModal({ projectId, onClose, onCreated }: NewTaskModalProps) {
  const [idea, setIdea] = useState("")
  const tts = useTTS()
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [manualTitle, setManualTitle] = useState("")
  const ideaRef = useRef<HTMLTextAreaElement | null>(null)

  // Auto-Focus auf das Ideen-Feld
  useEffect(() => {
    setTimeout(() => ideaRef.current?.focus(), 100)
  }, [])

  // === KI-Validierung (minimax-m3) ===
  const validateMut = useMutation({
    mutationFn: () =>
      api.post("/api/kanban/tasks/validate-with-llm", {
        title: idea.split("\n")[0].slice(0, 80) || "Neue Idee", // erste Zeile als vorlaeufiger Titel
        description: idea,
        category: "new_request",
        priority: 50,
        project_id: projectId,
      }),
    onSuccess: (resp: any) => {
      setValidation(resp)
      setManualTitle(resp.suggested_title || "")
    },
    onError: (e: any) => {
      setError(`KI-Validierung fehlgeschlagen: ${e?.message || String(e)}`)
    },
  })

  // === Task erstellen (mit den KI-verbesserten Werten) ===
  const createMut = useMutation({
    mutationFn: () => {
      const v = validation
      return api.post("/api/kanban/tasks", {
        project_id: projectId,
        title: editing ? manualTitle : (v?.suggested_title || idea.split("\n")[0].slice(0, 80)),
        description: idea,
        category: v?.suggested_category || "new_request",
        priority: v?.suggested_priority || 50,
        assigned_role: "pi-coder",
        tags: [],
        success_criteria: v?.suggested_criteria || [],
        status: "triage",
      })
    },
    onSuccess: (resp: any) => {
      onCreated(resp.id || "")
    },
    onError: (e: any) => {
      setError(`Task-Erstellung fehlgeschlagen: ${e?.message || String(e)}`)
      setCreating(false)
    },
  })

  function handleGenerate() {
    if (!idea.trim() || idea.trim().length < 20) {
      setError("Bitte gib eine Idee mit mindestens 20 Zeichen ein.")
      return
    }
    setError(null)
    setValidation(null)
    validateMut.mutate()
  }

  function handleCreate() {
    if (!validation && !idea.trim()) {
      setError("Bitte erst KI generieren lassen oder manuell erstellen.")
      return
    }
    setCreating(true)
    createMut.mutate()
  }

  function handleTTS() {
    if (!idea.trim()) return
    if (tts.speaking) {
      tts.stop()
    } else {
      tts.speak(idea)
    }
  }

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1100,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--color-hermes-bg, #0f0f0f)",
          border: "1px solid var(--color-hermes-accent, #7c3aed)",
          borderRadius: 10, padding: 24, maxWidth: 720, width: "92%",
          maxHeight: "90vh", overflowY: "auto",
          boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
          <Sparkles size={22} color="var(--color-hermes-accent, #7c3aed)" />
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>Neuen Task erstellen</h2>
            <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary, #999)" }}>
              KI (minimax-m3) generiert Titel, Priorität und Erfolgskriterien aus deiner Idee
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "transparent", border: "none", color: "#999", cursor: "pointer", padding: 4 }}
            title="Schliessen"
          >
            <X size={18} />
          </button>
        </div>

        {error && (
          <div style={{
            background: "rgba(220,38,38,0.15)", border: "1px solid #dc2626", padding: 10,
            borderRadius: 6, marginBottom: 12, fontSize: 12, color: "#fca5a5",
          }}>
            ⚠ {error}
          </div>
        )}

        {/* === Phase 1: Idee eingeben === */}
        {!validation && (
          <>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary, #999)", display: "block", marginBottom: 6, fontWeight: 600 }}>
                Deine Idee (mehrzeilig)
              </label>
              <div style={{ position: "relative" }}>
                <textarea
                  ref={ideaRef}
                  className="input"
                  value={idea}
                  onChange={(e) => setIdea(e.target.value)}
                  placeholder="Beschreibe deine Idee in 1-3 Sätzen. Z.B.: 'Login-Button mit OAuth2 soll auf der Startseite sichtbar sein, mit Google-Provider. Bei Klick soll ein Popup zur Google-Authentifizierung erscheinen.'"
                  rows={6}
                  style={{ resize: "vertical", minHeight: 120, paddingRight: 44 }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                      e.preventDefault()
                      handleGenerate()
                    }
                  }}
                />
                {/* TTS-Button (ueberlagert) */}
                <button
                  onClick={handleTTS}
                  disabled={!idea.trim()}
                  title={tts.speaking ? "Vorlesen stoppen" : "Idee vorlesen (TTS)"}
                  style={{
                    position: "absolute", bottom: 8, right: 8,
                    background: tts.speaking ? "rgba(220,38,38,0.2)" : "rgba(124,58,237,0.15)",
                    border: `1px solid ${tts.speaking ? "#dc2626" : "var(--color-hermes-accent, #7c3aed)"}`,
                    color: tts.speaking ? "#dc2626" : "#a78bfa",
                    borderRadius: 4, padding: "4px 8px", cursor: "pointer",
                    fontSize: 11, display: "flex", alignItems: "center", gap: 4,
                    opacity: idea.trim() ? 1 : 0.4,
                  }}
                >
                  {tts.speaking ? <Square size={11} /> : <Volume2 size={11} />}
                  {tts.speaking ? "Stop" : "TTS"}
                </button>
              </div>
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary, #999)", marginTop: 4, display: "flex", justifyContent: "space-between" }}>
                <span>{idea.length} Zeichen {idea.length < 20 ? "(min 20 noetig)" : "✓"}</span>
                <span>Strg+Enter zum Generieren</span>
              </div>
            </div>

            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <button
                className="btn btn-sm"
                onClick={onClose}
                disabled={validateMut.isPending}
                style={{ fontSize: 13 }}
              >
                Abbrechen
              </button>
              <button
                className="btn btn-sm btn-primary"
                onClick={handleGenerate}
                disabled={validateMut.isPending || idea.trim().length < 20}
                style={{ fontSize: 13, marginLeft: "auto" }}
              >
                {validateMut.isPending ? (
                  <>
                    <Loader2 size={13} className="spin" /> KI analysiert (bis zu 30s)...
                  </>
                ) : (
                  <>
                    <Sparkles size={13} /> KI generiert Task
                  </>
                )}
              </button>
            </div>
          </>
        )}

        {/* === Phase 2: KI-Generierte Felder anzeigen + erstellen === */}
        {validation && (
          <>
            <div style={{
              background: validation.ready_to_create ? "rgba(46,160,67,0.08)" : "rgba(245,158,11,0.08)",
              border: `1px solid ${validation.ready_to_create ? "#2ea043" : "#f59e0b"}`,
              borderRadius: 6, padding: 12, marginBottom: 14,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                {validation.ready_to_create ? (
                  <CheckCircle2 size={16} color="#2ea043" />
                ) : (
                  <Edit3 size={16} color="#f59e0b" />
                )}
                <span style={{ fontSize: 13, fontWeight: 600 }}>
                  KI-Score: {validation.score}/100 — {validation.ready_to_create ? "Bereit zum Erstellen" : "Bitte ueberarbeiten"}
                </span>
              </div>
              {validation.quality_issues && validation.quality_issues.length > 0 && (
                <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
                  <strong>Probleme:</strong>
                  <ul style={{ margin: "4px 0", paddingLeft: 20 }}>
                    {validation.quality_issues.map((i, idx) => <li key={idx}>{i}</li>)}
                  </ul>
                </div>
              )}
            </div>

            {/* Vorschau: Generierte Felder */}
            <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: "8px 12px", fontSize: 12, marginBottom: 14 }}>
              <span style={{ color: "var(--color-hermes-text-secondary)" }}>Titel:</span>
              {editing ? (
                <input className="input" value={manualTitle} onChange={(e) => setManualTitle(e.target.value)} style={{ fontSize: 12, padding: "4px 8px" }} />
              ) : (
                <span style={{ fontWeight: 600 }}>{validation.suggested_title || "—"}</span>
              )}

              <span style={{ color: "var(--color-hermes-text-secondary)" }}>Priorität:</span>
              <span>
                <span style={{
                  display: "inline-block", padding: "2px 8px", borderRadius: 3,
                  background: (validation.suggested_priority || 0) >= 80 ? "rgba(220,38,38,0.2)" :
                              (validation.suggested_priority || 0) >= 50 ? "rgba(245,158,11,0.2)" :
                              "rgba(125,125,125,0.2)",
                  fontWeight: 600,
                }}>
                  {validation.suggested_priority || 50}
                </span>
              </span>

              <span style={{ color: "var(--color-hermes-text-secondary)" }}>Kategorie:</span>
              <span><code style={{ fontSize: 11 }}>{validation.suggested_category || "new_request"}</code></span>

              <span style={{ color: "var(--color-hermes-text-secondary)" }}>Beschreibung:</span>
              <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>{idea.slice(0, 200)}{idea.length > 200 ? "..." : ""}</span>

              {validation.suggested_criteria && validation.suggested_criteria.length > 0 && (
                <>
                  <span style={{ color: "var(--color-hermes-text-secondary)", gridRow: "span 1" }}>Kriterien:</span>
                  <ul style={{ margin: 0, paddingLeft: 20, fontSize: 11 }}>
                    {validation.suggested_criteria.map((c, idx) => (
                      <li key={idx}>{c}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>

            <div style={{ display: "flex", gap: 8, marginTop: 16, paddingTop: 12, borderTop: "1px solid var(--color-hermes-border)" }}>
              <button
                className="btn btn-sm"
                onClick={() => { setValidation(null); setEditing(false); }}
                disabled={createMut.isPending}
                style={{ fontSize: 12 }}
              >
                ← Neu generieren
              </button>
              <button
                className="btn btn-sm"
                onClick={() => setEditing(!editing)}
                disabled={createMut.isPending}
                style={{ fontSize: 12 }}
              >
                <Edit3 size={12} /> {editing ? "Fertig" : "Titel bearbeiten"}
              </button>
              <button
                className="btn btn-sm btn-primary"
                onClick={handleCreate}
                disabled={createMut.isPending || creating}
                style={{ fontSize: 13, marginLeft: "auto" }}
              >
                {createMut.isPending || creating ? (
                  <>
                    <Loader2 size={13} className="spin" /> Erstelle...
                  </>
                ) : (
                  <>
                    <Send size={13} /> Task erstellen
                  </>
                )}
              </button>
            </div>
          </>
        )}

        <style>{`
          .spin { animation: spin 1s linear infinite; }
          @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        `}</style>
      </div>
    </div>
  )
}

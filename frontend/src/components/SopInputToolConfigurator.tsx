// SopInputToolConfigurator.tsx — Konfigurations-UI fuer User-Input-Tool im SOP-Designer
//
// User-Direktive 17.06.2026:
//   Wenn der User im SOP-Designer das User-Input-Tool fuer einen Step aktiviert,
//   soll er hier einstellen koennen:
//   - Welche Felder im Dialog sichtbar sind (Beschreibung, Empfehlung, TTS)
//   - Default-Beschreibung (optional, kann zur Laufzeit ueberschrieben werden)
//   - Default-Empfehlung (vorgeschlagene Antwort)
//   - Optionen (nur fuer choice-Fragen)
//
// Wird eingebunden in ToolRunner.tsx als zusaetzliche Action
// und in RacWorkflow.tsx (TODO: Step-Editor-Integration).

import { useState, useEffect } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../api"
import {
  CheckCircle2, XCircle, Save, Volume2, Wand2, FileText, Sparkles, MessageSquare, Eye, EyeOff,
  Loader2, AlertCircle,
} from "lucide-react"

const DEFAULT_OPTIONS = {
  show_description: true,
  show_recommendation: true,
  show_tts: true,
  allow_edit_recommendation: true,
  answer_required: true,
  recommendation_as_default: true,
}

interface Props {
  sopId: string
  stepId: string
  step: {
    id: string
    name: string
    agent: string
    input_tool_required?: boolean
    input_tool_type?: string | null
    input_tool_prompt?: string | null
    input_tool_description?: string | null
    input_tool_recommendation?: string | null
    input_tool_options?: string | null
    input_tool_options_config?: string | null
    input_tool_context_key?: string | null
  }
  onClose?: () => void
  // Embedded-Modus: kompakter, ohne grossen Titel, fuer Sidebar
  embedded?: boolean
  onSaved?: () => void
}

export function SopInputToolConfigurator({ sopId, stepId, step, onClose, embedded, onSaved }: Props) {
  const qc = useQueryClient()

  // Lokaler State
  const [enabled, setEnabled] = useState(!!step.input_tool_required)
  const [type, setType] = useState(step.input_tool_type || "text")
  const [prompt, setPrompt] = useState(step.input_tool_prompt || "")
  const [description, setDescription] = useState(step.input_tool_description || "")
  const [recommendation, setRecommendation] = useState(step.input_tool_recommendation || "")
  const [contextKey, setContextKey] = useState(step.input_tool_context_key || `step_${stepId.slice(0, 8)}_input`)
  const [optionsText, setOptionsText] = useState(() => {
    try { return step.input_tool_options ? JSON.stringify(JSON.parse(step.input_tool_options), null, 2) : "[]" }
    catch { return "[]" }
  })
  const [opts, setOpts] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = { ...DEFAULT_OPTIONS }
    if (step.input_tool_options_config) {
      try {
        const parsed = JSON.parse(step.input_tool_options_config)
        Object.keys(initial).forEach((k) => { if (typeof parsed[k] === "boolean") initial[k] = parsed[k] })
      } catch {}
    }
    return initial
  })
  const [validationError, setValidationError] = useState<string | null>(null)

  // Save-Mutation
  const saveMut = useMutation({
    mutationFn: () => {
      const payload: any = {
        input_tool_required: enabled,
        input_tool_type: enabled ? type : null,
        input_tool_prompt: enabled ? prompt : null,
        input_tool_description: enabled ? description : null,
        input_tool_recommendation: enabled ? recommendation : null,
        input_tool_options: enabled && type === "choice" ? optionsText : null,
        input_tool_options_config: enabled ? JSON.stringify(opts) : null,
        input_tool_context_key: enabled ? contextKey : null,
      }
      return api.testRunner.executeAction("noop", {}).catch(() => null).then(() =>
        fetch(`/api/sops/${sopId}/steps/${stepId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }).then((r) => r.json())
      )
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sop", sopId] })
      qc.invalidateQueries({ queryKey: ["sops"] })
      qc.invalidateQueries({ queryKey: ["sop", sopId, "step", stepId] })
      onSaved?.()
    },
  })

  // Preview
  const renderPreview = () => {
    const sampleQuestion = prompt || "Beispiel-Frage: Welche Datenbank-URL?"
    const sampleDesc = description || "Hier steht zusaetzlicher Kontext zur Frage, der dem User hilft, die richtige Antwort zu geben."
    const sampleRec = recommendation || "Empfohlene Antwort: postgresql+psycopg://user:pass@host:5432/db"
    return (
      <div style={{ background: "rgba(0,0,0,0.3)", border: "1px dashed #555", borderRadius: 6, padding: 12 }}>
        <div style={{ fontSize: 11, color: "#999", marginBottom: 8, textTransform: "uppercase", fontWeight: 600 }}>
          Vorschau (so sieht der User es)
        </div>
        <div style={{
          background: "rgba(255,255,255,0.03)", borderLeft: "3px solid #3b82f6",
          borderRadius: 4, padding: 10, marginBottom: 10, fontSize: 13, whiteSpace: "pre-wrap",
        }}>
          {sampleQuestion}
        </div>
        {opts.show_description && (
          <div style={{
            background: "rgba(59, 130, 246, 0.05)", borderLeft: "3px solid #3b82f6",
            borderRadius: 4, padding: 10, marginBottom: 10, fontSize: 12, whiteSpace: "pre-wrap",
          }}>
            <FileText size={11} style={{ marginRight: 4, verticalAlign: "text-bottom" }} /> {sampleDesc}
            {opts.show_tts && (
              <button style={{ marginLeft: 8, fontSize: 10 }} title="TTS-Vorlesen (Vorschau)">
                <Volume2 size={10} /> Vorlesen
              </button>
            )}
          </div>
        )}
        {opts.show_recommendation && (
          <div style={{
            background: "rgba(124, 58, 237, 0.05)", borderLeft: "3px solid #7c3aed",
            borderRadius: 4, padding: 10, marginBottom: 10, fontSize: 12, whiteSpace: "pre-wrap",
          }}>
            <Sparkles size={11} style={{ marginRight: 4, verticalAlign: "text-bottom" }} /> {sampleRec}
            {opts.show_tts && (
              <button style={{ marginLeft: 8, fontSize: 10 }} title="TTS-Vorlesen (Vorschau)">
                <Volume2 size={10} /> Vorlesen
              </button>
            )}
            {opts.allow_edit_recommendation && (
              <button style={{ marginLeft: 8, fontSize: 10, background: "#7c3aed", color: "#fff", border: "none", padding: "2px 8px", borderRadius: 3 }} title="Empfehlung uebernehmen (Vorschau)">
                <Wand2 size={10} /> Uebernehmen
              </button>
            )}
          </div>
        )}
        <div style={{
          background: "rgba(0,0,0,0.3)", border: "1px solid #333",
          borderRadius: 4, padding: 8, fontSize: 12, color: "#999", fontStyle: "italic",
        }}>
          [Textarea fuer User-Antwort]
        </div>
      </div>
    )
  }

  return (
    <div style={{
      display: embedded ? "block" : "grid",
      gridTemplateColumns: embedded ? undefined : "1fr 1fr",
      gap: 16,
    }}>
      {/* Linke Spalte: Konfig */}
      <div>
        {!embedded && (
          <>
            <h3 style={{ marginTop: 0, fontSize: 14 }}>
              Schritt: <code style={{ background: "#222", padding: "2px 6px", borderRadius: 3 }}>{step.name}</code>
            </h3>
            <div style={{ fontSize: 12, color: "#999", marginBottom: 12 }}>
              Agent: <strong>{step.agent}</strong> · Step-ID: <code>{stepId.slice(0, 12)}</code>
            </div>
          </>
        )}
        <h3 style={{ marginTop: 0, fontSize: 14 }}>
          Schritt: <code style={{ background: "#222", padding: "2px 6px", borderRadius: 3 }}>{step.name}</code>
        </h3>
        <div style={{ fontSize: 12, color: "#999", marginBottom: 12 }}>
          Agent: <strong>{step.agent}</strong> · Step-ID: <code>{stepId.slice(0, 12)}</code>
        </div>

        {/* Aktivieren */}
        <label style={{ display: "flex", alignItems: "center", gap: 8, padding: 10, background: enabled ? "rgba(124, 58, 237, 0.1)" : "transparent", border: "1px solid #333", borderRadius: 6, marginBottom: 12, cursor: "pointer" }}>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          <MessageSquare size={14} color={enabled ? "#7c3aed" : "#999"} />
          <strong style={{ fontSize: 13 }}>User-Input-Tool aktivieren</strong>
        </label>

        {enabled && (
          <>
            {/* Typ */}
            <div style={{ marginBottom: 10 }}>
              <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>
                Fragetyp
              </label>
              <select value={type} onChange={(e) => setType(e.target.value)} style={{ width: "100%", padding: 6, background: "#0f0f0f", color: "#e5e5e5", border: "1px solid #333", borderRadius: 4 }}>
                <option value="text">Text (Freitext-Antwort)</option>
                <option value="confirmation">Confirmation (ja/nein)</option>
                <option value="choice">Choice (Multiple Choice)</option>
                <option value="image">Image (Bild erforderlich)</option>
                <option value="attachment">Attachment (Datei erforderlich)</option>
                <option value="any">Any (Text + Anhang)</option>
              </select>
            </div>

            {/* Prompt */}
            <div style={{ marginBottom: 10 }}>
              <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>
                Frage <span style={{ color: "#dc2626" }}>*</span>
              </label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={3}
                placeholder="Die Hauptfrage, die der Agent dem User stellt..."
                style={{ width: "100%", padding: 8, background: "rgba(0,0,0,0.3)", color: "#e5e5e5", border: "1px solid #333", borderRadius: 4, fontSize: 12, fontFamily: "inherit" }}
              />
            </div>

            {/* Description */}
            <div style={{ marginBottom: 10 }}>
              <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>
                <FileText size={11} style={{ marginRight: 4, verticalAlign: "text-bottom" }} />
                Default-Beschreibung (optional)
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                placeholder="Zusaetzlicher Kontext, der im Dialog angezeigt wird (kann vom Agenten ueberschrieben werden)"
                style={{ width: "100%", padding: 8, background: "rgba(0,0,0,0.3)", color: "#e5e5e5", border: "1px solid #333", borderRadius: 4, fontSize: 12, fontFamily: "inherit" }}
              />
            </div>

            {/* Recommendation */}
            <div style={{ marginBottom: 10 }}>
              <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>
                <Sparkles size={11} style={{ marginRight: 4, verticalAlign: "text-bottom" }} />
                Default-Empfehlung (vorgeschlagene Antwort)
              </label>
              <textarea
                value={recommendation}
                onChange={(e) => setRecommendation(e.target.value)}
                rows={2}
                placeholder="Vom Agent vorgeschlagene Antwort — User kann sie uebernehmen und ergaenzen"
                style={{ width: "100%", padding: 8, background: "rgba(0,0,0,0.3)", color: "#e5e5e5", border: "1px solid #333", borderRadius: 4, fontSize: 12, fontFamily: "inherit" }}
              />
            </div>

            {/* Choice-Optionen */}
            {type === "choice" && (
              <div style={{ marginBottom: 10 }}>
                <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>
                  Choice-Optionen (JSON-Array, eine Option pro String)
                </label>
                <textarea
                  value={optionsText}
                  onChange={(e) => setOptionsText(e.target.value)}
                  rows={3}
                  style={{ width: "100%", padding: 8, background: "rgba(0,0,0,0.3)", color: "#e5e5e5", border: "1px solid #333", borderRadius: 4, fontSize: 12, fontFamily: "monospace" }}
                />
              </div>
            )}

            {/* Context-Key */}
            <div style={{ marginBottom: 10 }}>
              <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>
                Context-Key (Variable, unter der die Antwort gespeichert wird)
              </label>
              <input
                type="text"
                value={contextKey}
                onChange={(e) => setContextKey(e.target.value)}
                style={{ width: "100%", padding: 6, background: "rgba(0,0,0,0.3)", color: "#e5e5e5", border: "1px solid #333", borderRadius: 4, fontSize: 12, fontFamily: "monospace" }}
              />
            </div>

            {/* Options-Toggles */}
            <div style={{ marginBottom: 10, padding: 10, background: "rgba(0,0,0,0.2)", borderRadius: 6, border: "1px solid #333" }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Anzeige-Optionen (was der User sieht)</div>
              {[
                { k: "show_description", label: "Beschreibung anzeigen", icon: FileText },
                { k: "show_recommendation", label: "Empfehlung anzeigen", icon: Sparkles },
                { k: "show_tts", label: "TTS (Vorlese-Funktion) fuer Beschreibung+Empfehlung", icon: Volume2 },
                { k: "allow_edit_recommendation", label: "User darf Empfehlung uebernehmen und bearbeiten", icon: Wand2 },
                { k: "recommendation_as_default", label: "Empfehlung als Default-Antwort laden", icon: CheckCircle2 },
                { k: "answer_required", label: "Antwort ist Pflicht", icon: AlertCircle },
              ].map((opt) => {
                const Icon = opt.icon
                return (
                  <label key={opt.k} style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 0", cursor: "pointer", fontSize: 12 }}>
                    <input
                      type="checkbox"
                      checked={opts[opt.k]}
                      onChange={(e) => setOpts({ ...opts, [opt.k]: e.target.checked })}
                    />
                    <Icon size={12} color={opts[opt.k] ? "#7c3aed" : "#999"} />
                    <span>{opt.label}</span>
                  </label>
                )
              })}
            </div>

            {/* Validation */}
            {validationError && (
              <div style={{ background: "rgba(220, 38, 38, 0.1)", border: "1px solid #dc2626", borderRadius: 4, padding: 8, fontSize: 12, color: "#dc2626", marginBottom: 10 }}>
                <XCircle size={12} style={{ marginRight: 4, verticalAlign: "text-bottom" }} />
                {validationError}
              </div>
            )}

            {/* Save */}
            <button
              onClick={() => {
                if (enabled && !prompt.trim()) {
                  setValidationError("Frage ist Pflicht, wenn das Tool aktiviert ist")
                  return
                }
                if (type === "choice") {
                  try { JSON.parse(optionsText) }
                  catch { setValidationError("Choice-Optionen muessen valides JSON-Array sein"); return }
                }
                setValidationError(null)
                saveMut.mutate()
              }}
              disabled={saveMut.isPending}
              style={{
                background: "#7c3aed", color: "#fff", border: "none",
                borderRadius: embedded ? 4 : 6, padding: embedded ? "6px 12px" : "10px 16px",
                fontSize: embedded ? 12 : 14, fontWeight: 600,
                cursor: saveMut.isPending ? "wait" : "pointer",
                display: "flex", alignItems: "center", gap: 6,
                opacity: saveMut.isPending ? 0.6 : 1,
                width: embedded ? "100%" : "auto",
                justifyContent: "center",
              }}
            >
              {saveMut.isPending ? <Loader2 size={embedded ? 12 : 14} className="spin" /> : <Save size={embedded ? 12 : 14} />}
              {saveMut.isPending ? "Speichert..." : embedded ? "Speichern" : "Konfiguration speichern"}
            </button>

            {saveMut.isSuccess && (
              <div style={{ marginTop: 8, color: "#10b981", fontSize: 12, display: "flex", alignItems: "center", gap: 4 }}>
                <CheckCircle2 size={12} /> Gespeichert!
              </div>
            )}

            {onClose && !embedded && (
              <button
                onClick={onClose}
                style={{
                  marginTop: 8, marginLeft: 8, background: "transparent",
                  color: "#999", border: "1px solid #444", borderRadius: 6,
                  padding: "10px 16px", fontSize: 14, cursor: "pointer",
                }}
              >
                Schliessen
              </button>
            )}
          </>
        )}
      </div>

      {/* Rechte Spalte: Vorschau (nur im Full-Modus) */}
      {!embedded && (
        <div>
          <h3 style={{ marginTop: 0, fontSize: 14 }}>Vorschau</h3>
          {enabled ? renderPreview() : (
            <div style={{ padding: 20, textAlign: "center", color: "#999", border: "1px dashed #555", borderRadius: 6 }}>
              <EyeOff size={20} style={{ marginBottom: 6 }} />
              <div>Tool ist deaktiviert.</div>
              <div style={{ fontSize: 11, marginTop: 4 }}>Aktiviere die Checkbox links, um eine Vorschau zu sehen.</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// UserInputForm.tsx — Wiederverwendbares User-Input-Formular
//
// User-Direktive 17.06.2026:
//   Zeigt Frage, optional Beschreibung, optional Empfehlung, Texteingabe.
//   TTS-Buttons fuer Beschreibung und Empfehlung.
//   "Empfehlung uebernehmen"-Button uebertraegt Empfehlung in die Eingabe.
//
// Wird verwendet in:
//   - AgentQuestions.tsx (Detail-View)
//   - Kanban.tsx (UserInputModal)
//
// Sichtbarkeit der Felder wird ueber `options_config` gesteuert:
//   show_description, show_recommendation, show_tts, allow_edit_recommendation,
//   answer_required, recommendation_as_default

import { useState, useEffect, useRef } from "react"
import { useTTS } from "../hooks/useTTS"
import {
  CheckCircle2, Volume2, Square, Wand2, FileText, Sparkles, Send, Loader2, X,
} from "lucide-react"

const DEFAULT_OPTIONS = {
  show_description: true,
  show_recommendation: true,
  show_tts: true,
  allow_edit_recommendation: true,
  answer_required: true,
  recommendation_as_default: true,
}

export interface UserInputFormProps {
  question: {
    id: string
    title?: string | null
    question: string
    description?: string | null
    recommendation?: string | null
    options_config?: Record<string, any>
    question_type?: string
    agent_label?: string | null
  }
  onSubmit: (text: string) => Promise<void> | void
  onCancel?: () => void
  isSubmitting?: boolean
  // Default: Empfehlung wird beim Mount uebernommen (wenn recommendation_as_default)
  initialValue?: string
}

export function UserInputForm({
  question, onSubmit, onCancel, isSubmitting, initialValue,
}: UserInputFormProps) {
  const cfg = { ...DEFAULT_OPTIONS, ...(question.options_config || {}) }
  const ttsDesc = useTTS()
  const ttsRec = useTTS()
  const [text, setText] = useState(initialValue || "")
  const [recommendationTaken, setRecommendationTaken] = useState(false)
  const initialised = useRef(false)

  // Beim Mount: Empfehlung uebernehmen, wenn recommendation_as_default UND Empfehlung existiert
  useEffect(() => {
    if (initialised.current) return
    initialised.current = true
    if (
      cfg.recommendation_as_default &&
      question.recommendation &&
      !initialValue
    ) {
      setText(question.recommendation)
      setRecommendationTaken(true)
    }
  }, [cfg.recommendation_as_default, question.recommendation, initialValue])

  // Empfehlung uebernehmen (Button)
  const takeRecommendation = () => {
    if (question.recommendation) {
      setText(question.recommendation)
      setRecommendationTaken(true)
    }
  }

  const handleSubmit = async () => {
    if (cfg.answer_required && !text.trim()) return
    await onSubmit(text)
  }

  return (
    <div>
      {/* Title (falls vorhanden) - NEU: prominent anzeigen */}
      {question.title && (
        <div
          style={{
            background: "rgba(124, 58, 237, 0.1)",
            border: "1px solid rgba(124, 58, 237, 0.4)",
            borderLeft: "3px solid #7c3aed",
            borderRadius: 6,
            padding: 12,
            marginBottom: 14,
            fontSize: 16,
            fontWeight: 600,
            lineHeight: 1.4,
            whiteSpace: "pre-wrap",
            color: "var(--color-hermes-text, #e5e5e5)",
          }}
        >
          <div style={{ fontSize: 10, color: "#7c3aed", marginBottom: 4, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1 }}>
            {question.agent_label || "CIO-Rueckfrage"}
          </div>
          {question.title}
        </div>
      )}

      {/* Frage */}
      <div
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid var(--color-hermes-border, #333)",
          borderLeft: "3px solid #3b82f6",
          borderRadius: 6,
          padding: 14,
          marginBottom: 14,
          fontSize: 14,
          lineHeight: 1.5,
          whiteSpace: "pre-wrap",
        }}
      >
        <div style={{ fontSize: 11, color: "#999", marginBottom: 4, fontWeight: 600, textTransform: "uppercase" }}>
          Frage des Agenten
        </div>
        {question.question}
      </div>

      {/* Beschreibung (mit TTS) */}
      {cfg.show_description && question.description && (
        <div
          style={{
            background: "rgba(59, 130, 246, 0.05)",
            border: "1px solid rgba(59, 130, 246, 0.3)",
            borderLeft: "3px solid #3b82f6",
            borderRadius: 6,
            padding: 12,
            marginBottom: 14,
            fontSize: 13,
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <FileText size={12} color="#3b82f6" />
            <span style={{ fontSize: 11, color: "#3b82f6", fontWeight: 600, textTransform: "uppercase" }}>
              Beschreibung
            </span>
            {cfg.show_tts && ttsDesc.supported && (
              <button
                onClick={() => ttsDesc.speaking ? ttsDesc.stop() : ttsDesc.speak(question.description!)}
                title={ttsDesc.speaking ? "Vorlesen stoppen" : "Beschreibung vorlesen"}
                style={{
                  background: "transparent", border: "1px solid #3b82f6", color: "#3b82f6",
                  borderRadius: 4, padding: "2px 6px", cursor: "pointer", fontSize: 11,
                  display: "flex", alignItems: "center", gap: 4, marginLeft: "auto",
                }}
              >
                {ttsDesc.speaking ? <Square size={10} /> : <Volume2 size={10} />}
                {ttsDesc.speaking ? "Stop" : "Vorlesen"}
              </button>
            )}
          </div>
          {question.description}
        </div>
      )}

      {/* Empfehlung (mit TTS + Uebernehmen-Button) */}
      {cfg.show_recommendation && question.recommendation && (
        <div
          style={{
            background: "rgba(124, 58, 237, 0.05)",
            border: "1px solid rgba(124, 58, 237, 0.3)",
            borderLeft: "3px solid #7c3aed",
            borderRadius: 6,
            padding: 12,
            marginBottom: 14,
            fontSize: 13,
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <Sparkles size={12} color="#7c3aed" />
            <span style={{ fontSize: 11, color: "#7c3aed", fontWeight: 600, textTransform: "uppercase" }}>
              Empfehlung des Agenten
            </span>
            {cfg.show_tts && ttsRec.supported && (
              <button
                onClick={() => ttsRec.speaking ? ttsRec.stop() : ttsRec.speak(question.recommendation!)}
                title={ttsRec.speaking ? "Vorlesen stoppen" : "Empfehlung vorlesen"
                }
                style={{
                  background: "transparent", border: "1px solid #7c3aed", color: "#7c3aed",
                  borderRadius: 4, padding: "2px 6px", cursor: "pointer", fontSize: 11,
                  display: "flex", alignItems: "center", gap: 4,
                }}
              >
                {ttsRec.speaking ? <Square size={10} /> : <Volume2 size={10} />}
                {ttsRec.speaking ? "Stop" : "Vorlesen"}
              </button>
            )}
            {cfg.allow_edit_recommendation && !recommendationTaken && (
              <button
                onClick={takeRecommendation}
                title="Empfehlung als Antwort uebernehmen (kann danach noch bearbeitet werden)"
                style={{
                  background: "#7c3aed", color: "#fff", border: "none",
                  borderRadius: 4, padding: "4px 10px", cursor: "pointer", fontSize: 11,
                  display: "flex", alignItems: "center", gap: 4, marginLeft: "auto",
                }}
              >
                <Wand2 size={11} /> Uebernehmen
              </button>
            )}
            {recommendationTaken && (
              <span style={{ marginLeft: "auto", color: "#10b981", fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>
                <CheckCircle2 size={12} /> uebernommen
              </span>
            )}
          </div>
          {question.recommendation}
        </div>
      )}

      {/* Texteingabe */}
      <div style={{ marginBottom: 8, fontSize: 11, color: "#999", display: "flex", alignItems: "center", gap: 4 }}>
        <span>Deine Antwort</span>
        {cfg.answer_required && <span style={{ color: "#dc2626" }}>*</span>}
        {recommendationTaken && cfg.allow_edit_recommendation && (
          <span style={{ marginLeft: 8, color: "#7c3aed", fontSize: 10 }}>
            (Empfehlung uebernommen — kann bearbeitet werden)
          </span>
        )}
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Deine Antwort..."
        rows={5}
        autoFocus
        style={{
          width: "100%",
          background: "rgba(0,0,0,0.3)",
          border: "1px solid var(--color-hermes-border, #333)",
          borderRadius: 6,
          padding: 10,
          color: "var(--color-hermes-text, #e5e5e5)",
          fontSize: 14,
          fontFamily: "inherit",
          boxSizing: "border-box",
          resize: "vertical",
        }}
      />

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button
          onClick={handleSubmit}
          disabled={isSubmitting || (cfg.answer_required && !text.trim())}
          style={{
            background: "var(--color-hermes-accent, #7c3aed)",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            padding: "10px 16px",
            fontSize: 14,
            fontWeight: 600,
            cursor: isSubmitting || (cfg.answer_required && !text.trim()) ? "not-allowed" : "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            opacity: isSubmitting || (cfg.answer_required && !text.trim()) ? 0.5 : 1,
          }}
        >
          {isSubmitting ? <Loader2 size={14} className="spin" /> : <Send size={14} />}
          Senden
        </button>
        {onCancel && (
          <button
            onClick={onCancel}
            style={{
              background: "transparent",
              color: "#999",
              border: "1px solid #444",
              borderRadius: 6,
              padding: "10px 16px",
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            Abbrechen
          </button>
        )}
      </div>
    </div>
  )
}

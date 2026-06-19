import { useState, useEffect, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Send, FileText, Sparkles } from "lucide-react"
import { api } from "../api"
import { useTTSContext } from "../TTSContext"
import { DynamicTextarea } from "../TTSControl"

type BrainstormEntry = { id?: string; role: "user" | "assistant"; text: string; ts?: string }

// Client-seitige Mock-AI-Antwort (v2 hat kein LLM-Backend)
function generateAssistantReply(userText: string, projectName: string, prevCount: number): string {
  const lower = userText.toLowerCase()
  // Wenn der User Phasen erwähnt → Phasen extrahieren
  if (lower.includes("phase") || lower.includes("schritt")) {
    return `Ich habe folgende Phasen erfasst:

**Projekt:** ${projectName}

**Phasen:**
1. **Topic / Idee** — Konzept & Name des Inhalts
2. **Research** — Hintergrundrecherche, Quellen, Faktencheck
3. **Script / Drehbuch** — Text, Hook, Storyboard
4. **Audio** — Voiceover, Sprecher, Aufnahme
5. **Slides** — Visualisierungen, B-Roll, Stock-Material
6. **Video** — Schnitt, Animation, Effekte
7. **Upload** — Plattform-Optimierung, Thumbnails, SEO

**Verständnisfragen:**
1. Wer ist die Zielgruppe / der Nutzer dieser Lösung?
2. Welches konkrete Problem soll gelöst werden?
3. Gibt es ein Zeitlimit pro Phase?
4. Welche Tools/Plattformen sind im Einsatz?
5. Wer genehmigt die Endversion?

Du kannst deine Antworten direkt in dieses Feld schreiben — ich integriere sie ins Dokument.`
  }

  // Erstes Statement
  if (prevCount === 0) {
    return `Ich habe dein Projektziel verstanden:

**Projekt:** ${projectName}

**Zusammenfassung:** ${userText.slice(0, 300)}${userText.length > 300 ? "…" : ""}

Bitte beantworte diese Fragen, damit ich präziser brainstormen kann:

1. Wer ist die Zielgruppe?
2. Welches Problem soll gelöst werden?
3. Welche Phasen durchläuft der Prozess?
4. Welche Tools sind im Einsatz?
5. Was wäre ein erfolgreicher Abschluss?`
  }

  // Folgeantwort: kurzes Echo + neue Frage
  return `Verstanden. Ich habe Folgendes ergänzt:

> ${userText.slice(0, 200)}${userText.length > 200 ? "…" : ""}

Damit ist das Bild klarer. Eine letzte wichtige Frage:

- Gibt es bekannte Risiken, Engpässe oder Abhängigkeiten, die wir im Auge behalten sollten?

Wenn alles passt, klicke **Generate Requirements** um das Dokument zu finalisieren.`
}

function buildBrainstormDoc(log: BrainstormEntry[], project: { name: string; description?: string }): string {
  if (log.length === 0) {
    return `_Brainstorming starten, um Inhalte zu sammeln..._`
  }

  const lines: string[] = []
  lines.push(`# ${project.name}.`)
  if (project.description) {
    lines.push(``)
    lines.push(`> ${project.description}`)
  }
  lines.push(``)
  lines.push(`## 🧠 Ursprüngliche Vision.`)
  lines.push(``)
  lines.push(`> ${log[0]?.text || "—"}`)
  lines.push(``)

  // Sammle alle User-Antworten nach der initialen
  const followUps = log.filter(e => e.role === "user").slice(1)
  if (followUps.length > 0) {
    lines.push(`## 📋 Klärungen.`)
    lines.push(``)
    followUps.forEach((f, i) => {
      lines.push(`### ✅ Antwort ${i + 1}`)
      lines.push(``)
      lines.push(`> ${f.text}`)
      lines.push(``)
    })
  }

  // AI-Insights
  const assistant = log.filter(e => e.role === "assistant")
  if (assistant.length > 0) {
    lines.push(`## 🤖 AI-Insights.`)
    lines.push(``)
    lines.push(`> ${assistant[assistant.length - 1].text}`)
    lines.push(``)
  }

  return lines.join("\n")
}

export default function BrainstormTab({ projectId, project }: { projectId: string; project: { name: string; description?: string } }) {
  const qc = useQueryClient()
  const tts = useTTSContext()
  const [log, setLog] = useState<BrainstormEntry[]>([])
  const [input, setInput] = useState("")
  const chatRef = useRef<HTMLDivElement>(null)

  // Lade bestehende Brainstorming-Einträge vom Backend
  const { data: existing } = useQuery({
    queryKey: ["brainstorm", projectId],
    queryFn: () => api.listBrainstorm(projectId),
  })

  useEffect(() => {
    if (existing) {
      setLog(existing.map((e: any) => ({ id: e.id, role: e.role, text: e.text, ts: e.ts })))
    }
  }, [existing])

  // Speichere User + Assistant
  const sendMut = useMutation({
    mutationFn: async (text: string) => {
      await api.addBrainstorm(projectId, "user", text)
      const reply = generateAssistantReply(text, project.name, log.length)
      await api.addBrainstorm(projectId, "assistant", reply)
      return reply
    },
    onSuccess: (reply, text) => {
      setLog(prev => [...prev, { role: "user", text }, { role: "assistant", text: reply }])
      setInput("")
      setTimeout(() => {
        if (chatRef.current) {
          chatRef.current.scrollTop = chatRef.current.scrollHeight
        }
      }, 100)
    },
  })

  const generateReqMut = useMutation({
    mutationFn: () => api.generateRequirements(projectId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["requirements", projectId] })
      // Tab-Wechsel passiert über Parent
      window.dispatchEvent(new CustomEvent("kanban-tab-change", { detail: "requirements" }))
    },
  })

  const doc = buildBrainstormDoc(log, project)
  const canGenerate = log.length >= 2 // Mindestens 1 Austausch

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontSize: 13, fontWeight: 500, display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{
            display: "inline-block", width: 8, height: 8, borderRadius: "50%",
            background: "var(--color-hermes-accent-orange)", boxShadow: "0 0 4px var(--color-hermes-accent-orange)"
          }} />
          🧠 Brainstorming
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
            TTS: {tts.mode === "click" ? "👆 Klick" : tts.mode === "auto" ? "🔊 Auto" : "🔇 Aus"}
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignItems: "start" }}>
        {/* LINKS: Chat */}
        <div>
          <div ref={chatRef} className="card" style={{ marginBottom: 12, maxHeight: 500, overflow: "auto", minHeight: 400 }}>
            {log.length === 0 && (
              <div style={{ color: "var(--color-hermes-text-secondary)", textAlign: "center", padding: 20 }}>
                Beschreibe dein Projektziel, um mit dem Brainstorming zu beginnen.
              </div>
            )}
            {log.map((entry, i) => (
              <div key={i} style={{
                marginBottom: 8,
                padding: "8px 12px",
                borderRadius: 8,
                background: entry.role === "user" ? "rgba(88,166,255,0.08)" : "rgba(46,160,67,0.08)",
                borderLeft: `3px solid ${entry.role === "user" ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-accent)"}`
              }}>
                <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
                  {entry.role === "user" ? "🗣️ You" : "🤖 AI"}
                </div>
                <div style={{ fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                  {entry.text}
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <DynamicTextarea
              placeholder={canGenerate ? "Any refinements?" : "Describe your vision..."}
              value={input}
              onChange={(e: any) => setInput(e.target.value)}
              onKeyDown={(e: any) => e.key === "Enter" && !e.shiftKey && input.trim() && sendMut.mutate(input.trim())}
              style={{ flex: 1, minWidth: 200, fontFamily: "var(--font-mono)" }}
            />
            <button className="btn" onClick={() => input.trim() && sendMut.mutate(input.trim())} disabled={!input.trim() || sendMut.isPending}>
              <Send size={14} /> Send
            </button>
            <button className="btn" disabled title="Review-Pipeline (v2.1)">
              🔍 Review
            </button>
            <button className="btn" disabled title="Offene Fragen (v2.1)">
              📋 Offene Fragen
            </button>
            {canGenerate && (
              <button className="btn btn-primary" onClick={() => generateReqMut.mutate()} disabled={generateReqMut.isPending}>
                <FileText size={14} /> Generate Requirements
              </button>
            )}
          </div>
        </div>

        {/* RECHTS: Live-MD-Dokument */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <div style={{ fontSize: 12, fontWeight: 500 }}>📄 Live-MD-Dokument (Roh-Material)</div>
            <div style={{ display: "flex", gap: 4 }}>
              <button className="btn" style={{ fontSize: 10, padding: "2px 6px" }} onClick={() => navigator.clipboard.writeText(doc)} title="In Zwischenablage kopieren">
                📋 Copy
              </button>
              <button className="btn" style={{ fontSize: 10, padding: "2px 6px" }} onClick={() => {
                const blob = new Blob([doc], { type: "text/markdown" })
                const url = URL.createObjectURL(blob)
                const a = document.createElement("a")
                a.href = url
                a.download = `${project.name || "brainstorm"}.md`
                a.click()
                URL.revokeObjectURL(url)
              }} title="Als .md-Datei herunterladen">
                💾 Download
              </button>
            </div>
          </div>
          <pre className="card" style={{
            maxHeight: 540, overflow: "auto", padding: 12,
            fontFamily: "var(--font-mono)", fontSize: 12,
            whiteSpace: "pre-wrap", wordBreak: "break-word",
            lineHeight: 1.5, background: "var(--color-hermes-muted)",
            margin: 0,
          }}>
            {doc}
          </pre>
          <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
            Wird im Requirements-Schritt zu sauberem Text weiterverarbeitet. ({doc.length} Zeichen)
          </div>
        </div>
      </div>
    </div>
  )
}

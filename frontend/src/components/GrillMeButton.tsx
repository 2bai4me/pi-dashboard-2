import { useState, useEffect, useRef } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Flame, X, Send, Loader2, CheckCircle2, Plus, Terminal as TerminalIcon,
  ChevronRight,
} from "lucide-react"

interface Question {
  id: string
  category: string
  question: string
  context: string
  priority: string
}

interface GrillResult {
  status: "grilling" | "ready"
  questions: Question[]
  gaps_identified: string[]
  progress: number
  title?: string
  description?: string
  acceptance_criteria?: string[]
  recommended_component?: string
  info_to_record?: Array<{ info_type: string; key: string; value: string; source: string }>
}

interface Component {
  slug: string
  name: string
  type: string | null
  description: string | null
  port: number | null
}

interface GrillSession {
  session_id: string
  project_id: string
  project_name: string
  components: Component[]
  info_package_size: number
  result: GrillResult
}

interface Props {
  projectId: string
  projectName: string
}

function timeStamp(): string {
  const d = new Date()
  return d.toISOString().substring(11, 19)
}

// Terminal-Zeile
function TermLine({
  prompt,
  text,
  color = "#7df59b",
  delay = 0,
}: {
  prompt: string
  text: string | React.ReactNode
  color?: string
  delay?: number
}) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 4, marginBottom: 2 }}>
      <span style={{ color: "#7e9cba", flexShrink: 0 }}>{prompt}</span>
      <span style={{ color, whiteSpace: "pre-wrap", flex: 1 }}>{text}</span>
    </div>
  )
}

export default function GrillMeButton({ projectId, projectName }: Props) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [rawRequest, setRawRequest] = useState("")
  const [session, setSession] = useState<GrillSession | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [history, setHistory] = useState<Array<{ role: "user" | "analyst"; text: string; questions?: Question[]; ts: string }>>([])
  const [isTyping, setIsTyping] = useState(false)
  const terminalRef = useRef<HTMLDivElement>(null)

  // Auto-scroll
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight
    }
  }, [history, isTyping])

  // === Start Grill Session ===
  const startMutation = useMutation({
    mutationFn: async () => {
      const r = await fetch("/api/agents/grill-me/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, raw_request: rawRequest }),
      })
      if (!r.ok) throw new Error("Grill-Me start failed")
      return r.json() as Promise<GrillSession>
    },
    onMutate: () => setIsTyping(true),
    onSettled: () => setIsTyping(false),
    onSuccess: (data) => {
      setSession(data)
      setHistory([
        { role: "user", text: rawRequest, ts: timeStamp() },
        {
          role: "analyst",
          ts: timeStamp(),
          text: `Ich habe ${data.components.length} Components analysiert und ${data.info_package_size} Info-Eintraege gelesen.\nLass mich die kritischsten Luecken identifizieren:`,
          questions: data.result.questions,
        },
      ])
      setAnswers({})
    },
  })

  // === Submit Answers ===
  const answerMutation = useMutation({
    mutationFn: async () => {
      if (!session) return
      const r = await fetch(`/api/agents/grill-me/${session.session_id}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answers }),
      })
      if (!r.ok) throw new Error("Answer failed")
      return r.json() as Promise<{ session_id: string; result: GrillResult; history_count: number }>
    },
    onMutate: () => setIsTyping(true),
    onSettled: () => setIsTyping(false),
    onSuccess: (data) => {
      if (!session) return
      setSession({ ...session, result: data.result })
      const answeredQuestions = session.result.questions.filter(q => answers[q.id])
      setHistory([
        ...history,
        ...answeredQuestions.map(q => ({
          role: "user" as const,
          text: q.question + "\n  > " + (answers[q.id] || "(keine Antwort)"),
          ts: timeStamp(),
        })),
        {
          role: "analyst",
          ts: timeStamp(),
          text: data.result.status === "ready"
            ? "OK PRD ist bulletproof.\nBereite Task-Erstellung vor..."
            : `Naechste Runde. ${data.result.questions.length} neue Fragen identifiziert (Progress: ${data.result.progress || 0}%).`,
          questions: data.result.questions,
        },
      ])
      setAnswers({})
    },
  })

  // === Create Task ===
  const createTaskMutation = useMutation({
    mutationFn: async () => {
      if (!session?.result.title) throw new Error("No title")
      const r = await fetch(`/api/agents/grill-me/${session.session_id}/create-task`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: session.result.title,
          description: session.result.description || "",
          acceptance_criteria: session.result.acceptance_criteria || [],
          recommended_component: session.result.recommended_component,
          priority: 50,
        }),
      })
      if (!r.ok) throw new Error("Task creation failed")
      return r.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kanban"] })
      handleClose()
    },
  })

  const handleClose = () => {
    setOpen(false)
    setRawRequest("")
    setSession(null)
    setAnswers({})
    setHistory([])
  }

  const isReady = session?.result.status === "ready"

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title={`Grill-Me fuer Projekt ${projectName}\n\nSystem-Analyst stellt gezielte Fragen,\nbevor ein Task erstellt wird.\n\nSkill: GRILL_ME_SYSTEM_PROMPT (minimax-m3)`}
        style={{
          background: "linear-gradient(135deg, #ff6b35 0%, #f7931e 100%)",
          color: "#fff",
          border: "1px solid #ff6b35",
          borderRadius: 4,
          padding: "4px 12px",
          fontSize: 13,
          fontWeight: 600,
          cursor: "pointer",
          display: "flex", alignItems: "center", gap: 6,
          boxShadow: "0 2px 8px rgba(255, 107, 53, 0.4)",
        }}
      >
        <Flame size={14} /> Grill Me
      </button>

      {open && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 1000,
          background: "rgba(0,0,0,0.75)",
          display: "flex", alignItems: "center", justifyContent: "center",
          padding: 20,
        }}>
          <div style={{
            background: "#0c0c14",
            border: "1px solid #ff6b35",
            borderRadius: 8,
            width: "min(1100px, 95vw)",
            height: "min(850px, 90vh)",
            display: "flex", flexDirection: "column",
            boxShadow: "0 0 40px rgba(255, 107, 53, 0.3), 0 0 80px rgba(0,0,0,0.5)",
          }}>
            {/* === Terminal-Titlebar === */}
            <div style={{
              background: "linear-gradient(180deg, #1a1a2e 0%, #16162a 100%)",
              borderBottom: "1px solid #ff6b35",
              padding: "8px 12px",
              display: "flex", alignItems: "center", gap: 8,
              fontFamily: "var(--font-mono, monospace)",
            }}>
              <div style={{ display: "flex", gap: 5 }}>
                <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ff5f56" }} />
                <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ffbd2e" }} />
                <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#27c93f" }} />
              </div>
              <TerminalIcon size={13} color="#ff6b35" />
              <span style={{ color: "#ff6b35", fontSize: 12, fontWeight: 600, flex: 1 }}>
                grill-me@pi-dashboard:~/projects/{projectId}
              </span>
              <span style={{ color: "#7e9cba", fontSize: 10 }}>
                {session
                  ? `SESSION=${session.session_id} | STATUS=${session.result.status.toUpperCase()}`
                  : "READY"}
              </span>
              <button
                onClick={handleClose}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 2 }}
              >
                <X size={14} color="#7e9cba" />
              </button>
            </div>

            {/* === Terminal-Body === */}
            <div
              ref={terminalRef}
              style={{
                flex: 1, overflowY: "auto", padding: 12,
                background: "#0c0c14",
                fontFamily: "var(--font-mono, 'Cascadia Code', 'JetBrains Mono', 'Consolas', monospace)",
                fontSize: 12.5,
                lineHeight: 1.5,
                color: "#7df59b",
              }}
            >
              {/* ASCII-Header */}
              <pre style={{ color: "#ff6b35", margin: "0 0 8px 0", fontSize: 11, lineHeight: 1.1 }}>
{`╔══════════════════════════════════════════════════════════════════════╗
║  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄    ║
║  ▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌   ║
║  ▐░█▀▀▀▀▀█░░▌ ▀▀█░█▀▀▀▀▀█░▌▐░█▀▀▀▀▀█░▌ ▐░█▀▀▀█░█▀▀▀▀ ▐░█▀▀▀▀▀█░░▌   ║
║  ▐░▌     ▐░▌    ▐░▌     ▐░▌▐░▌     ▐░▌ ▐░▌   ▐░▌     ▐░▌     ▐░▌   ║
║  ▐░▌     ▐░▌    ▐░▌     ▐░▌▐░▌     ▐░▌ ▐░▌   ▐░▌     ▐░▌     ▐░▌   ║
║  ▐░▌     ▐░▌    ▐░▌     ▐░▌▐░▌     ▐░▌ ▐░▌   ▐░▌     ▐░▌     ▐░▌   ║
║  ▐░▌     ▐░▌    ▐░▌     ▐░▌▐░▌     ▐░▌ ▐░▌   ▐░▌     ▐░▌     ▐░▌   ║
║  ▐░█▄▄▄▄▄█░▌    ▐░█▄▄▄▄▄█░▌▐░█▄▄▄▄▄█░▌ ▐░█▄▄▄█░█▄▄▄▄ ▐░█▄▄▄▄▄█░░▌   ║
║  ▐░░░░░░░░░░░▌  ▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌   ║
║   ▀▀▀▀▀▀▀▀▀▀▀    ▀▀▀▀▀▀▀▀▀▀▀  ▀▀▀▀▀▀▀▀▀▀▀  ▀▀▀▀▀▀▀▀▀▀▀  ▀▀▀▀▀▀▀▀▀▀▀    ║
║                                                                      ║
║  System-Analyst fuer bulletproof PRD (User-Direktive 24.06.2026)    ║
╚══════════════════════════════════════════════════════════════════════╝`}
              </pre>

              {/* Initial-Phase: User-Input */}
              {!session && (
                <div>
                  <TermLine prompt={`grill-me@pi-dashboard:${timeStamp()}$`}
                    text="Grill-Session wird initialisiert..." color="#ffbd2e" />
                  <TermLine prompt={`grill-me@pi-dashboard:${timeStamp()}$`}
                    text={`Projekt: ${projectName} (${projectId})`} color="#7e9cba" />
                  <TermLine prompt={`grill-me@pi-dashboard:${timeStamp()}$`}
                    text="Skill geladen: GRILL_ME_SYSTEM_PROMPT (minimax-m3)"
                    color="#7df59b" />
                  <TermLine prompt={`grill-me@pi-dashboard:${timeStamp()}$`}
                    text="Warte auf User-Anfrage..." color="#7e9cba" />
                  <div style={{ marginTop: 12, marginBottom: 8 }}>
                    <label style={{ color: "#ff6b35", fontSize: 11, display: "block", marginBottom: 4 }}>
                      {'>'} User-Anfrage eingeben (Enter=Submit, Shift+Enter=Newline):
                    </label>
                    <textarea
                      className="textarea"
                      rows={6}
                      value={rawRequest}
                      onChange={(e) => setRawRequest(e.target.value)}
                      placeholder="z.B. 'Der Frontend-Container soll dunkles Theme bekommen' oder 'Pipeline soll nach Redis umziehen'"
                      style={{
                        width: "100%", fontSize: 12.5, padding: 8,
                        background: "#16162a", color: "#7df59b",
                        border: "1px solid #2a2a40", borderRadius: 4,
                        fontFamily: "var(--font-mono, monospace)",
                        resize: "vertical",
                      }}
                    />
                  </div>
                  <div style={{ color: "#7e9cba", fontSize: 10.5, marginTop: 4 }}>
                    <span style={{ color: "#ffbd2e" }}>INFO:</span> Der Grill-Analyst wird:
                    {"\n"}  - Luecken identifizieren (Edge Cases, fehlende Constraints)
                    {"\n"}  - Gezielte "Was passiert wenn..."-Fragen stellen
                    {"\n"}  - Logic-Stress-Tests durchfuehren
                    {"\n"}  - Bei bulletproof PRD automatisch Task erstellen
                  </div>
                </div>
              )}

              {/* Chat-Phase: History + Questions */}
              {session && (
                <div>
                  {history.map((msg, i) => (
                    <div key={i} style={{ marginBottom: 8 }}>
                      {msg.role === "user" ? (
                        <>
                          <TermLine
                            prompt={`user@grill-me [${msg.ts}]$`}
                            text="cat << 'EOF' | grill-analyst"
                            color="#88aaff"
                          />
                          <div style={{
                            background: "rgba(136,170,255,0.05)",
                            borderLeft: "2px solid #88aaff",
                            padding: "4px 12px",
                            marginLeft: 8,
                            marginBottom: 2,
                            color: "#cfd8ff",
                          }}>
                            {msg.text}
                          </div>
                          <TermLine prompt={`user@grill-me [${msg.ts}]$`} text="EOF" color="#88aaff" />
                        </>
                      ) : (
                        <>
                          <TermLine
                            prompt={`grill-analyst [${msg.ts}]$`}
                            text={msg.text}
                            color="#7df59b"
                          />
                          {msg.questions?.map((q, qi) => (
                            <div key={q.id} style={{
                              marginTop: 4, marginLeft: 12, padding: "6px 10px",
                              background: "rgba(125,245,155,0.04)",
                              borderLeft: `3px solid ${q.priority === "high" ? "#ff5f56" : "#ffbd2e"}`,
                              marginBottom: 4,
                            }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                                <ChevronRight size={11} color="#ff6b35" />
                                <span style={{
                                  color: q.priority === "high" ? "#ff5f56" : "#ffbd2e",
                                  fontSize: 10, fontWeight: 600,
                                }}>Q{qi + 1}.[{q.category}]</span>
                                <span style={{ color: "#ffbd2e", fontSize: 11, fontWeight: 600 }}>
                                  {q.question}
                                </span>
                              </div>
                              {q.context && (
                                <div style={{ color: "#7e9cba", fontSize: 10.5, marginTop: 3, marginLeft: 18 }}>
                                  <span style={{ color: "#ff6b35" }}>//</span> {q.context}
                                </div>
                              )}
                            </div>
                          ))}
                        </>
                      )}
                    </div>
                  ))}

                  {/* Typing-Indicator */}
                  {isTyping && (
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
                      <span style={{ color: "#7df59b" }}>grill-analyst [${timeStamp()}]$</span>
                      <span style={{ color: "#ffbd2e" }}>verarbeite</span>
                      <span style={{
                        display: "inline-block",
                        animation: "blink 1s infinite",
                        color: "#7df59b",
                      }}>█</span>
                    </div>
                  )}

                  {/* Answer-Inputs */}
                  {!isReady && session.result.questions.length > 0 && !isTyping && (
                    <div style={{ marginTop: 12, paddingTop: 8, borderTop: "1px dashed #2a2a40" }}>
                      <TermLine
                        prompt={`user@grill-me [${timeStamp()}]$`}
                        text={`# Antworten auf ${session.result.questions.length} offene Fragen eingeben:`}
                        color="#88aaff"
                      />
                      {session.result.questions.map((q) => (
                        <div key={q.id} style={{ marginTop: 6, marginLeft: 8 }}>
                          <label style={{ color: "#ffbd2e", fontSize: 11, display: "block", marginBottom: 2 }}>
                            {'>'} A[{q.id}] ({q.category}):
                          </label>
                          <textarea
                            className="textarea"
                            rows={2}
                            value={answers[q.id] || ""}
                            onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
                            style={{
                              width: "100%", fontSize: 11.5, padding: 6,
                              background: "#16162a", color: "#cfd8ff",
                              border: "1px solid #2a2a40", borderRadius: 4,
                              fontFamily: "var(--font-mono, monospace)",
                            }}
                          />
                        </div>
                      ))}
                    </div>
                  )}

                  {/* PRD-Ready */}
                  {isReady && session.result.title && (
                    <div style={{
                      marginTop: 12, padding: 10,
                      background: "rgba(39,201,63,0.08)",
                      border: "1px solid #27c93f", borderRadius: 4,
                    }}>
                      <TermLine
                        prompt={`grill-analyst [${timeStamp()}]$`}
                        text="STATUS: READY (PRD bulletproof)" color="#27c93f"
                      />
                      <div style={{ marginTop: 6, marginLeft: 12 }}>
                        <div style={{ color: "#ffbd2e", fontSize: 12, fontWeight: 600 }}>
                          + TASK: {session.result.title}
                        </div>
                        {session.result.description && (
                          <div style={{ color: "#cfd8ff", fontSize: 11, marginTop: 4, marginBottom: 4 }}>
                            {session.result.description}
                          </div>
                        )}
                        {session.result.acceptance_criteria && session.result.acceptance_criteria.length > 0 && (
                          <div style={{ color: "#7e9cba", fontSize: 11, marginTop: 4 }}>
                            <span style={{ color: "#ff6b35" }}>ACCEPTANCE_CRITERIA:</span>
                            {session.result.acceptance_criteria.map((ac, i) => (
                              <div key={i} style={{ marginLeft: 12 }}>
                                {"\n"}  [+] {ac}
                              </div>
                            ))}
                          </div>
                        )}
                        {session.result.recommended_component && (
                          <div style={{ color: "#7e9cba", fontSize: 10.5, marginTop: 4 }}>
                            <span style={{ color: "#ff6b35" }}>COMPONENT:</span> {session.result.recommended_component}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* === Terminal-Prompt (immer am Ende) === */}
              {!isTyping && (
                <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 8 }}>
                  <span style={{ color: "#7df59b" }}>
                    {session ? `grill-analyst [${timeStamp()}]$` : `user@grill-me [${timeStamp()}]$`}
                  </span>
                  <span style={{
                    display: "inline-block",
                    width: 8, height: 14,
                    background: "#7df59b",
                    animation: "blink 1s infinite",
                    marginLeft: 2,
                  }} />
                </div>
              )}
            </div>

            {/* === Status-Bar (unten) === */}
            <div style={{
              background: "linear-gradient(180deg, #16162a 0%, #1a1a2e 100%)",
              borderTop: "1px solid #2a2a40",
              padding: "6px 12px",
              display: "flex", alignItems: "center", gap: 16,
              fontFamily: "var(--font-mono, monospace)",
              fontSize: 10,
            }}>
              <span style={{ color: "#7df59b" }}>● ONLINE</span>
              <span style={{ color: "#7e9cba" }}>SKILL: GRILL_ME_SYSTEM_PROMPT</span>
              <span style={{ color: "#7e9cba" }}>MODEL: minimax-m3</span>
              <span style={{ color: "#7e9cba" }}>PROVIDER: minimax-direct</span>
              {session && (
                <>
                  <span style={{ color: "#ffbd2e" }}>ROUND: {session ? Math.ceil((history.filter(h => h.role === 'analyst').length)) : 0}</span>
                  <span style={{ color: "#ffbd2e" }}>PROGRESS: {session?.result.progress ?? 0}%</span>
                </>
              )}
              <div style={{ flex: 1 }} />
              <span style={{ color: "#7e9cba" }}>{projectName}</span>
            </div>

            {/* === Action-Bar === */}
            <div style={{
              background: "#1a1a2e",
              borderTop: "1px solid #2a2a40",
              padding: "8px 12px",
              display: "flex", gap: 8, justifyContent: "flex-end",
            }}>
              {!session ? (
                <>
                  <button
                    className="btn btn-sm"
                    onClick={handleClose}
                    style={{ background: "#2a2a40", color: "#7e9cba", border: "1px solid #2a2a40" }}
                  >
                    [ESC] Abbrechen
                  </button>
                  <button
                    onClick={() => startMutation.mutate()}
                    disabled={!rawRequest.trim() || startMutation.isPending}
                    style={{
                      background: !rawRequest.trim() || startMutation.isPending ? "#2a2a40" : "#ff6b35",
                      color: !rawRequest.trim() || startMutation.isPending ? "#7e9cba" : "#fff",
                      border: "none", borderRadius: 4, padding: "6px 16px",
                      fontSize: 12, fontWeight: 600, cursor: !rawRequest.trim() || startMutation.isPending ? "not-allowed" : "pointer",
                      display: "flex", alignItems: "center", gap: 6,
                      fontFamily: "var(--font-mono, monospace)",
                    }}
                  >
                    {startMutation.isPending
                      ? <><Loader2 size={12} className="spin" /> ANALYSE...</>
                      : <><Flame size={12} /> [ENTER] GRILL STARTEN</>}
                  </button>
                </>
              ) : isReady ? (
                <>
                  <button
                    className="btn btn-sm"
                    onClick={handleClose}
                    style={{ background: "#2a2a40", color: "#7e9cba", border: "1px solid #2a2a40" }}
                  >
                    [ESC] Schliessen
                  </button>
                  <button
                    onClick={() => createTaskMutation.mutate()}
                    disabled={createTaskMutation.isPending}
                    style={{
                      background: "#27c93f", color: "#0c0c14",
                      border: "none", borderRadius: 4, padding: "6px 16px",
                      fontSize: 12, fontWeight: 700, cursor: "pointer",
                      display: "flex", alignItems: "center", gap: 6,
                      fontFamily: "var(--font-mono, monospace)",
                    }}
                  >
                    {createTaskMutation.isPending
                      ? <><Loader2 size={12} className="spin" /> ERSTELLE...</>
                      : <><Plus size={12} /> [ENTER] TASK ERSTELLEN</>}
                  </button>
                </>
              ) : (
                <>
                  <button
                    className="btn btn-sm"
                    onClick={handleClose}
                    style={{ background: "#2a2a40", color: "#7e9cba", border: "1px solid #2a2a40" }}
                  >
                    [ESC] Abbrechen
                  </button>
                  <button
                    onClick={() => answerMutation.mutate()}
                    disabled={Object.keys(answers).length === 0 || answerMutation.isPending}
                    style={{
                      background: Object.keys(answers).length === 0 || answerMutation.isPending ? "#2a2a40" : "#ff6b35",
                      color: Object.keys(answers).length === 0 || answerMutation.isPending ? "#7e9cba" : "#fff",
                      border: "none", borderRadius: 4, padding: "6px 16px",
                      fontSize: 12, fontWeight: 600,
                      cursor: Object.keys(answers).length === 0 || answerMutation.isPending ? "not-allowed" : "pointer",
                      display: "flex", alignItems: "center", gap: 6,
                      fontFamily: "var(--font-mono, monospace)",
                    }}
                  >
                    {answerMutation.isPending
                      ? <><Loader2 size={12} className="spin" /> VERARBEITE...</>
                      : <><Send size={12} /> [ENTER] ANTWORTEN SENDEN</>}
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Blink-Animation */}
          <style>{`
            @keyframes blink { 0%, 49% { opacity: 1; } 50%, 100% { opacity: 0; } }
            .spin { animation: spin 1s linear infinite; }
            @keyframes spin { 100% { transform: rotate(360deg); } }
          `}</style>
        </div>
      )}
    </>
  )
}
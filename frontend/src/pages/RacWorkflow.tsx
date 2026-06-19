// RacWorkflow.tsx — Ansicht der Verantwortlichkeiten (RACI) und Standard-Workflows
// Quelle: OpenBrain bB + docs/RACI-WORKFLOW.md (16.06.2026)
// User-Direktive 16.06.2026: "Erstelle eine Ansicht der Verantwortlichkeiten und
// Abläufe bei der Softwareentwicklung aus dem OpenBrain"
import { useState } from "react"
import {
  Crown, HardHat, Wallet, Megaphone, Code2, FlaskConical, Eye, Wrench,
  ChevronRight, ChevronDown, Shield, AlertTriangle, CheckCircle2,
  GitBranch, FileText, FileCode2, Users, ListChecks, Target, Lightbulb,
} from "lucide-react"

// === Datenstrukturen ===
type Role = {
  key: string
  name: string
  emoji: string
  icon: any
  layer: "owner" | "c-level" | "sub-agent"
  level: number  // 0 = oben, 1 = mitte, 2 = unten
  provider: string
  model: string
  task: string
}

type WorkflowStep = {
  num: number
  from: string
  to: string
  agent: string
  description: string
  details?: string[]
}

type TriageCheck = {
  num: number
  title: string
  icon: any
  color: string
  fields: { key: string; required: boolean; description: string }[]
  example?: string
}

type ArchitectureRule = {
  key: string
  name: string
  description: string
  severity: "high" | "medium" | "low"
}

type BestPractice = {
  num: number
  title: string
  effort: string
  effect: string
  phase: "quick" | "mid" | "strategy"
}

type GovernanceRule = {
  num: number
  rule: string
  consequence: string
}

// === Daten aus OpenBrain (16.06.2026) ===
const ROLES: Role[] = [
  { key: "owner",     name: "Owner",     emoji: "👤", icon: Crown,      layer: "owner",      level: 0, provider: "Mensch",       model: "—",                          task: "Strategische Entscheidungen, Vision, Budget" },
  { key: "ceo",       name: "CEO-digital", emoji: "👑", icon: Crown,    layer: "c-level",    level: 1, provider: "minimax-direct", model: "minimax-m3",              task: "Orchestrierung — NIE Code-Entwicklung!" },
  { key: "cio",       name: "CIO",       emoji: "🏗️", icon: HardHat,   layer: "c-level",    level: 1, provider: "ollama",        model: "gemma4:12b",             task: "Triage, Standards, Worker-Assignment, Final-Review" },
  { key: "cfo",       name: "CFO",       emoji: "💰", icon: Wallet,    layer: "c-level",    level: 1, provider: "ollama",        model: "gemma4:12b",             task: "Finanzen, Budget-Kontrolle, Cost-Tracking" },
  { key: "cmo",       name: "CMO",       emoji: "📢", icon: Megaphone,  layer: "c-level",    level: 1, provider: "ollama",        model: "gemma4:12b",             task: "Marketing, externe Kommunikation" },
  { key: "pi-coder",  name: "pi-coder",  emoji: "💻", icon: Code2,     layer: "sub-agent",  level: 2, provider: "minimax-direct", model: "minimax-m3",              task: "Code schreiben, editieren, implementieren" },
  { key: "pi-tester", name: "pi-tester", emoji: "🧪", icon: FlaskConical, layer: "sub-agent", level: 2, provider: "minimax-direct", model: "minimax-m3",           task: "Tests, Code-Review, Bug-Suche" },
  { key: "pi-reviewer", name: "pi-reviewer", emoji: "👁️", icon: Eye, layer: "sub-agent",  level: 2, provider: "minimax-direct", model: "minimax-m3",              task: "Code-Review vor Merge" },
  { key: "pi-fixer",  name: "pi-fixer",  emoji: "🔧", icon: Wrench,    layer: "sub-agent",  level: 2, provider: "minimax-direct", model: "minimax-m3",              task: "Bug-Behebung, Refactoring" },
]

const WORKFLOW_STEPS: WorkflowStep[] = [
  { num: 0, from: "—", to: "triage",  agent: "User",       description: "Task-Erstellung", details: ["User/CEO erstellt Task im Kanban", "Task kommt in Triage-Spalte"] },
  { num: 1, from: "triage", to: "todo",       agent: "CIO",        description: "Schritt 0: CIO Triage Review (4 Prüfungen)", details: ["Task-Typ klassifizieren (new_request/change/ticket/bugfix)", "Standardvorgaben-Konformität prüfen (10 Architektur-Regeln)", "Änderungsbeschreibung strukturieren (files, routes, api_changes, db_changes, notes)", "Subagent-Readiness bewerten (model, branch, context_files, success_criteria)"] },
  { num: 2, from: "todo",   to: "todo (assigned)", agent: "CIO",   description: "Worker Assignment", details: ["CIO wählt passenden Sub-Agent", "pi-coder für Code, pi-tester für Diagnose, pi-fixer für Bugs, pi-reviewer für Review"] },
  { num: 3, from: "todo",   to: "in_progress", agent: "pi-coder",   description: "Worker Implementation", details: ["Auto-claim nach 5s Delay", "Implementiert auf eigenem Git-Branch", "Committet regelmäßig", "Respektiert Token-Budget und Cost-Limit"] },
  { num: 4, from: "in_progress", to: "review", agent: "pi-coder",   description: "Submit for Review", details: ["Worker schiebt fertigen Code zur Review", "Übergibt Notizen an Tester"] },
  { num: 5, from: "review", to: "rueckfrage/block", agent: "pi-tester", description: "Tester Code-Review", details: ["Prüft Code-Qualität, Tests, Standards", "Bei OK: BLOCK + Auto-Create [FREIGABE]-Sub-Task für CIO", "Bei Reject: zurück zu in_progress (Iteration++)"] },
  { num: 6, from: "rueckfrage", to: "done",   agent: "CIO",        description: "CIO Final-Review (Freigabe)", details: ["CIO prüft gegen Standards", "Approve: → DONE", "Reject: zurück zu in_progress oder todo"] },
]

const TRIAGE_CHECKS: TriageCheck[] = [
  {
    num: 1,
    title: "Task-Typ-Klassifizierung",
    icon: ListChecks,
    color: "var(--color-hermes-accent)",
    fields: [
      { key: "new_request", required: true, description: "Komplett neue Anforderung" },
      { key: "change",      required: true, description: "Änderung an Bestehendem" },
      { key: "ticket",      required: true, description: "User meldet was nicht funktioniert" },
      { key: "bugfix",      required: true, description: "Von Agenten gefunden (interner Fehler)" },
    ],
    example: 'Beispiel: task.task_type = "new_request"',
  },
  {
    num: 2,
    title: "Standardvorgaben-Konformität",
    icon: Shield,
    color: "var(--color-hermes-accent-blue)",
    fields: [
      { key: "matches",  required: true, description: "Liste der Architektur-Regeln, die erfüllt sind" },
      { key: "missing",  required: true, description: "Liste der Regeln, die ergänzt werden müssen" },
      { key: "checked_at", required: true, description: "Zeitstempel der Prüfung" },
    ],
    example: 'Prüfung gegen 10 Architektur-Regeln (siehe unten)',
  },
  {
    num: 3,
    title: "Änderungsbeschreibung",
    icon: FileText,
    color: "var(--color-hermes-accent-orange)",
    fields: [
      { key: "files",             required: true,  description: "Liste der zu ändernden Dateien" },
      { key: "notes",             required: true,  description: "Detaillierte Beschreibung der Änderung" },
      { key: "routes",            required: false, description: "Neue/geänderte API-Routen" },
      { key: "api_changes",       required: false, description: "Request/Response-Schema-Änderungen" },
      { key: "database_changes",  required: false, description: "Schema-Migrationen, neue Tabellen" },
    ],
    example: '{ files: ["backend/app/main.py"], notes: "Add health check endpoint", routes: ["/api/health"] }',
  },
  {
    num: 4,
    title: "Subagent-Readiness",
    icon: Wrench,
    color: "var(--color-hermes-danger)",
    fields: [
      { key: "model",            required: true,  description: "Provider + Model (z.B. minimax-m3)" },
      { key: "branch",           required: true,  description: "Git-Branch für die Implementierung" },
      { key: "context_files",    required: true,  description: "Relevante Dateien für Kontext" },
      { key: "success_criteria", required: true,  description: "Kriterien, wann der Task als 'done' gilt" },
      { key: "token_budget",     required: false, description: "Maximale Token für LLM-Aufrufe" },
      { key: "cost_limit_usd",   required: false, description: "Maximale Kosten in USD" },
      { key: "tools",            required: false, description: "Tool-Whitelist (read, write, bash, ...)" },
      { key: "timeout_s",        required: false, description: "Timeout in Sekunden" },
    ],
    example: '{ model: "minimax-m3", branch: "task/14afd8892448", context_files: [...], success_criteria: [...] }',
  },
]

const ARCH_RULES: ArchitectureRule[] = [
  { key: "arch-soa",            name: "Service-Oriented Architecture",  description: "Alles wird im Architektur-Geiste von SOA entwickelt", severity: "high" },
  { key: "arch-microservices",  name: "Microservices-Architektur",      description: "Jeder Service besteht aus Microservices (Schema-per-Tenant)", severity: "high" },
  { key: "arch-fastapi",        name: "Python 3.11+ / FastAPI",         description: "ME4-Standard: Python 3.11+ / FastAPI als Backend-Stack", severity: "medium" },
  { key: "arch-no-nodejs",      name: "KEIN Node.js",                  description: "Konsistenz mit FastAPI-Ökosystem (kein Node.js)", severity: "medium" },
  { key: "arch-llm-primary",    name: "LLM Primary + Fallback",        description: "minimax/minimax-m3 als PRIMARY, Ollama als Fallback", severity: "high" },
  { key: "arch-swarm-roles",    name: "Sub-Agent-Rollen-Set",          description: "pi-coder, pi-tester, pi-reviewer, pi-fixer, CIO, CEO-digital", severity: "high" },
  { key: "arch-cost-tracking",  name: "Token-Budget + Cost-Limit",     description: "Pro Sub-Agent werden Token-Budget und Cost-Limit gesetzt", severity: "high" },
  { key: "arch-git-branch",     name: "Git-Branch pro Task",           description: "Jeder Task bekommt eigenen Git-Branch (Rollback-Sicherheit)", severity: "medium" },
  { key: "arch-task-locking",   name: "Task-Locking",                  description: "Keine Doppelbearbeitung — Task wird gelockt während Bearbeitung", severity: "medium" },
  { key: "arch-multi-tenant",   name: "Multi-Tenant-Architektur",      description: "Schema-per-Tenant für Mandantenfähigkeit", severity: "high" },
]

const BEST_PRACTICES: BestPractice[] = [
  { num: 1, title: "Pre-Commit-Hooks (ruff, eslint, prettier, gitleaks)", effort: "1 Tag",  effect: "Fängt Fehler Minuten statt Stunden nach dem Schreiben", phase: "quick" },
  { num: 2, title: "Type-Checking in CI/CD (mypy --strict, tsc --noEmit)", effort: "1 Tag",  effect: "Pflicht-Gate vor Merge in main", phase: "quick" },
  { num: 3, title: "Structured Error-Logging mit Business-Kontext",     effort: "2 Tage", effect: "Schnellere Debug-Suche (video_id, user_id, service, trace_id)", phase: "quick" },
  { num: 4, title: "OpenTelemetry Traces (verteilte Traces)",           effort: "1 Woche", effect: "Trace vom Frontend bis Backend sichtbar", phase: "mid" },
  { num: 5, title: "RED-Metriken pro Service (Rate/Errors/Duration)",    effort: "1 Woche", effect: "Prometheus-Dashboards + Alerting", phase: "mid" },
  { num: 6, title: "SLOs + Error-Budget-Alerting",                      effort: "2 Wochen", effect: "Alert nur bei Budget-Burn, nicht bei Einzelfehlern", phase: "strategy" },
  { num: 7, title: "Feature-Flags",                                      effort: "1 Woche", effect: "Instant Rollback für neue Endpoints", phase: "strategy" },
  { num: 8, title: "Centralized Error-Tracking (Sentry)",                effort: "3 Tage", effect: "Alle Services + Frontend in einem Dashboard", phase: "strategy" },
]

const GOVERNANCE: GovernanceRule[] = [
  { num: 1, rule: "CEO(digital) entwickelt NIE selbst Code — NUR Orchestrierung",   consequence: "SOFORT Complaint-Task + Fix-Task im cio-board" },
  { num: 2, rule: "Alle Entwicklung läuft über KANBAN → CIO → PI-Agenten",           consequence: "Task wird zurück in Triage geschoben" },
  { num: 3, rule: "JEDER KANBAN-Task MUSS Präfix 'BUGFIX:' oder 'NEW:' im Titel haben", consequence: "Task wird abgelehnt" },
  { num: 4, rule: "Bei Prozessverstoß (Direktentwicklung): Sofort eskalieren",        consequence: "Keine Ausnahme — auch nicht bei Dringlichkeit" },
  { num: 5, rule: "RACI-Prinzip: Genau 1 Verantwortlicher pro Task",                  consequence: "Klärungs-Aktion, bis Eindeutigkeit herrscht" },
]

// === Severity-Farbe ===
function severityColor(s: ArchitectureRule["severity"]): string {
  if (s === "high") return "var(--color-hermes-danger)"
  if (s === "medium") return "var(--color-hermes-accent-orange)"
  return "var(--color-hermes-text-secondary)"
}

function phaseColor(p: BestPractice["phase"]): string {
  if (p === "quick") return "var(--color-hermes-accent)"
  if (p === "mid") return "var(--color-hermes-accent-blue)"
  return "var(--color-hermes-accent-orange)"
}

function phaseLabel(p: BestPractice["phase"]): string {
  if (p === "quick") return "Quick Win"
  if (p === "mid") return "Mittelfristig"
  return "Strategisch"
}

export default function RacWorkflow() {
  const [openWorkflowStep, setOpenWorkflowStep] = useState<number | null>(null)
  const [openTriageCheck, setOpenTriageCheck] = useState<number | null>(1)
  const [openSection, setOpenSection] = useState<Record<string, boolean>>({
    hierarchy: true, workflow: true, triage: true, rules: true, governance: true, best: true, cheat: false,
  })
  const [selectedRole, setSelectedRole] = useState<string>("cio")

  function toggle(s: string) {
    setOpenSection((prev) => ({ ...prev, [s]: !prev[s] }))
  }

  const ownerRoles = ROLES.filter((r) => r.layer === "owner")
  const cLevelRoles = ROLES.filter((r) => r.layer === "c-level")
  const subAgentRoles = ROLES.filter((r) => r.layer === "sub-agent")
  const selectedRoleData = ROLES.find((r) => r.key === selectedRole)

  return (
    <div>
      {/* === Header === */}
      <div className="page-header">
        <div className="workspace-header">
          <FileCode2 size={22} color="var(--color-hermes-accent-blue)" />
          <h1>RACI &amp; Standard-Workflow</h1>
        </div>
        <p>
          Verantwortlichkeiten &amp; Abläufe bei der Softwareentwicklung — aus dem
          <strong style={{ color: "var(--color-hermes-accent-blue)" }}> OpenBrain (bB)</strong> aggregiert.
          Quelle: <code style={{ color: "var(--color-hermes-accent)" }}>docs/RACI-WORKFLOW.md</code> · 16.06.2026
        </p>
      </div>

      {/* === HIERARCHIE === */}
      <div className="card mb-3">
        <div
          style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: openSection.hierarchy ? 12 : 0 }}
          onClick={() => toggle("hierarchy")}
        >
          {openSection.hierarchy ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <Users size={16} color="var(--color-hermes-accent-blue)" />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>1. Hierarchie &amp; Rollen</h2>
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginLeft: 8 }}>{ROLES.length} Rollen</span>
        </div>

        {openSection.hierarchy && (
          <>
            <p style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", margin: "0 0 12px", lineHeight: 1.5 }}>
              <strong>RACI-Prinzip:</strong> Jeder Task hat GENAU EINEN Verantwortlichen. Keine unklaren Zuständigkeiten.
              Owner (Mensch) → CEO-digital (Orchestrierung) → C-Level (Taktik) → Sub-Agents (Operativ).
            </p>

            {/* Layer 0: Owner */}
            <div style={{ display: "flex", justifyContent: "center", marginBottom: 8 }}>
              {ownerRoles.map((r) => (
                <div
                  key={r.key}
                  onClick={() => setSelectedRole(r.key)}
                  style={{
                    background: "var(--color-hermes-surface-2)",
                    border: `2px solid ${selectedRole === r.key ? "var(--color-hermes-accent)" : "var(--color-hermes-border)"}`,
                    borderRadius: 8,
                    padding: "8px 16px",
                    cursor: "pointer",
                    minWidth: 160,
                    textAlign: "center",
                    boxShadow: selectedRole === r.key ? "0 0 12px rgba(46,160,67,0.4)" : "none",
                  }}
                >
                  <div style={{ fontSize: 24 }}>{r.emoji}</div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>{r.name}</div>
                  <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{r.task}</div>
                </div>
              ))}
            </div>

            {/* Connector Lines */}
            <div style={{ display: "flex", justifyContent: "center", marginBottom: 4 }}>
              <div style={{ width: 1, height: 16, background: "var(--color-hermes-border)" }} />
            </div>

            {/* Layer 1: C-Level */}
            <div style={{ display: "flex", justifyContent: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
              {cLevelRoles.map((r) => {
                const Icon = r.icon
                return (
                  <div
                    key={r.key}
                    onClick={() => setSelectedRole(r.key)}
                    style={{
                      background: "var(--color-hermes-surface)",
                      border: `2px solid ${selectedRole === r.key ? "var(--color-hermes-accent)" : "var(--color-hermes-border)"}`,
                      borderRadius: 8,
                      padding: "8px 12px",
                      cursor: "pointer",
                      minWidth: 130,
                      boxShadow: selectedRole === r.key ? "0 0 12px rgba(46,160,67,0.4)" : "none",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <Icon size={14} color="var(--color-hermes-accent-blue)" />
                      <span style={{ fontSize: 18 }}>{r.emoji}</span>
                      <span style={{ fontSize: 12, fontWeight: 600 }}>{r.name}</span>
                    </div>
                    <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 2, lineHeight: 1.3 }}>{r.task}</div>
                  </div>
                )
              })}
            </div>

            {/* Connector Lines */}
            <div style={{ display: "flex", justifyContent: "center", marginBottom: 4 }}>
              <div style={{ width: 1, height: 16, background: "var(--color-hermes-border)" }} />
            </div>

            {/* Layer 2: Sub-Agents */}
            <div style={{ display: "flex", justifyContent: "center", gap: 8, flexWrap: "wrap" }}>
              {subAgentRoles.map((r) => {
                const Icon = r.icon
                return (
                  <div
                    key={r.key}
                    onClick={() => setSelectedRole(r.key)}
                    style={{
                      background: "var(--color-hermes-muted)",
                      border: `2px solid ${selectedRole === r.key ? "var(--color-hermes-accent)" : "var(--color-hermes-border)"}`,
                      borderRadius: 8,
                      padding: "6px 10px",
                      cursor: "pointer",
                      minWidth: 120,
                      boxShadow: selectedRole === r.key ? "0 0 12px rgba(46,160,67,0.4)" : "none",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <Icon size={12} color="var(--color-hermes-accent)" />
                      <span style={{ fontSize: 16 }}>{r.emoji}</span>
                      <span style={{ fontSize: 11, fontWeight: 600 }}>{r.name}</span>
                    </div>
                    <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)", marginTop: 2, lineHeight: 1.3 }}>{r.task}</div>
                  </div>
                )
              })}
            </div>

            {/* Role-Details Panel */}
            {selectedRoleData && (
              <div
                style={{
                  marginTop: 16,
                  padding: 12,
                  background: "var(--color-hermes-muted)",
                  borderRadius: 6,
                  border: "1px solid var(--color-hermes-border)",
                  borderLeft: `3px solid var(--color-hermes-accent)`,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <span style={{ fontSize: 28 }}>{selectedRoleData.emoji}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 16, fontWeight: 600 }}>{selectedRoleData.name}</div>
                    <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>{selectedRoleData.task}</div>
                  </div>
                  <div style={{ display: "flex", gap: 4, flexDirection: "column", alignItems: "flex-end" }}>
                    <span className="badge badge-blue" style={{ fontSize: 10 }}>
                      {selectedRoleData.provider}
                    </span>
                    <span className="badge badge-gray" style={{ fontSize: 10 }}>
                      {selectedRoleData.model}
                    </span>
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: "4px 12px", fontSize: 12 }}>
                  <span style={{ color: "var(--color-hermes-text-secondary)" }}>Layer:</span>
                  <span>
                    {selectedRoleData.layer === "owner" && "Owner (Mensch)"}
                    {selectedRoleData.layer === "c-level" && "C-Level (Taktik)"}
                    {selectedRoleData.layer === "sub-agent" && "Sub-Agent (Operativ)"}
                  </span>
                  <span style={{ color: "var(--color-hermes-text-secondary)" }}>Hauptaufgabe:</span>
                  <span>{selectedRoleData.task}</span>
                </div>
              </div>
            )}

            {/* Rollen-Tabelle */}
            <h3 style={{ fontSize: 13, fontWeight: 600, margin: "16px 0 8px" }}>📋 Rollen im Detail</h3>
            <table className="data-table" style={{ fontSize: 11 }}>
              <thead>
                <tr>
                  <th>Rolle</th>
                  <th>Provider / Model</th>
                  <th>Hauptaufgabe</th>
                </tr>
              </thead>
              <tbody>
                {ROLES.map((r) => (
                  <tr key={r.key} onClick={() => setSelectedRole(r.key)} style={{ cursor: "pointer" }}>
                    <td>
                      <span style={{ marginRight: 6 }}>{r.emoji}</span>
                      <strong>{r.name}</strong>
                    </td>
                    <td className="mono" style={{ fontSize: 10 }}>{r.provider}/{r.model}</td>
                    <td>{r.task}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      {/* === STANDARD-WORKFLOW === */}
      <div className="card mb-3">
        <div
          style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: openSection.workflow ? 12 : 0 }}
          onClick={() => toggle("workflow")}
        >
          {openSection.workflow ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <GitBranch size={16} color="var(--color-hermes-accent)" />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>2. Standard-Workflow (SOP "Standard-Workflow Task" v1)</h2>
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginLeft: 8 }}>{WORKFLOW_STEPS.length} Schritte</span>
        </div>

        {openSection.workflow && (
          <>
            <p style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", margin: "0 0 12px", lineHeight: 1.5 }}>
              <strong>6-Phasen-Flow:</strong> Triage → Todo → In Progress → Review → Rückfrage/Block → Done.
              <strong> 5s Delay pro Übergang</strong> (User-Transparenz). Jeder Schritt wird in der <code>task_transitions</code>-Tabelle protokolliert.
            </p>

            {/* Workflow-Visualisierung */}
            <div style={{ display: "flex", alignItems: "stretch", gap: 0, overflowX: "auto", padding: "8px 0" }}>
              {WORKFLOW_STEPS.map((s, idx) => {
                const isLast = idx === WORKFLOW_STEPS.length - 1
                const isSelected = openWorkflowStep === s.num
                const agentColor = s.agent === "CIO" ? "var(--color-hermes-accent-blue)"
                  : s.agent === "pi-coder" ? "var(--color-hermes-accent)"
                  : s.agent === "pi-tester" ? "var(--color-hermes-accent-orange)"
                  : "var(--color-hermes-text-secondary)"
                return (
                  <div key={s.num} style={{ display: "flex", alignItems: "center", flex: "0 0 auto" }}>
                    <div
                      onClick={() => setOpenWorkflowStep(isSelected ? null : s.num)}
                      style={{
                        background: "var(--color-hermes-surface)",
                        border: `2px solid ${isSelected ? "var(--color-hermes-accent)" : "var(--color-hermes-border)"}`,
                        borderRadius: 8,
                        padding: 10,
                        minWidth: 110,
                        cursor: "pointer",
                        textAlign: "center",
                        boxShadow: isSelected ? "0 0 12px rgba(46,160,67,0.3)" : "none",
                      }}
                    >
                      <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>
                        Schritt {s.num}
                      </div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: agentColor, marginBottom: 2 }}>
                        {s.to}
                      </div>
                      <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)" }}>
                        {s.agent}
                      </div>
                    </div>
                    {!isLast && (
                      <div style={{ width: 24, display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <div style={{ fontSize: 16, color: "var(--color-hermes-text-secondary)" }}>→</div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Detail-View des ausgewählten Schritts */}
            {openWorkflowStep !== null && WORKFLOW_STEPS[openWorkflowStep] && (() => {
              const s = WORKFLOW_STEPS[openWorkflowStep]
              return (
                <div style={{ marginTop: 12, padding: 12, background: "var(--color-hermes-muted)", borderRadius: 6, border: "1px solid var(--color-hermes-border)", borderLeft: "3px solid var(--color-hermes-accent)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <span className="badge badge-orange" style={{ fontSize: 10 }}>Schritt {s.num}</span>
                    <span className="mono" style={{ fontSize: 12 }}>{s.from} → <strong>{s.to}</strong></span>
                    <span className="badge badge-blue" style={{ fontSize: 10 }}>Agent: {s.agent}</span>
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 6 }}>{s.description}</div>
                  {s.details && (
                    <ul style={{ margin: 0, paddingLeft: 20, fontSize: 11, color: "var(--color-hermes-text-secondary)", lineHeight: 1.7 }}>
                      {s.details.map((d, i) => <li key={i}>{d}</li>)}
                    </ul>
                  )}
                </div>
              )
            })()}
          </>
        )}
      </div>

      {/* === CIO TRIAGE REVIEW (Schritt 0) === */}
      <div className="card mb-3">
        <div
          style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: openSection.triage ? 12 : 0 }}
          onClick={() => toggle("triage")}
        >
          {openSection.triage ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <ListChecks size={16} color="var(--color-hermes-accent-orange)" />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>3. CIO Triage Review (Schritt 0) — 4 Prüfungen</h2>
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginLeft: 8 }}>Pflicht vor Bearbeitung</span>
        </div>

        {openSection.triage && (
          <>
            <p style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", margin: "0 0 12px", lineHeight: 1.5 }}>
              Bevor ein Task das Board durchläuft, prüft CIO <strong>vier Pflicht-Punkte</strong>.
              Bei unvollständigen Angaben: <strong>BLOCK + Frage an User</strong>.
            </p>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
              {TRIAGE_CHECKS.map((c) => {
                const Icon = c.icon
                const isOpen = openTriageCheck === c.num
                return (
                  <div
                    key={c.num}
                    onClick={() => setOpenTriageCheck(isOpen ? null : c.num)}
                    style={{
                      background: "var(--color-hermes-surface)",
                      border: `1px solid var(--color-hermes-border)`,
                      borderLeft: `3px solid ${c.color}`,
                      borderRadius: 8,
                      padding: 12,
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                      <Icon size={14} color={c.color} />
                      <strong style={{ fontSize: 12 }}>Prüfung {c.num}</strong>
                      <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                        {isOpen ? "▼" : "▶"}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: "var(--color-hermes-text)", marginBottom: 6 }}>{c.title}</div>

                    {isOpen && (
                      <>
                        <div style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 8, marginBottom: 8 }}>
                          {c.fields.map((f) => (
                            <div key={f.key} style={{ fontSize: 10, padding: "3px 6px", background: "var(--color-hermes-muted)", borderRadius: 3, display: "flex", alignItems: "center", gap: 4 }}>
                              {f.required ? <AlertTriangle size={9} color="var(--color-hermes-danger)" /> : <span style={{ width: 9, height: 9 }} />}
                              <code style={{ fontSize: 10, color: "var(--color-hermes-accent-blue)" }}>{f.key}</code>
                              <span style={{ color: "var(--color-hermes-text-secondary)", marginLeft: 4 }}>{f.description}</span>
                            </div>
                          ))}
                        </div>
                        {c.example && (
                          <pre style={{ fontSize: 9, background: "var(--color-hermes-bg)", padding: 6, borderRadius: 3, margin: 0, fontFamily: "var(--font-mono)", color: "var(--color-hermes-accent)", overflow: "auto" }}>
                            {c.example}
                          </pre>
                        )}
                      </>
                    )}
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>

      {/* === ARCHITEKTUR-REGELN === */}
      <div className="card mb-3">
        <div
          style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: openSection.rules ? 12 : 0 }}
          onClick={() => toggle("rules")}
        >
          {openSection.rules ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <Shield size={16} color="var(--color-hermes-accent-orange)" />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>4. Architektur-Vorgaben ({ARCH_RULES.length} Regeln)</h2>
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginLeft: 8 }}>OpenBrain-Seed</span>
        </div>

        {openSection.rules && (
          <>
            <p style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", margin: "0 0 12px", lineHeight: 1.5 }}>
              Diese <strong>10 Standardvorgaben</strong> werden bei jedem Task im Schritt 0 gegen die Anforderung geprüft.
              <strong style={{ color: "var(--color-hermes-danger)" }}> Fehlt eine Vorgabe, MUSS sie in OpenBrain ergänzt werden</strong>.
            </p>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 8 }}>
              {ARCH_RULES.map((r) => (
                <div
                  key={r.key}
                  style={{
                    background: "var(--color-hermes-surface)",
                    border: "1px solid var(--color-hermes-border)",
                    borderLeft: `3px solid ${severityColor(r.severity)}`,
                    borderRadius: 6,
                    padding: 10,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                    <code style={{ fontSize: 10, color: "var(--color-hermes-accent-blue)" }}>{r.key}</code>
                    <span
                      className="badge"
                      style={{
                        fontSize: 9,
                        marginLeft: "auto",
                        background: severityColor(r.severity) + "33",
                        color: severityColor(r.severity),
                        border: `1px solid ${severityColor(r.severity)}`,
                      }}
                    >
                      {r.severity}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 2 }}>{r.name}</div>
                  <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{r.description}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* === GOVERNANCE === */}
      <div className="card mb-3">
        <div
          style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: openSection.governance ? 12 : 0 }}
          onClick={() => toggle("governance")}
        >
          {openSection.governance ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <Target size={16} color="var(--color-hermes-danger)" />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>5. Governance-Regeln</h2>
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginLeft: 8 }}>Pflicht für alle</span>
        </div>

        {openSection.governance && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {GOVERNANCE.map((g) => (
              <div
                key={g.num}
                style={{
                  background: "var(--color-hermes-surface)",
                  border: "1px solid var(--color-hermes-border)",
                  borderLeft: "3px solid var(--color-hermes-danger)",
                  borderRadius: 6,
                  padding: 10,
                  display: "grid",
                  gridTemplateColumns: "30px 1fr 1fr",
                  gap: 8,
                  alignItems: "center",
                }}
              >
                <span style={{ fontSize: 16, fontWeight: 700, color: "var(--color-hermes-danger)" }}>#{g.num}</span>
                <span style={{ fontSize: 12 }}>{g.rule}</span>
                <span style={{ fontSize: 11, color: "var(--color-hermes-accent-orange)", fontStyle: "italic" }}>
                  ⚠ {g.consequence}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* === BEST PRACTICES === */}
      <div className="card mb-3">
        <div
          style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: openSection.best ? 12 : 0 }}
          onClick={() => toggle("best")}
        >
          {openSection.best ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <Lightbulb size={16} color="var(--color-hermes-accent)" />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>6. DevOps Best Practices</h2>
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginLeft: 8 }}>{BEST_PRACTICES.length} Maßnahmen</span>
        </div>

        {openSection.best && (
          <>
            <p style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", margin: "0 0 12px", lineHeight: 1.5 }}>
              <strong>Goldene Regel:</strong> Kürzester Feedback-Loop = Schnellster Bug-Fix.
              <strong> Trace-ID ist das Rückgrat</strong> — ohne sie kein Cross-Service-Debugging.
            </p>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 8 }}>
              {BEST_PRACTICES.map((bp) => (
                <div
                  key={bp.num}
                  style={{
                    background: "var(--color-hermes-surface)",
                    border: "1px solid var(--color-hermes-border)",
                    borderLeft: `3px solid ${phaseColor(bp.phase)}`,
                    borderRadius: 6,
                    padding: 10,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                    <span className="badge" style={{ fontSize: 9, background: phaseColor(bp.phase) + "33", color: phaseColor(bp.phase), border: `1px solid ${phaseColor(bp.phase)}` }}>
                      {phaseLabel(bp.phase)}
                    </span>
                    <span className="badge badge-gray" style={{ fontSize: 9 }}>{bp.effort}</span>
                    <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>#{bp.num}</span>
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 4 }}>{bp.title}</div>
                  <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>→ {bp.effect}</div>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 12, padding: 10, background: "var(--color-hermes-muted)", borderRadius: 6, fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
              <strong style={{ color: "var(--color-hermes-accent)" }}>📚 Quellen:</strong> Google SRE Book, OpenTelemetry Docs, GitLab/Google DevOps State Reports 2024-2025
            </div>
          </>
        )}
      </div>

      {/* === CHEAT-SHEET === */}
      <div className="card">
        <div
          style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: openSection.cheat ? 12 : 0 }}
          onClick={() => toggle("cheat")}
        >
          {openSection.cheat ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <CheckCircle2 size={16} color="var(--color-hermes-accent)" />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>7. Cheat-Sheet — Wer macht was?</h2>
        </div>

        {openSection.cheat && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, lineHeight: 1.7, background: "var(--color-hermes-bg)", padding: 12, borderRadius: 6, color: "var(--color-hermes-text)" }}>
            <div><span style={{ color: "var(--color-hermes-text-secondary)" }}># Was willst du?</span></div>
            <div style={{ paddingLeft: 16 }}>
              <div>├── Neue Funktion bauen → Task "NEW: ..." → CEO-digital → CIO-Triage → <span style={{ color: "var(--color-hermes-accent)" }}>pi-coder</span></div>
              <div>├── Bug fixen → Task "BUGFIX: ..." → CEO-digital → CIO-Triage → <span style={{ color: "var(--color-hermes-accent)" }}>pi-fixer</span></div>
              <div>├── Etwas funktioniert nicht (User) → Task "TICKET: ..." → CEO-digital → CIO-Triage → pi-tester (diagnose) → pi-fixer (fix)</div>
              <div>└── Etwas ändern → Task "CHANGE: ..." → CEO-digital → CIO-Triage → pi-coder</div>
            </div>

            <div style={{ marginTop: 12 }}><span style={{ color: "var(--color-hermes-text-secondary)" }}># Was prüft wer?</span></div>
            <div style={{ paddingLeft: 16 }}>
              <div>├── Vor der Bearbeitung: <span style={{ color: "var(--color-hermes-accent-blue)" }}>CIO</span> (Schritt 0: 4 Prüfungen)</div>
              <div>├── Während der Bearbeitung: pi-coder (-tester, -reviewer) implementiert</div>
              <div>├── Nach der Bearbeitung: <span style={{ color: "var(--color-hermes-accent-orange)" }}>pi-tester</span> (Code-Review + Tests)</div>
              <div>└── Vor dem Done: <span style={{ color: "var(--color-hermes-accent-blue)" }}>CIO</span> (Final-Review gegen Standards)</div>
            </div>

            <div style={{ marginTop: 12 }}><span style={{ color: "var(--color-hermes-text-secondary)" }}># Was passiert bei Fehlern?</span></div>
            <div style={{ paddingLeft: 16 }}>
              <div>├── Tester findet Bug → zurück zu pi-coder (Iteration++)</div>
              <div>├── CIO findet Standard-Verstoß → zurück zu pi-coder (CIO-Reject)</div>
              <div>└── User meldet Bug → neuer TICKET-Task → kompletter Loop</div>
            </div>

            <div style={{ marginTop: 12 }}><span style={{ color: "var(--color-hermes-text-secondary)" }}># Was passiert bei Prozess-Verstoß?</span></div>
            <div style={{ paddingLeft: 16, color: "var(--color-hermes-danger)" }}>
              <div>└── JEDER Verstoß → SOFORT Complaint-Task im cio-board</div>
            </div>
          </div>
        )}
      </div>

      {/* === Footer === */}
      <div style={{ marginTop: 16, textAlign: "center", fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
        Quelle: OpenBrain bB (16.06.2026) · <code>docs/RACI-WORKFLOW.md</code> · Verantwortlich: Owner Andy Amann (Strategie) · CEO-digital (Orchestrierung) · CIO (Umsetzung)
      </div>
    </div>
  )
}

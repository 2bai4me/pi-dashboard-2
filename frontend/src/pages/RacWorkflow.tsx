// RacWorkflow.tsx — Standardvorgaben, Governance und DevOps Best Practices
//
// User-Direktive 22.06.2026: Inhalt reduziert.
// - 1. Hierarchie & Rollen  → entfernt (lebt jetzt in SubAgenten-Konfiguration)
// - 2. Standard-Workflow SOP → entfernt (lebt jetzt in SOP "Standard-Workflow Task")
// - 3. CIO Triage 4-Pruefungen → entfernt (wird nicht mehr so dokumentiert)
// Verbleibend: Architektur-Vorgaben, Governance, DevOps Best Practices, Cheat-Sheet.
import { useState } from "react"
import {
  ChevronRight, ChevronDown, Shield, AlertTriangle, CheckCircle2,
  FileCode2, Target, Lightbulb,
} from "lucide-react"

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

const GOVERNANCE: GovernanceRule[] = [
  { num: 1, rule: "CEO(digital) entwickelt NIE selbst Code — NUR Orchestrierung",   consequence: "SOFORT Complaint-Task + Fix-Task im cio-board" },
  { num: 2, rule: "Alle Entwicklung läuft über KANBAN → CIO → PI-Agenten",           consequence: "Task wird zurück in Triage geschoben" },
  { num: 3, rule: "JEDER KANBAN-Task MUSS Präfix 'BUGFIX:' oder 'NEW:' im Titel haben", consequence: "Task wird abgelehnt" },
  { num: 4, rule: "Bei Prozessverstoß (Direktentwicklung): Sofort eskalieren",        consequence: "Keine Ausnahme — auch nicht bei Dringlichkeit" },
  { num: 5, rule: "RACI-Prinzip: Genau 1 Verantwortlicher pro Task",                  consequence: "Klärungs-Aktion, bis Eindeutigkeit herrscht" },
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
  const [openSection, setOpenSection] = useState<Record<string, boolean>>({
    rules: true, governance: true, best: true, cheat: false,
  })

  function toggle(s: string) {
    setOpenSection((prev) => ({ ...prev, [s]: !prev[s] }))
  }

  return (
    <div>
      {/* === Header === */}
      <div className="page-header">
        <div className="workspace-header">
          <FileCode2 size={22} color="var(--color-hermes-accent-blue)" />
          <h1>Config</h1>
        </div>
        <p>
          Standardvorgaben, Governance und DevOps Best Practices.
          Hierarchie und Rollen leben in <strong style={{ color: "var(--color-hermes-accent-blue)" }}>SubAgenten</strong>,
          der Standard-Workflow in den <strong style={{ color: "var(--color-hermes-accent-blue)" }}>SOPs</strong>.
        </p>
      </div>

      {/* === 1. ARCHITEKTUR-VORGABEN === */}
      <div className="card mb-3">
        <div
          style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: openSection.rules ? 12 : 0 }}
          onClick={() => toggle("rules")}
        >
          {openSection.rules ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <Shield size={16} color="var(--color-hermes-accent-orange)" />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>1. Architektur-Vorgaben ({ARCH_RULES.length} Regeln)</h2>
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginLeft: 8 }}>Aktiv im Code: SOP-Engine check_architecture</span>
        </div>

        {openSection.rules && (
          <>
            <p style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", margin: "0 0 12px", lineHeight: 1.5 }}>
              Diese <strong>10 Standardvorgaben</strong> werden bei jedem Task im Schritt 0 gegen die Anforderung geprüft
              (<code>backend/app/services/sop_engine.py → check_architecture</code>).
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

      {/* === 2. GOVERNANCE === */}
      <div className="card mb-3">
        <div
          style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: openSection.governance ? 12 : 0 }}
          onClick={() => toggle("governance")}
        >
          {openSection.governance ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <Target size={16} color="var(--color-hermes-danger)" />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>2. Governance-Regeln</h2>
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

      {/* === 3. BEST PRACTICES === */}
      <div className="card mb-3">
        <div
          style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: openSection.best ? 12 : 0 }}
          onClick={() => toggle("best")}
        >
          {openSection.best ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <Lightbulb size={16} color="var(--color-hermes-accent)" />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>3. DevOps Best Practices</h2>
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

      {/* === 4. CHEAT-SHEET === */}
      <div className="card">
        <div
          style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: openSection.cheat ? 12 : 0 }}
          onClick={() => toggle("cheat")}
        >
          {openSection.cheat ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <CheckCircle2 size={16} color="var(--color-hermes-accent)" />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>4. Cheat-Sheet — Wer macht was?</h2>
        </div>

        {openSection.cheat && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, lineHeight: 1.7, background: "var(--color-hermes-bg)", padding: 12, borderRadius: 6, color: "var(--color-hermes-text)" }}>
            <div><span style={{ color: "var(--color-hermes-text-secondary)" }}># Was willst du?</span></div>
            <div style={{ paddingLeft: 16 }}>
              <div>├── Neue Funktion bauen → Task "NEW: ..." → CEO-digital → <span style={{ color: "var(--color-hermes-accent-blue)" }}>CIO-Triage</span> → <span style={{ color: "var(--color-hermes-accent)" }}>pi-coder</span></div>
              <div>├── Bug fixen → Task "BUGFIX: ..." → CEO-digital → CIO-Triage → <span style={{ color: "var(--color-hermes-accent)" }}>pi-fixer</span></div>
              <div>├── Etwas funktioniert nicht (User) → Task "TICKET: ..." → CEO-digital → CIO-Triage → pi-tester (diagnose) → pi-fixer (fix)</div>
              <div>└── Etwas ändern → Task "CHANGE: ..." → CEO-digital → CIO-Triage → pi-coder</div>
            </div>

            <div style={{ marginTop: 12 }}><span style={{ color: "var(--color-hermes-text-secondary)" }}># Was prüft wer?</span></div>
            <div style={{ paddingLeft: 16 }}>
              <div>├── Vor der Bearbeitung: <span style={{ color: "var(--color-hermes-accent-blue)" }}>CIO</span> (Triage + Architektur-Check)</div>
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
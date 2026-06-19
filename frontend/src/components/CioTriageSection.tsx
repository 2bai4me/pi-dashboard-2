// CioTriageSection — Schritt 0 des Standard-Workflows (User-Direktive 16.06.2026)
// Im SOP-Schritt "CIO Triage Review" muss der CIO 4 Pruefungen vornehmen:
//   1. Task-Typ klassifizieren (new_request | change | ticket | bugfix)
//   2. Standardvorgaben-Konformitaet pruefen (OpenBrain-Vorgaben)
//   3. Aenderungsbeschreibung detaillieren (was, wo, wie)
//   4. Subagent-Readiness bewerten (was braucht der Subagent?)
import { useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "../api"
import { CheckCircle2, AlertCircle, ListChecks, FileText, Shield, Bot, ChevronDown, ChevronRight } from "lucide-react"

const TASK_TYPES = [
  { key: "new_request", label: "Neu (new_request)", color: "var(--color-hermes-accent)", desc: "Komplett neue Anforderung" },
  { key: "change",      label: "Change Request",    color: "var(--color-hermes-accent-blue)", desc: "Aenderung an Bestehendem" },
  { key: "ticket",      label: "Ticket",            color: "var(--color-hermes-accent-orange)", desc: "User meldet was nicht funktioniert" },
  { key: "bugfix",      label: "Bugfix",            color: "var(--color-hermes-danger)", desc: "Von Agenten gefunden" },
] as const

export function CioTriageSection({ taskId, task, onUpdate }: { taskId: string; task: any; onUpdate?: () => void }) {
  const qc = useQueryClient()
  // User-Direktive 17.06.2026: CR-Felder default ZUGEKLAPPT (User klappt nur bei Bedarf auf)
  const [open, setOpen] = useState(false)

  // Standardvorgaben laden
  const { data: rulesData } = useQuery({
    queryKey: ["architecture-rules"],
    queryFn: () => api.listRules(),
  })
  const rules: any[] = (rulesData as any)?.items || []

  // Aktuelle Werte
  const currentType = task.task_type || ""
  const currentPlan = task.implementation_plan || {}
  const currentStandards = task.standards_check || {}
  const currentReadiness = task.subagent_readiness || {}

  // === Mutations ===
  const setTaskTypeMut = useMutation({
    mutationFn: (t: string) => api.setTaskType(taskId, t),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task", taskId] })
      qc.invalidateQueries({ queryKey: ["tasks"] })
      onUpdate?.()
    },
  })
  const setPlanMut = useMutation({
    mutationFn: (plan: any) => api.setImplementationPlan(taskId, plan),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task", taskId] })
      onUpdate?.()
    },
  })
  const setStandardsMut = useMutation({
    mutationFn: (s: any) => api.setStandardsCheck(taskId, s),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task", taskId] })
      onUpdate?.()
    },
  })
  const setReadinessMut = useMutation({
    mutationFn: (r: any) => api.setSubagentReadiness(taskId, r),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task", taskId] })
      onUpdate?.()
    },
  })

  // === Hilfsfunktion: Standards-Check-Toggle ===
  function toggleStandardMatch(ruleId: string) {
    const matches: string[] = currentStandards.matches || []
    const missing: string[] = currentStandards.missing || []
    let newMatches, newMissing
    if (matches.includes(ruleId)) {
      newMatches = matches.filter((x: string) => x !== ruleId)
      newMissing = [...missing, ruleId]
    } else if (missing.includes(ruleId)) {
      newMissing = missing.filter((x: string) => x !== ruleId)
    } else {
      newMatches = [...matches, ruleId]
    }
    setStandardsMut.mutate({
      ...currentStandards,
      matches: newMatches,
      missing: newMissing,
      checked_at: new Date().toISOString(),
    })
  }

  // === Helper: Zaehlen, wie viele Pruefungen abgeschlossen sind ===
  const checks = [
    { label: "Task-Typ", done: !!currentType },
    { label: "Standards", done: (currentStandards.matches?.length || 0) > 0 || (currentStandards.missing?.length || 0) > 0 },
    { label: "Aenderungs-Plan", done: !!currentPlan.notes && (!!currentPlan.files || !!currentPlan.routes || !!currentPlan.api_changes) },
    { label: "Subagent-Readiness", done: !!currentReadiness.model && !!currentReadiness.branch },
  ]
  const doneCount = checks.filter((c) => c.done).length
  const allDone = doneCount === 4

  return (
    <div
      style={{
        borderLeft: `3px solid ${allDone ? "var(--color-hermes-accent)" : "var(--color-hermes-accent-orange)"}`,
        background: "var(--color-hermes-bg-secondary)",
        borderRadius: 6,
        padding: 12,
        marginBottom: 10,
        fontSize: 12,
      }}
    >
      {/* Header */}
      <div
        onClick={() => setOpen(!open)}
        style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: open ? 10 : 0 }}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Shield size={14} color={allDone ? "var(--color-hermes-accent)" : "var(--color-hermes-accent-orange)"} />
        <strong style={{ fontSize: 13 }}>CIO Triage Review (Schritt 0)</strong>
        <span style={{
          fontSize: 10, padding: "2px 6px", borderRadius: 8,
          background: allDone ? "var(--color-hermes-accent)" : "var(--color-hermes-accent-orange)",
          color: "#000", fontWeight: 600,
        }}>
          {doneCount}/4
        </span>
        {allDone && <CheckCircle2 size={12} color="var(--color-hermes-accent)" />}
        <div style={{ flex: 1 }} />
        {allDone ? (
          <span style={{ fontSize: 10, color: "var(--color-hermes-accent)" }}>✓ Alle Pruefungen abgeschlossen</span>
        ) : (
          <span style={{ fontSize: 10, color: "var(--color-hermes-accent-orange)" }}>⚠ Pruefungen ausstehend</span>
        )}
      </div>

      {open && (
        <>
          {/* === 1. Task-Typ === */}
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 6, fontWeight: 600 }}>
              1. TASK-TYP KLASSIFIZIEREN
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {TASK_TYPES.map((t) => {
                const active = currentType === t.key
                return (
                  <button
                    key={t.key}
                    className={`btn btn-sm ${active ? "btn-primary" : ""}`}
                    onClick={() => setTaskTypeMut.mutate(t.key)}
                    disabled={setTaskTypeMut.isPending}
                    title={t.desc}
                    style={active ? { background: t.color, borderColor: t.color, color: "#fff" } : {}}
                  >
                    {t.label}
                  </button>
                )
              })}
            </div>
            {currentType && (
              <div style={{ marginTop: 4, fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                → Klassifiziert als: <strong>{TASK_TYPES.find((t) => t.key === currentType)?.label}</strong>
              </div>
            )}
          </div>

          {/* === 2. Standardvorgaben-Konformitaet === */}
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 6, fontWeight: 600 }}>
              2. STANDARDVORGABEN-KONFORMITÄT PRÜFEN ({rules.length} Regeln)
            </div>
            <div style={{ maxHeight: 200, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
              {rules.map((r: any) => {
                const matches = (currentStandards.matches || []).includes(r.id)
                const missing = (currentStandards.missing || []).includes(r.id)
                return (
                  <div
                    key={r.id}
                    style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "5px 8px",
                      background: matches ? "rgba(46, 160, 67, 0.1)" : missing ? "rgba(210, 153, 34, 0.1)" : "var(--color-hermes-surface)",
                      border: `1px solid ${matches ? "var(--color-hermes-accent)" : missing ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-border)"}`,
                      borderRadius: 4,
                      fontSize: 11,
                    }}
                  >
                    <span style={{ fontSize: 10, color: r.severity === "must" ? "var(--color-hermes-danger)" : "var(--color-hermes-text-secondary)", fontWeight: 600 }}>
                      [{r.severity}]
                    </span>
                    <span style={{ flex: 1 }}>
                      <strong>{r.name}</strong>
                      {r.description && (
                        <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{r.description.slice(0, 80)}</div>
                      )}
                    </span>
                    <button
                      className={`btn btn-sm ${matches ? "btn-primary" : ""}`}
                      onClick={() => toggleStandardMatch(r.id)}
                      style={{ fontSize: 9, padding: "2px 6px", minWidth: 30 }}
                      title="Konform"
                    >
                      ✓
                    </button>
                    <button
                      className={`btn btn-sm ${missing ? "btn-danger" : ""}`}
                      onClick={() => {
                        if (!missing) {
                          const matchesArr = (currentStandards.matches || []).filter((x: string) => x !== r.id)
                          const missingArr = [...(currentStandards.missing || []), r.id]
                          setStandardsMut.mutate({ ...currentStandards, matches: matchesArr, missing: missingArr, checked_at: new Date().toISOString() })
                        } else {
                          const missingArr = (currentStandards.missing || []).filter((x: string) => x !== r.id)
                          setStandardsMut.mutate({ ...currentStandards, missing: missingArr, checked_at: new Date().toISOString() })
                        }
                      }}
                      style={{ fontSize: 9, padding: "2px 6px", minWidth: 30 }}
                      title="Fehlt / Verletzt"
                    >
                      ✗
                    </button>
                  </div>
                )
              })}
            </div>
            <div style={{ marginTop: 4, fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
              ✓ = {(currentStandards.matches || []).length} konform · ✗ = {(currentStandards.missing || []).length} fehlt
            </div>
          </div>

          {/* === 3. Aenderungsbeschreibung === */}
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 6, fontWeight: 600 }}>
              3. ÄNDERUNGSBESCHREIBUNG (so detailliert wie möglich)
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div>
                <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>Dateien (kommasepariert)</div>
                <input
                  className="input"
                  placeholder="frontend/src/..., backend/app/..."
                  defaultValue={(currentPlan.files || []).join(", ")}
                  onBlur={(e) => {
                    const files = e.target.value.split(",").map((s) => s.trim()).filter(Boolean)
                    if (JSON.stringify(files) !== JSON.stringify(currentPlan.files || [])) {
                      setPlanMut.mutate({ ...currentPlan, files })
                    }
                  }}
                  style={{ fontSize: 11 }}
                />
              </div>
              <div>
                <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>API-Änderungen (kommasepariert)</div>
                <input
                  className="input"
                  placeholder="POST /api/..., GET /api/..."
                  defaultValue={(currentPlan.api_changes || []).join(", ")}
                  onBlur={(e) => {
                    const api_changes = e.target.value.split(",").map((s) => s.trim()).filter(Boolean)
                    if (JSON.stringify(api_changes) !== JSON.stringify(currentPlan.api_changes || [])) {
                      setPlanMut.mutate({ ...currentPlan, api_changes })
                    }
                  }}
                  style={{ fontSize: 11 }}
                />
              </div>
              <div>
                <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>Notizen (Pflicht)</div>
                <textarea
                  className="input"
                  placeholder="Was soll wo und wie geaendert werden? (moeglichst detailliert)"
                  defaultValue={currentPlan.notes || ""}
                  onBlur={(e) => {
                    if (e.target.value !== (currentPlan.notes || "")) {
                      setPlanMut.mutate({ ...currentPlan, notes: e.target.value })
                    }
                  }}
                  style={{ minHeight: 60, fontSize: 11 }}
                />
              </div>
            </div>
          </div>

          {/* === 4. Subagent-Readiness === */}
          <div style={{ marginBottom: 4 }}>
            <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 6, fontWeight: 600 }}>
              4. SUBAGENT-READINESS (Swarm-Anforderungen)
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
              <div>
                <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>LLM-Model *</div>
                <input
                  className="input"
                  placeholder="minimax/minimax-m3"
                  defaultValue={currentReadiness.model || ""}
                  onBlur={(e) => {
                    if (e.target.value !== (currentReadiness.model || "")) {
                      setReadinessMut.mutate({ ...currentReadiness, model: e.target.value })
                    }
                  }}
                  style={{ fontSize: 11 }}
                />
              </div>
              <div>
                <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>Git-Branch *</div>
                <input
                  className="input"
                  placeholder={`task/${taskId.slice(0, 8)}`}
                  defaultValue={currentReadiness.branch || ""}
                  onBlur={(e) => {
                    if (e.target.value !== (currentReadiness.branch || "")) {
                      setReadinessMut.mutate({ ...currentReadiness, branch: e.target.value })
                    }
                  }}
                  style={{ fontSize: 11 }}
                />
              </div>
              <div>
                <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>Token-Budget (optional)</div>
                <input
                  className="input"
                  type="number"
                  placeholder="15000"
                  defaultValue={currentReadiness.token_budget || ""}
                  onBlur={(e) => {
                    const v = e.target.value ? Number(e.target.value) : undefined
                    if (v !== currentReadiness.token_budget) {
                      setReadinessMut.mutate({ ...currentReadiness, token_budget: v })
                    }
                  }}
                  style={{ fontSize: 11 }}
                />
              </div>
              <div>
                <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>Cost-Limit USD (optional)</div>
                <input
                  className="input"
                  type="number"
                  step={0.01}
                  placeholder="0.05"
                  defaultValue={currentReadiness.cost_limit_usd || ""}
                  onBlur={(e) => {
                    const v = e.target.value ? Number(e.target.value) : undefined
                    if (v !== currentReadiness.cost_limit_usd) {
                      setReadinessMut.mutate({ ...currentReadiness, cost_limit_usd: v })
                    }
                  }}
                  style={{ fontSize: 11 }}
                />
              </div>
            </div>
            <div style={{ marginTop: 6, fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
              <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={!!currentReadiness.ready}
                  onChange={(e) => setReadinessMut.mutate({ ...currentReadiness, ready: e.target.checked })}
                />
                Subagent kann sofort starten (alle Pflicht-Infos vorhanden)
              </label>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

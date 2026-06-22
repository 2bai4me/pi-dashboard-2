import { useState, useEffect, useMemo, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import ReactMarkdown from "react-markdown"
import {
  BookOpen, Plus, Trash2, Eye, GitBranch, Workflow,
  FileCode2, ImageIcon, ListTree, Settings2, ChevronRight, X, ArrowLeft,
  ZoomIn, ZoomOut, Maximize2, Download, Volume2, VolumeX, Edit3, PlusCircle,
} from "lucide-react"
import BpmnViewer from "bpmn-js/lib/Viewer"
import NavigatedViewer from "bpmn-js/lib/NavigatedViewer"
import BpmnModeler from "bpmn-js/lib/Modeler"
import { DiagramProvider, SequenceDiagram } from "beautiful-plantuml"
import { api } from "../api"
import { SpeakButton } from "../components/SpeakButton"
import { AgentModelDisplay, AgentOption } from "../components/AgentModelDisplay"
import { useTTSContext } from "../TTSContext"
import { SopStepToolSelector } from "../components/SopStepToolSelector"
import "bpmn-js/dist/assets/diagram-js.css"
import "bpmn-js/dist/assets/bpmn-js.css"
import "bpmn-js/dist/assets/bpmn-font/css/bpmn-embedded.css"

// ─────────────── Dynamische Agent-Auswahl aus SubAgent-Konfigurationen ───────────────
function AgentSelect({
  value,
  onChange,
  style,
}: {
  value: string
  onChange: (agent: string) => void
  style?: React.CSSProperties
}) {
  const { data } = useQuery({
    queryKey: ["subagent-configs"],
    queryFn: () => api.subagents.listConfigs(),
    staleTime: 60_000,
  })
  const configs: AgentOption[] = (data as any) || []
  // User-Direktive 22.06.2026: Agenten alphabetisch sortieren fuer bessere UX
  // localeCompare() beachtet Umlaute und Locale-Einstellungen korrekt.
  const sortedConfigs = useMemo(
    () => [...configs].sort((a, b) => a.name.localeCompare(b.name, "de")),
    [configs]
  )
  // Immer bekannte System-Optionen anbieten, auch wenn Configs noch laden
  const systemOptions = ["system", "user"]
  const unknownButSelected = value && !configs.some((c) => c.name === value) && !systemOptions.includes(value)

  return (
    <select
      className="select"
      value={value || ""}
      onChange={(e) => onChange(e.target.value)}
      style={style}
    >
      {sortedConfigs.map((c) => (
        <option key={c.name} value={c.name}>
          {c.emoji || "🤖"} {c.name} {c.is_subagent ? "(Sub-Agent)" : "(Org)"}
        </option>
      ))}
      {systemOptions.map((s) => (
        <option key={s} value={s}>{s}</option>
      ))}
      {unknownButSelected && <option value={value}>{value} (unbekannt)</option>}
    </select>
  )
}

// ─────────────── Modell-Anzeige: read-only, wird aus SubAgent-Konfiguration gezogen ───────────────
// (extrahiert nach src/components/AgentModelDisplay.tsx fuer Testbarkeit)
// User-Direktive 22.06.2026: Im SOP-Step-Editor wird das Modell NICHT mehr ausgewaehlt,
// sondern aus der gewaehlten SubAgent-Konfiguration uebernommen und nur angezeigt.
// Aenderung des Modells erfolgt ausschliesslich in der SubAgent-Ansicht.

// Markdown-Styles fuer KI-Support-Designer Vorschau
const mdComponents = {
  h1: ({ children }: any) => <h1 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 8px", color: "var(--color-hermes-accent-blue)" }}>{children}</h1>,
  h2: ({ children }: any) => <h2 style={{ fontSize: 14, fontWeight: 700, margin: "10px 0 6px", color: "var(--color-hermes-accent)" }}>{children}</h2>,
  h3: ({ children }: any) => <h3 style={{ fontSize: 13, fontWeight: 600, margin: "8px 0 4px" }}>{children}</h3>,
  p: ({ children }: any) => <p style={{ margin: "0 0 6px" }}>{children}</p>,
  ul: ({ children }: any) => <ul style={{ margin: "0 0 6px", paddingLeft: 20 }}>{children}</ul>,
  ol: ({ children }: any) => <ol style={{ margin: "0 0 6px", paddingLeft: 20 }}>{children}</ol>,
  li: ({ children }: any) => <li style={{ marginBottom: 2 }}>{children}</li>,
  code: ({ children }: any) => <code style={{ background: "var(--color-hermes-bg-secondary)", padding: "1px 4px", borderRadius: 3, fontSize: 11, fontFamily: "var(--font-mono)" }}>{children}</code>,
  strong: ({ children }: any) => <strong style={{ color: "var(--color-hermes-text)", fontWeight: 600 }}>{children}</strong>,
}

type View = "list" | "detail" | "builder" | "instances" | "bpmn" | "uml"

export default function Sops() {
  const qc = useQueryClient()
  const [view, setView] = useState<View>("list")
  const [selectedSopId, setSelectedSopId] = useState<string | null>(null)
  const [showSeedResult, setShowSeedResult] = useState<string | null>(null)

  // === Queries ===
  const { data: sopsData, isLoading: sopsLoading } = useQuery({
    queryKey: ["sops"],
    queryFn: () => api.listSops(),
  })
  const sops: any[] = (sopsData as any)?.items || []

  // === Seed defaults ===
  const seedMut = useMutation({
    mutationFn: () => api.seedDefaultSops(),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ["sops"] })
      setShowSeedResult(`${data.seeded} SOP(s) geseedet`)
      setTimeout(() => setShowSeedResult(null), 3000)
    },
  })

  // === List-View: Kachel-View mit allen SOPs (analog zu ProjectList) ===
  if (view === "list") {
    return (
      <SopListView
        sops={sops}
        loading={sopsLoading}
        seedPending={seedMut.isPending}
        seedResult={showSeedResult}
        onSelect={(id: string) => { setSelectedSopId(id); setView("detail") }}
        onNew={() => setView("builder")}
        onSeed={() => seedMut.mutate()}
      />
    )
  }

  // === Builder (SOP erstellen) ===
  if (view === "builder") {
    return (
      <SopBuilder
        onCancel={() => setView("list")}
        onCreated={(sop: any) => {
          qc.invalidateQueries({ queryKey: ["sops"] })
          setSelectedSopId(sop.id)
          setView("detail")
        }}
      />
    )
  }

  // === Detail-Workspace: Tabs (Detail / Instances / BPMN / UML) ===
  if (selectedSopId) {
    return (
      <SopWorkspace
        sopId={selectedSopId}
        view={view}
        onTabChange={setView}
        onBack={() => { setSelectedSopId(null); setView("list") }}
        onDeleted={() => {
          qc.invalidateQueries({ queryKey: ["sops"] })
          setSelectedSopId(null)
          setView("list")
        }}
      />
    )
  }

  return null
}

// ─────────────── SOP-Liste (Kachel-View, analog zu ProjectList) ───────────────
function SopListView({
  sops, loading, seedPending, seedResult, onSelect, onNew, onSeed,
}: {
  sops: any[]
  loading: boolean
  seedPending: boolean
  seedResult: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onSeed: () => void
}) {
  if (loading) {
    return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Lade SOPs…</div>
  }
  return (
    <div>
      <div className="page-header">
        <div className="workspace-header">
          <BookOpen size={20} color="var(--color-hermes-accent-blue)" />
          <h1>SOP</h1>
        </div>
        <p>Standard Operating Procedures — wiederverwendbare Regelprozesse (Klick auf Kachel öffnet Detail-Workspace).</p>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <button className="btn btn-primary" onClick={onNew}>
          <Plus size={14} /> Neue SOP
        </button>
        <button className="btn" onClick={onSeed} disabled={seedPending}>
          <Settings2 size={14} /> {seedPending ? "Seedet…" : "Default-SOP seeden"}
        </button>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
          {sops.length} SOP{sops.length !== 1 ? "s" : ""} vorhanden
        </span>
      </div>

      {seedResult && (
        <div className="card" style={{ borderLeft: "3px solid var(--color-hermes-accent)", marginBottom: 12, fontSize: 12 }}>
          ✅ {seedResult}
        </div>
      )}

      {sops.length === 0 ? (
        <div className="card" style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
          <BookOpen size={32} style={{ marginBottom: 8 }} />
          <p>Noch keine SOPs vorhanden.</p>
          <p style={{ fontSize: 12 }}>
            Klicke <strong>+ Neue SOP</strong> zum Erstellen oder <strong>Default-SOP seeden</strong> für den Standard-Workflow.
          </p>
        </div>
      ) : (
        <div className="card-grid">
          {sops.map((s: any) => (
            <SopListCard key={s.id} sop={s} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  )
}

// ─────────────── SOP-List-Card mit ID-Display (User-Direktive 17.06.2026) ───────────────
function SopListCard({ sop, onSelect }: { sop: any; onSelect: (id: string) => void }) {
  const [copied, setCopied] = useState(false)
  function copyId(e: React.MouseEvent) {
    e.stopPropagation()
    navigator.clipboard.writeText(sop.id)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }
  return (
    <div
      className="project-card"
      onClick={() => onSelect(sop.id)}
      style={{
        borderLeftColor: sop.is_template
          ? "var(--color-hermes-accent-orange)"
          : sop.category === "review"
          ? "var(--color-hermes-accent-blue)"
          : sop.category === "release"
          ? "var(--color-hermes-accent)"
          : "var(--color-hermes-accent-blue)"
      }}
    >
      <div className="project-card-name">{sop.name}</div>
      <div className="project-card-desc">
        {sop.description ? sop.description.slice(0, 140) + "…" : "(keine Beschreibung)"}
      </div>
      <div className="project-card-meta">
        <span className="badge badge-gray">{sop.category}</span>
        <span>· v{sop.version}</span>
        <span>· {sop.step_count} Steps</span>
        <span>· ⏱ {sop.default_delay_s}s</span>
      </div>
      <div className="project-card-meta" style={{ marginTop: 6, fontSize: 10 }}>
        <span
          className={`id-badge id-badge-board ${copied ? "id-badge-copied" : ""}`}
          onClick={copyId}
          title={copied ? "Kopiert!" : `SOP-ID: ${sop.id} — Klick zum Kopieren`}
          style={{ fontSize: 9, padding: "1px 4px" }}
        >
          {copied ? "✓ Kopiert" : `ID: ${sop.id.slice(0, 12)}…`}
        </span>
        <span style={{ marginLeft: 6, color: "var(--color-hermes-text-secondary)" }}>
          Created: {sop.created_at ? new Date(sop.created_at).toLocaleDateString("de-DE") : "—"}
        </span>
      </div>
    </div>
  )
}

// ─────────────── SOP-Workspace (Detail mit Tabs) ───────────────
function SopWorkspace({
  sopId, view, onTabChange, onBack, onDeleted,
}: {
  sopId: string
  view: View
  onTabChange: (v: View) => void
  onBack: () => void
  onDeleted: () => void
}) {
  const qc = useQueryClient()
  const { data: sop, isLoading } = useQuery({
    queryKey: ["sop", sopId],
    queryFn: () => api.getSop(sopId),
  })
  // === Edit-Name-State (User-Direktive 17.06.2026) ===
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState("")
  const [copiedId, setCopiedId] = useState(false)

  const renameMut = useMutation({
    mutationFn: (newName: string) => api.updateSop(sopId, { name: newName }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sop", sopId] })
      qc.invalidateQueries({ queryKey: ["sops"] })
      setEditingName(false)
    },
  })

  function startRename() {
    if (!sop) return
    setNameDraft(sop.name || "")
    setEditingName(true)
  }
  function saveRename() {
    const trimmed = nameDraft.trim()
    if (!trimmed) return
    if (trimmed === sop?.name) {
      setEditingName(false)
      return
    }
    renameMut.mutate(trimmed)
  }
  function copySopId() {
    navigator.clipboard.writeText(sopId)
    setCopiedId(true)
    setTimeout(() => setCopiedId(false), 1200)
  }
  const delMut = useMutation({
    mutationFn: () => api.deleteSop(sopId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sops"] })
      onDeleted()
    },
  })

  if (isLoading || !sop) {
    return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Lade SOP…</div>
  }

  return (
    <div>
      <div className="page-header">
        <div className="workspace-header">
          <button className="btn btn-sm" onClick={onBack} style={{ padding: "0 6px" }} title="Zurück zur SOP-Liste">
            <ArrowLeft size={14} />
          </button>
          <BookOpen size={20} color="var(--color-hermes-accent-blue)" />
          <h1>SOP</h1>
          {editingName ? (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <span className="workspace-breadcrumb" style={{ color: "var(--color-hermes-text-secondary)" }}>/</span>
              <input
                autoFocus
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") saveRename()
                  if (e.key === "Escape") setEditingName(false)
                }}
                style={{
                  fontSize: 14, padding: "2px 6px", minWidth: 200,
                  background: "var(--color-hermes-muted)",
                  color: "var(--color-hermes-text)",
                  border: "1px solid var(--color-hermes-accent-blue)",
                  borderRadius: 4,
                  fontFamily: "inherit",
                }}
              />
              <button
                className="btn btn-sm"
                onClick={saveRename}
                disabled={renameMut.isPending || !nameDraft.trim()}
                title="Speichern (Enter)"
                style={{ background: "var(--color-hermes-accent)", color: "#fff", borderColor: "var(--color-hermes-accent)" }}
              >
                {renameMut.isPending ? "..." : "✓"}
              </button>
              <button
                className="btn btn-sm"
                onClick={() => setEditingName(false)}
                title="Abbrechen (Esc)"
              >
                ✕
              </button>
            </span>
          ) : (
            <>
              <span
                className="workspace-breadcrumb"
                onClick={startRename}
                title="Klick zum Umbenennen"
                style={{ cursor: "pointer", borderBottom: "1px dashed transparent" }}
                onMouseEnter={(e) => (e.currentTarget.style.borderBottom = "1px dashed var(--color-hermes-accent-blue)")}
                onMouseLeave={(e) => (e.currentTarget.style.borderBottom = "1px dashed transparent")}
              >
                / {sop.name}
              </span>
              <button
                className="btn btn-sm"
                onClick={startRename}
                title="SOP umbenennen"
                style={{ padding: "1px 5px" }}
              >
                <Edit3 size={11} />
              </button>
            </>
          )}
        </div>
        {/* === ID-Display klein (User-Direktive 17.06.2026) === */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
          <span
            className={`id-badge ${copiedId ? "id-badge-copied" : ""}`}
            onClick={copySopId}
            title={copiedId ? "✓ Kopiert!" : `SOP-ID: ${sopId} — Klick zum Kopieren`}
            style={{ fontSize: 9, padding: "1px 5px", letterSpacing: "0.2px" }}
          >
            {copiedId ? "✓ ID kopiert" : `ID: ${sopId}`}
          </span>
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
            · v{sop.version}
          </span>
        </div>
        <p style={{ marginTop: 8 }}>{sop.description?.slice(0, 200) || "Standard Operating Procedure — Detail-Workspace"}</p>
      </div>

      <div className="subtab-bar">
        <button className={`subtab ${view === "detail" ? "active" : ""}`} onClick={() => onTabChange("detail")}>
          <Eye size={14} /> Detail
        </button>
        <button className={`subtab ${view === "instances" ? "active" : ""}`} onClick={() => onTabChange("instances")}>
          <GitBranch size={14} /> Instances
        </button>
        <button className={`subtab ${view === "bpmn" ? "active" : ""}`} onClick={() => onTabChange("bpmn")}>
          <FileCode2 size={14} /> BPMN
        </button>
        <button className={`subtab ${view === "uml" ? "active" : ""}`} onClick={() => onTabChange("uml")}>
          <ImageIcon size={14} /> UML
        </button>
        <div style={{ flex: 1 }} />
        <span className="badge badge-blue" style={{ fontSize: 10 }}>{sop.name}</span>
        <button className="btn btn-sm" onClick={() => delMut.mutate()} disabled={delMut.isPending}>
          <Trash2 size={12} /> Löschen
        </button>
      </div>

      {view === "detail" && <SopDetail sop={sop} />}
      {view === "instances" && <SopInstancesTab sopId={sopId} />}
      {view === "bpmn" && <BpmnView sopId={sopId} />}
      {view === "uml" && <UmlView sopId={sopId} />}
    </div>
  )
}

// ─────────────── SOP-Detail (Steps + Rules) ───────────────
function SopDetail({ sop }: { sop: any }) {
  // === Step-Auswahl-State (User-Direktive 16.06.2026) ===
  // Klick auf einen Step in der Liste öffnet die Sidebar rechts.
  const [selectedStepIdx, setSelectedStepIdx] = useState<number | null>(null)
  // === KI-Support-Designer-Modal (User-Direktive 17.06.2026, BUG-Fix) ===
  const [showAiSupportDesigner, setShowAiSupportDesigner] = useState(false)
  // === AddStep-Modal (User-Direktive 17.06.2026) ===
  const [showAddStep, setShowAddStep] = useState(false)
  const steps: any[] = sop.steps || []
  const selectedStep = selectedStepIdx != null ? steps[selectedStepIdx] : null
  const hasPrev = selectedStepIdx != null && selectedStepIdx > 0
  const hasNext = selectedStepIdx != null && selectedStepIdx < steps.length - 1
  function gotoPrev() { if (hasPrev) setSelectedStepIdx((selectedStepIdx as number) - 1) }
  function gotoNext() { if (hasNext) setSelectedStepIdx((selectedStepIdx as number) + 1) }

  return (
    <div style={{ display: "grid", gridTemplateColumns: selectedStep ? "1fr 570px" : "1fr", gap: 12, alignItems: "start" }}>
      {/* === Linke Spalte: Step-Liste === */}
      <div>
        <div className="card" style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Workflow size={20} color="var(--color-hermes-accent-blue)" />
            <h2 style={{ margin: 0, fontSize: 18 }}>{sop.name}</h2>
            <span className="badge badge-blue">v{sop.version}</span>
            <span className="badge badge-gray">{sop.category}</span>
            {sop.is_template && <span className="badge badge-orange">TEMPLATE</span>}
          </div>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, color: "var(--color-hermes-text-secondary)", margin: 0 }}>
            {sop.description}
          </pre>
        </div>

        <h3 style={{ fontSize: 14, margin: "12px 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
          Steps ({steps.length})
          {selectedStep != null && (
            <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", fontWeight: 400 }}>
              · Schritt {selectedStepIdx! + 1} ausgewählt
            </span>
          )}
          <div style={{ flex: 1 }} />
          <button
            className="btn btn-sm"
            onClick={() => setShowAddStep(true)}
            style={{ fontSize: 11, padding: "2px 8px" }}
            title="Neuen Step zu dieser SOP hinzufügen"
          >
            <PlusCircle size={12} style={{ marginRight: 4, verticalAlign: "middle" }} />
            Step hinzufügen
          </button>
        </h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {steps.map((s: any, idx: number) => {
            const isSelected = selectedStepIdx === idx
            return (
              <div
                key={s.id}
                onClick={() => setSelectedStepIdx(idx)}
                className="card"
                style={{
                  cursor: "pointer",
                  borderLeft: `3px solid ${
                    s.phase === "End" ? "var(--color-hermes-accent)"
                    : s.phase === "Sub-SOP" ? "var(--color-hermes-accent-orange)"
                    : "var(--color-hermes-accent-blue)"
                  }`,
                  outline: isSelected ? "2px solid var(--color-hermes-accent)" : "none",
                  outlineOffset: isSelected ? "1px" : 0,
                  background: isSelected ? "rgba(46, 160, 67, 0.06)" : undefined,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <span className="badge badge-orange">#{s.step_order}</span>
                  <strong style={{ fontSize: 13 }}>{s.name}</strong>
                  <span style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)" }}>· ID: {s.id.slice(0, 8)}</span>
                  <span className="badge badge-gray">{s.phase}</span>
                  <span className="badge badge-blue">👤 {s.agent}</span>
                  <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>⏱ {s.delay_s}s</span>
                  <div style={{ flex: 1 }} />
                  {isSelected && <span style={{ fontSize: 10, color: "var(--color-hermes-accent)", fontWeight: 600 }}>👈 Sidebar</span>}
                  {s.next_step_id && <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>→ next</span>}
                  {s.fail_step_id && <span style={{ fontSize: 10, color: "var(--color-hermes-danger)" }}>↯ fail</span>}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 4, fontSize: 12 }}>
                  <span style={{ color: "var(--color-hermes-text-secondary)" }}>Trigger:</span>
                  <span><code>{s.trigger}</code></span>
                  <span style={{ color: "var(--color-hermes-text-secondary)" }}>Action:</span>
                  <span><code>{s.action}</code></span>
                  <span style={{ color: "var(--color-hermes-text-secondary)" }}>Expected:</span>
                  <span>{s.expected_result || "—"}</span>
                </div>
                {s.rules && s.rules.length > 0 && (
                  <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--color-hermes-border)" }}>
                    <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
                      Wenn-Dann-Regeln ({s.rules.length}):
                    </div>
                    {s.rules.map((r: any) => (
                      <div key={r.id} style={{ fontSize: 11, padding: "2px 0" }}>
                        <code>if {r.condition_field} {r.condition_operator} {JSON.stringify(r.condition_value)}</code>
                        {" "}→ <code style={{ color: "var(--color-hermes-accent)" }}>{r.action_type}({r.action_target || "—"})</code>
                        {r.description && <span style={{ color: "var(--color-hermes-text-secondary)" }}> — {r.description}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* === Rechte Spalte: Detail-Sidebar (analog zu BPMN/UML) === */}
      {selectedStep && (
        <div style={{ position: "sticky", top: 12, width: 570, minWidth: 570 }}>
          <StepDetailSidebar
            sopId={sop.id}
            step={selectedStep}
            index={selectedStepIdx!}
            total={steps.length}
            hasPrev={hasPrev}
            hasNext={hasNext}
            onPrev={gotoPrev}
            onNext={gotoNext}
            onClose={() => setSelectedStepIdx(null)}
            onStepDeleted={() => {
              // Nach Löschen: Liste neu laden, Selektion aufheben
              setSelectedStepIdx(null)
            }}
            onOpenAiDesigner={() => setShowAiSupportDesigner(true)}
          />
        </div>
      )}

      {/* === KI-Support-Designer Modal (User-Direktive 17.06.2026, BUG-Fix) === */}
      {showAiSupportDesigner && selectedStep && (
        <AiSupportDesignerModal
          sopId={sop.id}
          step={selectedStep}
          onClose={() => setShowAiSupportDesigner(false)}
          initialMd={selectedStep?.action_params?.ai_instructions_md || ""}
        />
      )}

      {/* === AddStep Modal (User-Direktive 17.06.2026) === */}
      {showAddStep && (
        <AddStepModal
          sopId={sop.id}
          steps={steps}
          onClose={() => setShowAddStep(false)}
          onCreated={(newId) => {
            // Selektion auf den neu erstellten Step setzen (nach Reload)
            setTimeout(() => {
              if (newId) {
                const idx = steps.findIndex((s: any) => s.id === newId)
                if (idx >= 0) setSelectedStepIdx(idx)
              }
            }, 300)
          }}
        />
      )}
    </div>
  )
}

// ─────────────── SOP-Instances ───────────────
function SopInstancesTab({ sopId }: { sopId: string }) {
  const { data: instancesData, isLoading } = useQuery({
    queryKey: ["sop-instances", sopId],
    queryFn: () => api.listSopInstances(),
  })
  const allInstances: any[] = (instancesData as any)?.items || []
  const instances = allInstances.filter((i: any) => i.sop_id === sopId)

  if (isLoading) return <div>Lade Instances…</div>
  if (instances.length === 0) {
    return (
      <div className="card" style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
        <GitBranch size={32} style={{ marginBottom: 8 }} />
        <p>Noch keine Instances für diese SOP gestartet.</p>
        <p style={{ fontSize: 12 }}>
          Eine Instance wird gestartet, wenn ein Task an die SOP gebunden wird
          (z.B. via <code>POST /api/sops/{sopId.slice(0, 8)}…/start</code>).
        </p>
      </div>
    )
  }
  return (
    <div>
      {instances.map((inst: any) => (
        <InstanceRow key={inst.id} instance={inst} />
      ))}
    </div>
  )
}

function InstanceRow({ instance }: { instance: any }) {
  const [open, setOpen] = useState(false)
  const { data: detail, isLoading } = useQuery({
    queryKey: ["sop-instance", instance.id],
    queryFn: () => api.getSopInstance(instance.id),
    enabled: open,
  })

  return (
    <div className="card" style={{ marginBottom: 8, borderLeft: `3px solid ${statusColor(instance.status)}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <button className="btn btn-sm" style={{ padding: "0 4px" }} onClick={() => setOpen(!open)}>
          <ChevronRight size={12} style={{ transform: open ? "rotate(90deg)" : "none" }} />
        </button>
        <span className="badge badge-blue">{instance.status}</span>
        <span className="id-badge">{instance.id.slice(0, 12)}</span>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
          Started: {new Date(instance.started_at).toLocaleString("de-DE")}
        </span>
      </div>

      {open && !isLoading && detail && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--color-hermes-border)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 4, fontSize: 11, marginBottom: 8 }}>
            <span style={{ color: "var(--color-hermes-text-secondary)" }}>Project:</span>
            <span><code>{instance.project_id || "—"}</code></span>
            <span style={{ color: "var(--color-hermes-text-secondary)" }}>Task:</span>
            <span><code>{instance.task_id || "—"}</code></span>
            <span style={{ color: "var(--color-hermes-text-secondary)" }}>Current Step:</span>
            <span><code>{instance.current_step_id || "—"}</code></span>
            {instance.completed_at && (
              <>
                <span style={{ color: "var(--color-hermes-text-secondary)" }}>Completed:</span>
                <span>{new Date(instance.completed_at).toLocaleString("de-DE")}</span>
              </>
            )}
          </div>
          <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
            Execution-Log ({detail.executions?.length || 0}):
          </div>
          {detail.executions?.slice(0, 20).map((ex: any) => (
            <div key={ex.id} style={{ fontSize: 10, padding: "1px 0", color: "var(--color-hermes-text-secondary)" }}>
              <span style={{ color: ex.success ? "var(--color-hermes-accent)" : "var(--color-hermes-danger)" }}>●</span>{" "}
              {new Date(ex.ts).toLocaleTimeString("de-DE")} ·{" "}
              <code>{ex.event}</code>{" "}
              {ex.agent && <span>({ex.agent})</span>}
              {ex.duration_ms != null && <span> · {ex.duration_ms}ms</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─────────────── BPMN-View (mit bpmn-js Renderer + Detail-Sidebar) ───────────────
function BpmnView({ sopId }: { sopId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["sop-bpmn", sopId],
    queryFn: () => api.getSopBpmn(sopId),
  })

  // SOP-Daten laden (fuer Schritt-Details + RACI)
  const { data: sopData } = useQuery({
    queryKey: ["sop", sopId],
    queryFn: () => api.getSop(sopId),
  })
  const steps: any[] = ((sopData as any)?.steps || []).slice().sort((a: any, b: any) => a.step_order - b.step_order)

  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<BpmnViewer | null>(null)
  const [renderError, setRenderError] = useState<string | null>(null)
  const [rendered, setRendered] = useState(false)
  const [selectedStepIdx, setSelectedStepIdx] = useState<number>(0)
  const [highlightedElementId, setHighlightedElementId] = useState<string | null>(null)
  const [isPanning, setIsPanning] = useState(false)
  // KI-Support-Designer Modal (User-Direktive 16.06.2026)
  const [showAiSupportDesigner, setShowAiSupportDesigner] = useState(false)
  // AddStep-Modal (User-Direktive 17.06.2026)
  const [showAddStep, setShowAddStep] = useState(false)

  // BPMN-Viewer rendern + Click-Handler
  useEffect(() => {
    if (!data || !containerRef.current) return
    const xml = (data as any)?.xml || ""
    if (!xml) return

    // Cleanup: alten Viewer zerstoeren (falls vorhanden)
    if (viewerRef.current) {
      try { viewerRef.current.destroy() } catch (e) { /* ignore */ }
      viewerRef.current = null
    }
    setRendered(false)
    setRenderError(null)

    // Lokale Variarblen, damit Cleanup-Funktion async-Promises sicher abbrechen kann
    // Wichtig wegen React StrictMode (Doppel-Mount im Dev) + bpmn-js-Import-Lifecycle
    let isCancelled = false
    // BpmnModeler statt BpmnViewer: brauchen modeling.moveElements() damit Edges mitwandern
    const localViewer = new BpmnModeler({
      container: containerRef.current,
      // Keyboard-Editing deaktivieren (nur Anzeige + Drag)
      keyboard: { bindTo: undefined as any },
    })
    viewerRef.current = localViewer

    // Explizit Mouse-Events am Container erlauben (nicht blockieren)
    if (containerRef.current) {
      containerRef.current.style.touchAction = "none"
    }

    localViewer
      .importXML(xml)
      .then(({ warnings }: { warnings: any[] }) => {
        if (isCancelled) return

        // Pan + Zoom NACH importXML explizit aktivieren
        try {
          const zoomScroll: any = localViewer.get("zoomScroll")
          if (zoomScroll) {
            if (typeof zoomScroll.toggle === "function") zoomScroll.toggle(true)
            // Auch Keyboard-Addons aktivieren
            if (typeof zoomScroll.addEventListener === "function") {
              console.log("[BPMN] zoomScroll aktiv")
            }
          }
          const moveCanvas: any = localViewer.get("moveCanvas")
          if (moveCanvas) {
            if (typeof moveCanvas.toggle === "function") moveCanvas.toggle(true)
            console.log("[BPMN] moveCanvas aktiv")
          }
        } catch (e) {
          console.warn("[BPMN] Controls-Toggle fehlgeschlagen:", e)
        }

        try {
          const canvas = localViewer.get<any>("canvas")
          if (canvas) canvas.zoom("fit-viewport", "auto")
        } catch (e) {
          console.warn("[BPMN] Zoom fehlgeschlagen:", e)
        }

        // === DRAG-FUNKTION: SubProcesses per Maus verschieben (User-Direktive 17.06.2026) ===
        // BpmnModeler + modeling.moveElements() -> Edges wandern automatisch mit
        try {
          const eventBus: any = localViewer.get("eventBus")
          const canvas: any = localViewer.get("canvas")
          const modeling: any = localViewer.get("modeling", false)
          const elementRegistry: any = localViewer.get("elementRegistry", false)
          if (eventBus && canvas && modeling && elementRegistry) {
            // Cursor aendern wenn ueber SubProcess
            eventBus.on("element.hover", (e: any) => {
              const el = e?.element
              if (el && el.type === "bpmn:SubProcess") {
                canvas.getContainer().style.cursor = "move"
              }
            })
            eventBus.on("element.out", () => {
              canvas.getContainer().style.cursor = "grab"
            })

            // Drag-Logik: Mousedown auf SubProcess -> Mousemove -> Mouseup
            let dragState: {
              el: any
              startMouseX: number
              startMouseY: number
              origX: number
              origY: number
            } | null = null

            // Pixel-zu-Modell-Koordinaten
            function clientToModel(clientX: number, clientY: number): { x: number; y: number } {
              const evt = { clientX, clientY } as MouseEvent
              const point = canvas._clientToCanvas ? canvas._clientToCanvas(evt) : null
              if (point) return { x: point.x, y: point.y }
              // Fallback: zoom-Faktor aus canvas.zoom() nutzen
              const z = canvas.zoom() || 1
              const viewbox = canvas.viewbox()
              const containerRect = canvas.getContainer().getBoundingClientRect()
              const x = (clientX - containerRect.left) / z + viewbox.x
              const y = (clientY - containerRect.top) / z + viewbox.y
              return { x, y }
            }

            const onMouseDown = (e: MouseEvent) => {
              const target = e.target as HTMLElement
              // Pruefen ob das Target innerhalb eines SubProcess-Elements liegt
              const subProcessG = target.closest('g.djs-element[data-element-id^="sp"]') as HTMLElement | null
              if (!subProcessG) return
              const elemId = subProcessG.getAttribute("data-element-id")
              if (!elemId || !elemId.startsWith("sp")) return
              const el = elementRegistry.get(elemId)
              if (!el || el.type !== "bpmn:SubProcess") return

              dragState = {
                el,
                startMouseX: e.clientX,
                startMouseY: e.clientY,
                origX: el.x,
                origY: el.y,
              }
              e.preventDefault()
              e.stopPropagation()
            }

            const onMouseMove = (e: MouseEvent) => {
              if (!dragState) return
              // Maus-Delta in Modell-Koordinaten umrechnen
              const startModel = clientToModel(dragState.startMouseX, dragState.startMouseY)
              const currentModel = clientToModel(e.clientX, e.clientY)
              const newX = dragState.origX + (currentModel.x - startModel.x)
              const newY = dragState.origY + (currentModel.y - startModel.y)
              // Nur updaten wenn Position sich geaendert hat
              if (dragState.el.x !== newX || dragState.el.y !== newY) {
                modeling.moveElements([dragState.el], { x: newX, y: newY })
              }
            }

            const onMouseUp = () => {
              dragState = null
            }

            const containerEl = canvas.getContainer()
            containerEl.addEventListener("mousedown", onMouseDown as any)
            window.addEventListener("mousemove", onMouseMove)
            window.addEventListener("mouseup", onMouseUp)

            // Cleanup-Funktion registrieren
            ;(localViewer as any)._dragCleanup = () => {
              containerEl.removeEventListener("mousedown", onMouseDown as any)
              window.removeEventListener("mousemove", onMouseMove)
              window.removeEventListener("mouseup", onMouseUp)
            }
            console.log("[BPMN] Drag-Funktion aktiv (SubProcess + Edges)")
          }
        } catch (e) {
          console.warn("[BPMN] Drag-Setup fehlgeschlagen:", e)
        }

        setRendered(true)
        // Event-Listener fuer Node-Klicks
        try {
          const eventBus = localViewer.get<any>("eventBus")
          if (eventBus) {
            eventBus.on("element.click", (e: any) => {
              const el = e?.element
              if (!el) return
              const id = el.id || ""
              if (id.startsWith("step_")) {
                const stepId = id.replace("step_", "")
                const idx = steps.findIndex((s: any) => s.id === stepId)
                if (idx >= 0) {
                  setSelectedStepIdx(idx)
                  setHighlightedElementId(id)
                }
              } else {
                setHighlightedElementId(id)
              }
            })
          }
        } catch (e) {
          console.warn("BPMN-EventBus-Setup fehlgeschlagen:", e)
        }
        if (warnings && warnings.length > 0) {
          console.warn("BPMN-Warnings:", warnings)
        }
      })
      .catch((err: any) => {
        if (isCancelled) return
        console.error("BPMN-Import fehlgeschlagen:", err)
        setRenderError(err?.message || String(err))
      })

    return () => {
      isCancelled = true
      // Drag-Cleanup
      try {
        const cleanup = (localViewer as any)._dragCleanup
        if (typeof cleanup === "function") cleanup()
      } catch (e) { /* ignore */ }
      if (viewerRef.current === localViewer) {
        try { localViewer.destroy() } catch (e) { /* ignore */ }
        viewerRef.current = null
      }
    }
  }, [data, steps.length])

  // Highlight-Effekt: gewaehlter Node bekommt farbigen Outline
  useEffect(() => {
    if (!rendered) return
    // bpmn-js rendert in den HTML-Container (containerRef) — wir queryen direkt darin
    const root = containerRef.current
    if (!root || typeof root.querySelectorAll !== "function") return
    // Alle vorhandenen Outlines zuruecksetzen
    root.querySelectorAll(".djs-element").forEach((el) => {
      const h = el as HTMLElement
      h.style.outline = ""
      h.style.outlineOffset = ""
    })
    if (highlightedElementId) {
      // Finde das Element per ID (bpmn-js nutzt g-Element mit data-element-id)
      const nodeEl = root.querySelector(`[data-element-id="${highlightedElementId}"]`) as HTMLElement | null
      if (nodeEl) {
        nodeEl.style.outline = "3px solid #f0c674"
        nodeEl.style.outlineOffset = "2px"
      }
    }
  }, [highlightedElementId, rendered])

  // Mouse-Event-Listener entfernt - bpmn-js NavigatedViewer hat Pan/Zoom eingebaut
  // Eigene Mouse-Listener wuerden bpmn-js-Events blockieren
  useEffect(() => {
    // (leer - Pan/Zoom wird vom NavigatedViewer nativ gehandhabt)
  }, [rendered])

  // Zoom-Controls
  function zoomIn() {
    const canvas = viewerRef.current?.get<any>("canvas")
    if (canvas) canvas.zoom(canvas.zoom() * 1.2)
  }
  function zoomOut() {
    const canvas = viewerRef.current?.get<any>("canvas")
    if (canvas) canvas.zoom(canvas.zoom() / 1.2)
  }
  function fitToViewport() {
    const canvas = viewerRef.current?.get<any>("canvas")
    if (canvas) canvas.zoom("fit-viewport", "auto")
  }

  // Navigation: Vorheriger / Naechster / Start / Ende
  function gotoPrev() {
    if (selectedStepIdx > 0) {
      setSelectedStepIdx(selectedStepIdx - 1)
      const step = steps[selectedStepIdx - 1]
      if (step) setHighlightedElementId(`step_${step.id}`)
    }
  }
  function gotoNext() {
    if (selectedStepIdx < steps.length - 1) {
      setSelectedStepIdx(selectedStepIdx + 1)
      const step = steps[selectedStepIdx + 1]
      if (step) setHighlightedElementId(`step_${step.id}`)
    }
  }
  function gotoStart() { setHighlightedElementId(`start_${sopId}`) }
  function gotoEnd() {
    if (steps.length > 0) setSelectedStepIdx(steps.length - 1)
    setHighlightedElementId(`end_${sopId}`)
  }

  if (isLoading) return <div>Lade BPMN...</div>

  const selectedStep = steps[selectedStepIdx]
  const hasPrev = selectedStepIdx > 0
  const hasNext = selectedStepIdx < steps.length - 1

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 240px)", minHeight: 600 }}>
      {/* === Toolbar oben === */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
        <FileCode2 size={16} color="var(--color-hermes-accent-blue)" />
        <h3 style={{ margin: 0, fontSize: 14 }}>BPMN 2.0 Prozess-Diagramm</h3>
        <span className="badge badge-blue" style={{ fontSize: 10 }}>bpmn-js</span>
        <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
          {steps.length} Schritte
        </span>
        <div style={{ width: 1, height: 18, background: "var(--color-hermes-border)", margin: "0 4px" }} />

        {/* Navigation: Start / Vor / Counter / Naechster / Ende */}
        <button className="btn btn-sm" onClick={gotoStart} title="Zum Start-Event" disabled={!rendered}>
          ⏮
        </button>
        <button className="btn btn-sm" onClick={gotoPrev} disabled={!hasPrev} title="Vorheriger Schritt">
          <ChevronRight size={12} style={{ transform: "rotate(180deg)" }} />
        </button>
        <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", minWidth: 70, textAlign: "center" }}>
          {selectedStep ? `${selectedStepIdx + 1} / ${steps.length}` : "—"}
        </span>
        <button className="btn btn-sm" onClick={gotoNext} disabled={!hasNext} title="Nächster Schritt">
          <ChevronRight size={12} />
        </button>
        <button className="btn btn-sm" onClick={gotoEnd} title="Zum End-Event" disabled={!rendered}>
          ⏭
        </button>
        <div style={{ width: 1, height: 18, background: "var(--color-hermes-border)", margin: "0 4px" }} />

        {/* Zoom-Controls */}
        <button className="btn btn-sm" onClick={zoomIn} title="Vergrößern"><ZoomIn size={12} /></button>
        <button className="btn btn-sm" onClick={zoomOut} title="Verkleinern"><ZoomOut size={12} /></button>
        <button className="btn btn-sm" onClick={fitToViewport} title="Zentrieren / Einpassen (alle Elemente sichtbar)"><Maximize2 size={12} /></button>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", padding: "0 8px" }} title="Mit Mausrad zoomen, mit gedrückter linker Maustaste verschieben">
          🖱 Scroll = Zoom | Drag = Verschieben
        </span>

        {/* + Step hinzufügen (User-Direktive 17.06.2026) */}
        <button
          className="btn btn-sm"
          onClick={() => setShowAddStep(true)}
          title="Neuen Step zur SOP hinzufügen"
          style={{ background: "linear-gradient(135deg, #2ea043 0%, #58a6ff 100%)", color: "#fff", fontWeight: 600 }}
        >
          <PlusCircle size={12} /> Step hinzufügen
        </button>
        <a
          className="btn btn-sm"
          href={`data:text/xml;charset=utf-8,${encodeURIComponent((data as any)?.xml || "")}`}
          download={`sop-${sopId.slice(0, 8)}.bpmn`}
          title="BPMN-XML herunterladen"
        >
          <Download size={12} /> XML
        </a>
        {/* KI-Support-Designer (User-Direktive 16.06.2026) — links neben XML */}
        <button
          className="btn btn-sm"
          onClick={() => setShowAiSupportDesigner(true)}
          disabled={!selectedStep}
          title={selectedStep ? "KI-Support Designer: aus Freitext eine Markdown-Anweisung fuer den PI-Agent generieren" : "Zuerst einen Schritt im Diagramm auswaehlen"}
          style={{ background: selectedStep ? "linear-gradient(135deg, #a371f7 0%, #58a6ff 100%)" : undefined, color: selectedStep ? "#fff" : undefined, fontWeight: 600 }}
        >
          🪄 KI-Support Designer
        </button>
      </div>

      {renderError && (
        <div className="card" style={{ borderLeft: "3px solid var(--color-hermes-danger)", marginBottom: 8, fontSize: 12, color: "var(--color-hermes-danger)" }}>
          ⚠ Render-Fehler: {renderError}
        </div>
      )}

      {/* === Body: Canvas (links, mittig) + Detail-Sidebar (rechts) === */}
      <div style={{ display: "flex", flex: 1, gap: 8, minHeight: 0 }}>
        {/* Canvas — immer mittig durch bpmn-js fit-viewport */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          <div
            ref={containerRef}
            style={{
              flex: 1,
              background: "#fafbfc",
              border: "1px solid var(--color-hermes-border)",
              borderRadius: 6,
              position: "relative",
              // Visueller Hinweis: Cursor wird zu 'grab' (Hand), beim Ziehen zu 'grabbing'
              cursor: !rendered ? "default" : "grab",
              // Smooth-Transitions fuer Zoom
              transition: rendered ? "none" : undefined,
              overflow: "hidden",
            }}
          >
            {!rendered && !renderError && (
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-hermes-text-secondary)" }}>
                BPMN wird gerendert...
              </div>
            )}
          </div>
          <div style={{ marginTop: 6, fontSize: 11, color: "var(--color-hermes-text-secondary)", textAlign: "center", display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap" }}>
            <span><strong style={{ color: "var(--color-hermes-accent-blue)" }}>🖱️ Ziehen</strong> = Verschieben (Pan)</span>
            <span><strong style={{ color: "var(--color-hermes-accent-blue)" }}>🔍 Mausrad</strong> = Zoom rein/raus</span>
            <span><strong style={{ color: "var(--color-hermes-accent-blue)" }}>⌨️ Strg+±</strong> = Zoom (Tastatur)</span>
            <span><strong style={{ color: "var(--color-hermes-accent-blue)" }}>👆 Klick auf Node</strong> = Details rechts</span>
            <button
              className="btn btn-sm"
              onClick={fitToViewport}
              style={{ fontSize: 10, padding: "1px 8px" }}
              title="Zentriert das Diagramm und passt die Ansicht ein"
            >
              <Maximize2 size={10} /> Zentrieren
            </button>
          </div>
        </div>

        {/* Detail-Sidebar rechts */}
        <div style={{ width: 540, flexShrink: 0, display: "flex", flexDirection: "column", gap: 8, overflowY: "auto" }}>
          {selectedStep ? (
            <StepDetailSidebar
              sopId={sopId}
              step={selectedStep}
              index={selectedStepIdx}
              total={steps.length}
              hasPrev={hasPrev}
              hasNext={hasNext}
              onPrev={gotoPrev}
              onNext={gotoNext}
              onOpenAiDesigner={() => setShowAiSupportDesigner(true)}
            />
          ) : (
            <div className="card" style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", textAlign: "center", padding: 20 }}>
              👉 Klick auf einen Node im Diagramm, um Details zu sehen
            </div>
          )}
        </div>
      </div>

      {/* KI-Support-Designer Modal (User-Direktive 16.06.2026) */}
      {showAiSupportDesigner && selectedStep && (
        <AiSupportDesignerModal
          sopId={sopId}
          step={selectedStep}
          onClose={() => setShowAiSupportDesigner(false)}
          initialMd={selectedStep?.action_params?.ai_instructions_md || ""}
        />
      )}

      {/* AddStep Modal (User-Direktive 17.06.2026) */}
      {showAddStep && (
        <AddStepModal
          sopId={sopId}
          steps={steps}
          onClose={() => setShowAddStep(false)}
          onCreated={() => { /* refresh via qc.invalidateQueries im Modal */ }}
        />
      )}
    </div>
  )
}

// ─────────────── Gemeinsame Step-Detail-Sidebar (BPMN, UML, SOP-Detail) ───────────────
// Wird in allen Views wiederverwendet, die einen Step-Detail anzeigen.
// Zeigt alle Step-Infos, editierbare Description, TTS-Button, Success-Criteria, Rules.
function StepDetailSidebar({
  sopId, step, index, total, hasPrev, hasNext, onPrev, onNext, onClose, onStepDeleted, onOpenAiDesigner,
}: {
  sopId: string
  step: any
  index: number
  total: number
  hasPrev: boolean
  hasNext: boolean
  onPrev: () => void
  onNext: () => void
  onClose?: () => void
  onStepDeleted?: () => void
  onOpenAiDesigner?: () => void
}) {
  const qc = useQueryClient()
  const updateMut = useMutation({
    mutationFn: (data: { agent?: string; model?: string }) => api.updateSopStep(sopId, step.id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sop", sopId] })
      qc.invalidateQueries({ queryKey: ["sop-bpmn", sopId] })
      qc.invalidateQueries({ queryKey: ["sop-uml", sopId] })
    },
  })

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%" }}>
      {/* Header */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
          <div style={{ flex: 1, fontSize: 10, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", letterSpacing: 0.5 }}>
            Schritt {index + 1} / {total} · ID: <code style={{ color: "var(--color-hermes-accent-blue)" }}>{step.id}</code>
          </div>
          {onClose && (
            <button
              className="btn btn-sm"
              onClick={onClose}
              title="Sidebar schliessen"
              style={{ padding: "1px 6px", fontSize: 10 }}
            >
              <X size={10} /> Schliessen
            </button>
          )}
        </div>
        <h3 style={{ margin: "4px 0 8px", fontSize: 15, fontWeight: 600, color: "var(--color-hermes-accent-blue)" }}>
          {step.name}
        </h3>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
          <span className="badge badge-blue" style={{ fontSize: 10 }}>{step.phase}</span>
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginLeft: 4 }}>Agent:</span>
          <AgentSelect
            value={step.agent || ""}
            onChange={(agent) => updateMut.mutate({ agent })}
            style={{ width: 130, fontSize: 11 }}
          />
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginLeft: 4 }}>Modell:</span>
          <AgentModelDisplay
            agent={step.agent || ""}
            style={{ width: 190 }}
          />
          {step.action && <span className="badge badge-gray" style={{ fontSize: 10 }}>⚡ {step.action}</span>}
        </div>
      </div>

      {/* === KI-Anweisungen (Markdown) — User-Direktive 16.06.2026 === */}
      <AiInstructionsEditor
        sopId={sopId}
        stepId={step.id}
        step={step}
        onOpenAiDesigner={onOpenAiDesigner}
      />

      {/* === Agent-Tools (User-Direktive 17.06.2026) === */}
      <SopStepToolSelector
        sopId={sopId}
        stepId={step.id}
        step={step}
      />

      {/* Navigation: Vorheriger / Nächster */}
      <div style={{ display: "flex", gap: 6 }}>
        <button
          className="btn btn-sm"
          onClick={onPrev}
          disabled={!hasPrev}
          style={{ flex: 1 }}
        >
          ← Vorheriger
        </button>
        <button
          className="btn btn-sm btn-primary"
          onClick={onNext}
          disabled={!hasNext}
          style={{ flex: 1 }}
        >
          Nächster →
        </button>
      </div>

      {/* Trigger, Action, Delay — kurze Metadaten (User-Direktive 16.06.2026) */}
      {step.trigger && (
        <DetailRow label="Trigger" value={step.trigger} mono />
      )}
      {step.action && (
        <DetailRow label="Action" value={step.action} mono />
      )}
      {step.delay_s != null && (
        <DetailRow label="Verzögerung" value={`${step.delay_s}s`} mono />
      )}

      {/* Was-passiert-hier / Success-Criteria / RACI wurden entfernt — alles jetzt in den KI-Anweisungen */}
    </div>
  )
}

function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, fontSize: 12, padding: "4px 0", borderBottom: "1px dashed var(--color-hermes-border)" }}>
      <span style={{ color: "var(--color-hermes-text-secondary)" }}>{label}</span>
      <span style={{ color: "var(--color-hermes-text)", fontFamily: mono ? "var(--font-mono)" : undefined, fontSize: mono ? 11 : 12 }}>{value}</span>
    </div>
  )
}

function RaciRow({ label, value }: { label: string; value?: string | null }) {
  const hasValue = value && value.trim().length > 0
  return (
    <tr>
      <td style={{ padding: "3px 6px 3px 0", color: "var(--color-hermes-text-secondary)", fontSize: 11, verticalAlign: "top", width: "40%" }}>{label}</td>
      <td style={{ padding: "3px 0", color: hasValue ? "var(--color-hermes-text)" : "var(--color-hermes-text-secondary)", fontStyle: hasValue ? "normal" : "italic", fontSize: 11 }}>
        {hasValue ? value : "—"}
      </td>
    </tr>
  )
}

// ─────────────── KI-Anweisungen-Editor (User-Direktive 16.06.2026) ───────────────
function AiInstructionsEditor({
  sopId, stepId, step, onOpenAiDesigner,
}: {
  sopId: string
  stepId: string
  step: any
  onOpenAiDesigner?: () => void
}) {
  const qc = useQueryClient()
  const aiMd = step?.action_params?.ai_instructions_md || ""
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(aiMd)
  const [saving, setSaving] = useState(false)
  const [showPreview, setShowPreview] = useState(true)

  // Reset draft wenn step sich ändert
  useEffect(() => { setDraft(aiMd); setEditing(false) }, [aiMd, stepId])

  const isEmpty = !aiMd.trim()

  async function save() {
    setSaving(true)
    try {
      await api.updateSopStep(sopId, stepId, { ai_instructions_md: draft })
      qc.invalidateQueries({ queryKey: ["sop", sopId] })
      qc.invalidateQueries({ queryKey: ["sop-bpmn", sopId] })
      qc.invalidateQueries({ queryKey: ["sop-uml", sopId] })
      setEditing(false)
    } catch (e: any) {
      alert("Speichern fehlgeschlagen: " + (e.message || e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{
      background: isEmpty ? "var(--color-hermes-bg-secondary)" : "linear-gradient(135deg, #1a2a3a 0%, #2a1f3a 100%)",
      border: `1px solid ${isEmpty ? "var(--color-hermes-border)" : "#a371f7"}`,
      borderRadius: 6, padding: 8,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
        <div style={{ fontSize: 13 }}>🪄</div>
        <div style={{ fontSize: 10, fontWeight: 600, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, flex: 1 }}>
          KI-Anweisungen für den PI-Agent
        </div>
        {!isEmpty && (
          <span className="badge badge-blue" style={{ fontSize: 9 }}>
            {aiMd.length} Zeichen
          </span>
        )}
      </div>
      {isEmpty ? (
        editing ? (
          // === Edit-Modus bei initial leeren Anweisungen (User-Direktive 17.06.2026, BUG-Fix) ===
          <>
            <textarea
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="// Schreibe hier deine Anweisungen fuer diesen Step. Markdown wird unterstuetzt."
              style={{
                width: "100%", minHeight: 200, padding: 8, fontSize: 11, lineHeight: 1.5,
                fontFamily: "var(--font-mono)", resize: "vertical",
                background: "var(--color-hermes-bg)", color: "var(--color-hermes-text)",
                border: "1px solid var(--color-hermes-border)", borderRadius: 4,
              }}
            />
            <div style={{ display: "flex", gap: 4, marginTop: 6, alignItems: "center" }}>
              <button className="btn btn-sm btn-primary" onClick={save} disabled={saving || !draft.trim()} style={{ fontSize: 10, padding: "2px 8px" }}>
                {saving ? "💾..." : "💾 Speichern"}
              </button>
              <button className="btn btn-sm" onClick={() => { setEditing(false); setDraft("") }} style={{ fontSize: 10, padding: "2px 8px" }}>
                Abbrechen
              </button>
              <div style={{ flex: 1 }} />
              {onOpenAiDesigner && (
                <button
                  className="btn btn-sm"
                  onClick={onOpenAiDesigner}
                  title="Stattdessen mit KI-Unterstuetzung generieren"
                  style={{ fontSize: 10, padding: "2px 8px", background: "linear-gradient(135deg, #a371f7 0%, #58a6ff 100%)", color: "#fff", fontWeight: 600 }}
                >
                  🪄 Stattdessen mit KI
                </button>
              )}
            </div>
          </>
        ) : (
          // === Anzeige-Modus bei leeren Anweisungen (zwei Optionen) ===
          <div style={{ textAlign: "center", padding: "12px 8px" }}>
            <p style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", margin: "0 0 8px" }}>
              Noch keine KI-Anweisung vorhanden. Wähle, wie du vorgehen möchtest:
            </p>
            <div style={{ display: "flex", gap: 6, justifyContent: "center", flexWrap: "wrap" }}>
              <button
                className="btn btn-sm"
                onClick={() => { setDraft(""); setEditing(true) }}
                style={{ fontSize: 10, padding: "4px 10px" }}
                title="Schreibe die Anweisungen direkt als Markdown"
              >
                ✏️ Direkt schreiben
              </button>
              {onOpenAiDesigner && (
                <button
                  className="btn btn-sm btn-primary"
                  onClick={onOpenAiDesigner}
                  style={{ background: "linear-gradient(135deg, #a371f7 0%, #58a6ff 100%)", border: "none", fontWeight: 600, fontSize: 10, padding: "4px 10px" }}
                >
                  🪄 KI-Support Designer öffnen
                </button>
              )}
            </div>
          </div>
        )
      ) : (
        <>
          {editing ? (
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              style={{
                width: "100%", minHeight: 200, padding: 8, fontSize: 11, lineHeight: 1.5,
                fontFamily: "var(--font-mono)", resize: "vertical",
                background: "var(--color-hermes-bg)", color: "var(--color-hermes-text)",
                border: "1px solid var(--color-hermes-border)", borderRadius: 4,
              }}
            />
          ) : showPreview ? (
            <div style={{
              minHeight: 100, maxHeight: 300, overflow: "auto", padding: 8,
              background: "var(--color-hermes-bg)", borderRadius: 4,
              fontSize: 12, lineHeight: 1.5,
            }}>
              <ReactMarkdown components={mdComponents}>{aiMd}</ReactMarkdown>
            </div>
          ) : (
            <pre style={{
              minHeight: 100, maxHeight: 300, overflow: "auto", padding: 8, margin: 0,
              background: "var(--color-hermes-bg)", borderRadius: 4,
              fontSize: 11, lineHeight: 1.5, fontFamily: "var(--font-mono)",
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>{aiMd}</pre>
          )}
          <div style={{ display: "flex", gap: 4, marginTop: 6, alignItems: "center", flexWrap: "wrap" }}>
            {editing ? (
              <>
                <button className="btn btn-sm btn-primary" onClick={save} disabled={saving} style={{ fontSize: 10, padding: "2px 8px" }}>
                  {saving ? "💾..." : "💾 Speichern"}
                </button>
                <button className="btn btn-sm" onClick={() => { setEditing(false); setDraft(aiMd) }} style={{ fontSize: 10, padding: "2px 8px" }}>
                  Abbrechen
                </button>
              </>
            ) : (
              <>
                <button className="btn btn-sm" onClick={() => setEditing(true)} style={{ fontSize: 10, padding: "2px 8px" }}>
                  ✏️ Bearbeiten
                </button>
                <button
                  className={`btn btn-sm ${showPreview ? "btn-primary" : ""}`}
                  onClick={() => setShowPreview(!showPreview)}
                  style={{ fontSize: 10, padding: "2px 8px" }}
                >
                  {showPreview ? "📝 Quelltext" : "👁 Vorschau"}
                </button>
              </>
            )}
            <div style={{ flex: 1 }} />
            {onOpenAiDesigner && (
              <button
                className="btn btn-sm"
                onClick={onOpenAiDesigner}
                title="Mit KI-Unterstuetzung im Chat-Dialog aendern"
                style={{ fontSize: 10, padding: "2px 8px", background: "linear-gradient(135deg, #a371f7 0%, #58a6ff 100%)", color: "#fff", fontWeight: 600 }}
              >
                🪄 Mit KI aendern (Chat)
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ─────────────── KI-Support-Designer Modal (User-Direktive 16.06.2026) ───────────────
function AiSupportDesignerModal({
  sopId, step, onClose, onApplied, initialMd,
}: {
  sopId: string
  step: any
  onClose: () => void
  onApplied?: (aiMd: string) => void
  initialMd?: string  // Bereits gespeicherter MD-Text (fuer "Bearbeiten")
}) {
  const qc = useQueryClient()
  const tts = useTTSContext()
  // Standard: ollama/gemma4:12b (lokal, User-Direktive 16.06.2026 — Cloud-API nicht erlaubt fuer KI-Support Designer)
  const [model, setModel] = useState<string>("ollama/gemma4:12b")
  const [aiMd, setAiMd] = useState<string>(initialMd || "")
  const [chatInput, setChatInput] = useState<string>("")
  const [chatHistory, setChatHistory] = useState<Array<{ role: "user" | "assistant"; content: string }>>([])
  const [evaluating, setEvaluating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(true)
  // TTS: Cursor-Position im Editor (wenn showPreview=false)
  const editorRef = useRef<HTMLTextAreaElement>(null)
  const [ttsCursor, setTtsCursor] = useState<number>(0)
  const chatEndRef = useRef<HTMLDivElement>(null)

  // Auto-Scroll zum Ende des Chats
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [chatHistory, evaluating])

  async function sendMessage() {
    const msg = chatInput.trim()
    if (msg.length < 10) {
      setError("Bitte mindestens 10 Zeichen eingeben.")
      return
    }
    setError(null)
    setChatInput("")
    const newHistory: Array<{ role: "user" | "assistant"; content: string }> = [
      ...chatHistory,
      { role: "user", content: msg }
    ]
    setChatHistory(newHistory)
    setEvaluating(true)
    try {
      const result = await api.aiStepEvaluate(
        sopId, step.id, msg, model, false,  // user_input, model, auto_save
        aiMd,                                // current_md
        newHistory.map(m => ({ role: m.role, content: m.content }))  // conversation
      )
      const newMd = result.ai_instructions_md || ""
      setAiMd(newMd)
      setChatHistory([...newHistory, { role: "assistant", content: "✅ Markdown-Anweisung aktualisiert (siehe rechts)" }])
    } catch (e: any) {
      setError(`LLM-Fehler: ${e.message || e}`)
      setChatHistory([...newHistory, { role: "assistant", content: `⚠ Fehler: ${e.message || e}` }])
    } finally {
      setEvaluating(false)
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  async function onApplyAndSave() {
    if (!aiMd.trim()) {
      setError("Zuerst KI-Anweisung generieren — kein MD-Text vorhanden.")
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.updateSopStep(sopId, step.id, { ai_instructions_md: aiMd })
      qc.invalidateQueries({ queryKey: ["sop", sopId] })
      qc.invalidateQueries({ queryKey: ["sop-bpmn", sopId] })
      qc.invalidateQueries({ queryKey: ["sop-uml", sopId] })
      onApplied?.(aiMd)
      onClose()
    } catch (e: any) {
      setError(`Speichern fehlgeschlagen: ${e.message || e}`)
    } finally {
      setSaving(false)
    }
  }

  // Esc schliesst
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [onClose])

  // === TTS-Funktionen (User-Direktive 16.06.2026) =================
  // Vorgelesen wird IMMER ab aktueller Cursor-Position bis zum Ende
  // Funktioniert in beiden Modi (Preview + Editor), aber Cursor nur
  // im Editor-Modus explizit erfassbar.
  function startTtsFromCursor() {
    if (!aiMd.trim()) {
      setError("Kein Text zum Vorlesen vorhanden.")
      return
    }
    let startPos = 0
    if (!showPreview && editorRef.current) {
      // Editor-Modus: echte Cursor-Position aus Textarea
      startPos = editorRef.current.selectionStart ?? 0
    } else {
      // Preview-Modus: zuletzt gemerkte Cursor-Position nutzen (oder 0)
      startPos = ttsCursor
    }
    const textToSpeak = aiMd.slice(startPos)
    if (!textToSpeak.trim()) {
      setError("Cursor steht am Ende des Dokuments — nichts zu sprechen.")
      return
    }
    setError(null)
    tts.speakFrom(aiMd, startPos)
  }

  function stopTts() {
    tts.stop()
  }

  // TTS-Modus aktiv? Button wird zu "Stop"
  const isSpeakingAiMd = tts.speaking
  // TTS global deaktiviert? Buttons ausblenden
  const ttsEnabled = tts.mode !== "off"

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 9999, padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--color-hermes-surface)",
          borderRadius: 8, border: "1px solid var(--color-hermes-border)",
          width: "min(1200px, 95vw)", maxWidth: 1200,
          height: "min(780px, 90vh)", maxHeight: 780,
          display: "flex", flexDirection: "column", overflow: "hidden",
          boxShadow: "0 20px 50px rgba(0,0,0,0.5)",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", padding: "12px 16px", borderBottom: "1px solid var(--color-hermes-border)", gap: 8 }}>
          <div style={{ fontSize: 18 }}>🪄</div>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>KI-Support Designer (Chat)</h2>
          <span className="badge badge-blue" style={{ fontSize: 10 }}>User-Direktive 16.06.2026</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
            Schritt: <strong style={{ color: "var(--color-hermes-accent-blue)" }}>{step.name}</strong>
            {" · Agent: "}<strong>{step.agent}</strong>
          </span>
          <button className="btn btn-sm" onClick={onClose} title="Schliessen (Esc)" style={{ marginLeft: 8 }}>
            <X size={12} />
          </button>
        </div>

        {/* Body: 2-Spalten Layout */}
        <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
          {/* LINKS: Chat-UI */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", borderRight: "1px solid var(--color-hermes-border)", padding: 12, gap: 8, minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", letterSpacing: 0.5 }}>
              💬 Chat mit der KI
            </div>
            <p style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", margin: "0 0 4px" }}>
              Schicke einzelne Sätze, was dieser Schritt tun soll, prüfen muss, welche Edge-Cases es gibt.
              Mit jedem Satz wird die rechte Markdown-Anweisung verbessert. Enter = Senden, Shift+Enter = Zeilenumbruch.
            </p>

            {/* Chat-History (scrollbar) */}
            <div style={{
              flex: 1, overflowY: "auto", padding: 8,
              background: "var(--color-hermes-bg)", border: "1px solid var(--color-hermes-border)", borderRadius: 4,
              display: "flex", flexDirection: "column", gap: 6,
            }}>
              {chatHistory.length === 0 && !evaluating && (
                <div style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)", fontSize: 11, padding: 20 }}>
                  <div style={{ fontSize: 32, opacity: 0.3 }}>💭</div>
                  <p>Noch keine Nachricht. Schreib deinen ersten Satz unten.</p>
                  {initialMd && (
                    <p style={{ fontSize: 10, marginTop: 8 }}>
                      <strong>Tipp:</strong> Es ist bereits ein MD-Text gespeichert.<br/>
                      Schicke Verbesserungen — die KI integriert sie automatisch.
                    </p>
                  )}
                </div>
              )}
              {chatHistory.map((msg, i) => (
                <div key={i} style={{
                  alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "85%",
                  padding: "6px 10px", borderRadius: 8,
                  background: msg.role === "user" ? "linear-gradient(135deg, #58a6ff 0%, #a371f7 100%)" : "var(--color-hermes-surface-2)",
                  color: msg.role === "user" ? "#fff" : "var(--color-hermes-text)",
                  fontSize: 12, lineHeight: 1.5,
                  border: msg.role === "user" ? "none" : "1px solid var(--color-hermes-border)",
                  whiteSpace: "pre-wrap", wordBreak: "break-word",
                }}>
                  <div style={{ fontSize: 9, opacity: 0.7, marginBottom: 2 }}>
                    {msg.role === "user" ? "👤 Du" : "🪄 KI"}
                  </div>
                  {msg.content}
                </div>
              ))}
              {evaluating && (
                <div style={{
                  alignSelf: "flex-start",
                  padding: "6px 10px", borderRadius: 8,
                  background: "var(--color-hermes-surface-2)", border: "1px solid var(--color-hermes-border)",
                  fontSize: 12, color: "var(--color-hermes-text-secondary)",
                }}>
                  <div style={{ fontSize: 9, opacity: 0.7, marginBottom: 2 }}>🪄 KI</div>
                  ⏳ Denke nach und aktualisiere die Markdown-Anweisung...
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {error && (
              <div style={{ padding: "6px 10px", background: "var(--color-hermes-danger)", color: "#fff", borderRadius: 4, fontSize: 11 }}>
                ⚠ {error}
              </div>
            )}

            {/* Chat-Input (UEBER dem Modell-Selector) */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <textarea
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Schreibe einen Satz... (Enter = Senden, Shift+Enter = Zeilenumbruch)"
                style={{
                  minHeight: 60, maxHeight: 100, padding: 8, fontSize: 12, lineHeight: 1.5,
                  fontFamily: "var(--font-mono)", resize: "vertical",
                  background: "var(--color-hermes-bg)", color: "var(--color-hermes-text)",
                  border: "1px solid var(--color-hermes-border)", borderRadius: 4,
                }}
                disabled={evaluating}
              />
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <button
                  className="btn btn-sm"
                  onClick={sendMessage}
                  disabled={evaluating || chatInput.trim().length < 10}
                  style={{ background: "linear-gradient(135deg, #a371f7 0%, #58a6ff 100%)", color: "#fff", fontWeight: 600, flex: 1 }}
                  title="Satz an die KI senden (Enter)"
                >
                  {evaluating ? "⏳ Verarbeite..." : "📤 Senden (Enter)"}
                </button>
                <button
                  className="btn btn-sm"
                  onClick={() => { setChatHistory([]); setAiMd(initialMd || ""); setChatInput("") }}
                  disabled={evaluating || chatHistory.length === 0}
                  title="Chat-History loeschen"
                >
                  🔄 Reset
                </button>
              </div>
            </div>

            {/* Modell-Selector + AI-Helper (UNTER dem Chat-Input) */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", paddingTop: 4, borderTop: "1px dashed var(--color-hermes-border)" }}>
              <label style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>🪄 Modell:</label>
              <select
                className="input"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                style={{ fontSize: 10, padding: "1px 4px", flex: 1, minWidth: 150 }}
                disabled={evaluating}
              >
                <option value="minimax-direct/minimax-m3">minimax-direct/minimax-m3 (Standard, Cloud)</option>
                <option value="ollama/gemma3:4b">ollama/gemma3:4b (lokal, schnell)</option>
                <option value="ollama/qwen3.6:27b">ollama/qwen3.6:27b (lokal, 27B)</option>
                <option value="ollama/gemma4:12b">ollama/gemma4:12b (lokal, 12B)</option>
                <option value="ollama/qwen3.6:latest">ollama/qwen3.6:latest</option>
                <option value="ollama/pi-subagent:latest">ollama/pi-subagent:latest</option>
              </select>
            </div>
          </div>

          {/* RECHTS: MD-Live-Vorschau */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: 12, gap: 8, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, flex: 1 }}>
                📝 Live-Vorschau (Markdown)
              </div>
              {/* === TTS-Button (User-Direktive 16.06.2026) === */}
              {ttsEnabled && (
                isSpeakingAiMd ? (
                  <button
                    className="btn btn-sm"
                    onClick={stopTts}
                    title="Vorlesen stoppen (Esc)"
                    style={{
                      fontSize: 10, padding: "1px 8px",
                      background: "rgba(248,81,73,0.15)",
                      color: "var(--color-hermes-danger)",
                      borderColor: "var(--color-hermes-danger)",
                      fontWeight: 600,
                    }}
                  >
                    <VolumeX size={11} /> ⏹ Stop
                  </button>
                ) : (
                  <button
                    className="btn btn-sm"
                    onClick={startTtsFromCursor}
                    disabled={!aiMd.trim()}
                    title={showPreview
                      ? "Liest den gesamten Text vor (Preview-Modus: keine echte Cursor-Position)"
                      : "Liest ab aktueller Cursor-Position bis Dokumentende vor"
                    }
                    style={{
                      fontSize: 10, padding: "1px 8px",
                      background: "linear-gradient(135deg, rgba(88,166,255,0.15) 0%, rgba(163,113,247,0.15) 100%)",
                      color: "var(--color-hermes-accent-blue)",
                      borderColor: "var(--color-hermes-accent-blue)",
                      fontWeight: 600,
                    }}
                  >
                    <Volume2 size={11} /> 🔊 Vorlesen (ab Cursor)
                  </button>
                )
              )}
              <button
                className={`btn btn-sm ${showPreview ? "btn-primary" : ""}`}
                onClick={() => setShowPreview(!showPreview)}
                style={{ fontSize: 10, padding: "1px 8px" }}
              >
                {showPreview ? "Editor" : "Vorschau"}
              </button>
            </div>
            {showPreview && aiMd.trim() && (
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: -4, marginBottom: 4, fontStyle: "italic" }}>
                💡 Tipp: Wechsle in den <strong>Editor-Modus</strong> und klicke irgendwo in den Text, um nur ab dieser Position vorzulesen.
              </div>
            )}
            {showPreview ? (
              aiMd ? (
                <div
                  style={{
                    flex: 1, overflow: "auto", padding: 12,
                    background: "var(--color-hermes-bg)", border: "1px solid var(--color-hermes-border)",
                    borderRadius: 4, fontSize: 12, lineHeight: 1.6,
                  }}
                >
                  <ReactMarkdown components={mdComponents}>{aiMd}</ReactMarkdown>
                </div>
              ) : (
                <div style={{
                  flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
                  color: "var(--color-hermes-text-secondary)", fontSize: 12, textAlign: "center",
                  border: "1px dashed var(--color-hermes-border)", borderRadius: 4,
                }}>
                  <div>
                    <div style={{ fontSize: 36, opacity: 0.3 }}>📋</div>
                    <p>Noch keine KI-Anweisung generiert.</p>
                    <p style={{ fontSize: 11 }}>Schicke einen Satz im Chat links.</p>
                  </div>
                </div>
              )
            ) : (
              <textarea
                ref={editorRef}
                value={aiMd}
                onChange={(e) => {
                  setAiMd(e.target.value)
                  // Cursor-Position bei jeder Aenderung merken
                  setTtsCursor(e.target.selectionStart ?? 0)
                }}
                onSelect={(e) => {
                  // Cursor-Position bei Selektion merken
                  const target = e.target as HTMLTextAreaElement
                  setTtsCursor(target.selectionStart ?? 0)
                }}
                onKeyUp={(e) => {
                  // Cursor-Position nach Pfeiltasten etc. merken
                  const target = e.target as HTMLTextAreaElement
                  setTtsCursor(target.selectionStart ?? 0)
                }}
                onClick={(e) => {
                  // Cursor-Position nach Klick merken
                  const target = e.target as HTMLTextAreaElement
                  setTtsCursor(target.selectionStart ?? 0)
                }}
                placeholder="// KI-Output erscheint hier. Du kannst den Text manuell nachbearbeiten."
                style={{
                  flex: 1, padding: 10, fontSize: 12, lineHeight: 1.5,
                  fontFamily: "var(--font-mono)", resize: "none",
                  background: "var(--color-hermes-bg)", color: "var(--color-hermes-text)",
                  border: `1px solid ${isSpeakingAiMd ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-border)"}`,
                  borderRadius: 4,
                  transition: "border-color 0.15s",
                }}
              />
            )}
            {/* TTS-Status unter dem Editor (auch im Preview-Modus sichtbar) */}
            {isSpeakingAiMd && (
              <div style={{ fontSize: 10, color: "var(--color-hermes-accent-blue)", textAlign: "center", marginTop: 4 }}>
                🔊 Wird vorgelesen ab Zeichen-Position {ttsCursor} …
              </div>
            )}
            {/* Action-Buttons */}
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <button
                className="btn btn-sm"
                onClick={() => navigator.clipboard.writeText(aiMd)}
                disabled={!aiMd}
                title="MD-Text in Zwischenablage kopieren"
              >
                📋 Kopieren
              </button>
              <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                {aiMd ? `${aiMd.length} Zeichen` : "leer"}
              </span>
              <div style={{ flex: 1 }} />
              <button className="btn btn-sm" onClick={onClose}>Abbrechen</button>
              <button
                className="btn btn-sm btn-primary"
                onClick={onApplyAndSave}
                disabled={!aiMd || saving}
                title="MD-Text dauerhaft in der DB speichern"
                style={{ fontWeight: 600 }}
              >
                {saving ? "💾 Speichere..." : "✅ Übernehmen & Speichern"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────── UML-View (Diagramm links + Schritt-Auswahl + Beschreibung rechts) ───────────────
function UmlView({ sopId }: { sopId: string }) {
  const { data: umlData, isLoading: umlLoading } = useQuery({
    queryKey: ["sop-uml", sopId],
    queryFn: () => api.getSopUml(sopId),
  })
  const { data: sop } = useQuery({
    queryKey: ["sop", sopId],
    queryFn: () => api.getSop(sopId),
  })
  const source = (umlData as any)?.source || ""
  const [showSource, setShowSource] = useState(false)
  const [selectedStepIdx, setSelectedStepIdx] = useState<number>(0)

  if (umlLoading) return <div>Lade UML…</div>
  if (!source) return <div>Keine UML-Quelle vorhanden.</div>

  const steps: any[] = sop?.steps || []
  const selectedStep = steps[selectedStepIdx] || null

  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <ImageIcon size={16} color="var(--color-hermes-accent-blue)" />
        <h3 style={{ margin: 0, fontSize: 14 }}>UML Sequenzdiagramm</h3>
        <span className="badge badge-blue" style={{ fontSize: 10 }}>beautiful-plantuml</span>
        <div style={{ flex: 1 }} />
        <button
          className={`btn btn-sm ${showSource ? "btn-primary" : ""}`}
          onClick={() => setShowSource(!showSource)}
        >
          {showSource ? "Diagramm" : "Quellcode"} anzeigen
        </button>
      </div>
      <p style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", margin: "0 0 8px" }}>
        Auto-generiert aus der SOP-Definition · Format: <code>{(umlData as any)?.format}</code>
        · Klicke einen <strong>Schritt</strong> unten an, um die Detail-Beschreibung zu sehen
      </p>

      {showSource ? (
        <pre style={{
          background: "var(--color-hermes-bg-secondary)",
          padding: 12, fontSize: 11, maxHeight: 600, overflow: "auto", borderRadius: 4,
          fontFamily: "var(--font-mono)"
        }}>
          {source}
        </pre>
      ) : (
        <div>
          {/* DIAGRAMM */}
          <div style={{
            background: "#ffffff",
            border: "1px solid var(--color-hermes-border)",
            borderRadius: 6,
            padding: 8,
            minHeight: 320,
            overflow: "auto",
            marginBottom: 12,
          }}>
            <DiagramProvider code={source} theme="zinc-dark">
              <SequenceDiagram
                enableHoverLayer={false}
                enableDragLayer={false}
              />
            </DiagramProvider>
          </div>

          {/* SCHRITT-AUSWAHL */}
          <div style={{
            display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12,
            padding: 8, background: "var(--color-hermes-bg-secondary)",
            border: "1px solid var(--color-hermes-border)", borderRadius: 6,
          }}>
            <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", alignSelf: "center", marginRight: 4 }}>
              Schritt wählen:
            </span>
            {steps.map((s: any, i: number) => (
              <button
                key={s.id}
                className={`btn btn-sm ${selectedStepIdx === i ? "btn-primary" : ""}`}
                onClick={() => setSelectedStepIdx(i)}
                style={{ fontSize: 11 }}
                title={s.name}
              >
                <span style={{
                  display: "inline-block", width: 18, height: 18, lineHeight: "18px",
                  borderRadius: 9, background: selectedStepIdx === i ? "#fff" : "var(--color-hermes-accent-blue)",
                  color: selectedStepIdx === i ? "var(--color-hermes-accent-blue)" : "#fff",
                  fontSize: 10, fontWeight: 600, marginRight: 4,
                }}>
                  {i + 1}
                </span>
                {s.name.length > 28 ? s.name.slice(0, 26) + "…" : s.name}
              </button>
            ))}
          </div>

          {/* LINKS: Schritt-Beschreibung (rechts vom Diagramm gewünscht, aber responsiv untereinander) */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 12, alignItems: "start" }}>
            <div style={{
              padding: 10,
              background: "var(--color-hermes-bg-secondary)",
              border: "1px solid var(--color-hermes-border)",
              borderRadius: 6,
              fontSize: 12,
            }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, color: "var(--color-hermes-accent)" }}>
                📋 Prozess: {sop?.name}
              </div>
              <p style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", margin: 0 }}>
                {sop?.description?.slice(0, 250) || "Schritt-für-Schritt-Beschreibung des Prozesses."}
              </p>
              <div style={{ marginTop: 10, fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                <strong>{steps.length} Schritte</strong> · Klicke einen Schritt oben an, um Details zu sehen.
              </div>
            </div>
            <UmlDescription step={selectedStep} stepIdx={selectedStepIdx} totalSteps={steps.length} />
          </div>
        </div>
      )}
      <div style={{ marginTop: 8, fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
        💡 Bedienung: Mausrad = Zoom im Diagramm · Klick + Ziehen = Pan · Schritt-Buttons wählen die Detail-Beschreibung
      </div>
    </div>
  )
}

// ─────────────── Schritt-Detail-Beschreibung (zeigt NUR den ausgewählten Schritt) ───────────────
function UmlDescription({ step, stepIdx, totalSteps }: { step: any; stepIdx: number; totalSteps: number }) {
  if (!step) {
    return (
      <div className="card" style={{
        padding: 12, fontSize: 12,
        color: "var(--color-hermes-text-secondary)",
        background: "var(--color-hermes-bg-secondary)",
      }}>
        Keine SOP-Details verfügbar.
      </div>
    )
  }
  const rules = step.rules || []
  return (
    <div style={{
      background: "var(--color-hermes-bg-secondary)",
      border: "2px solid var(--color-hermes-accent)",
      borderRadius: 6,
      padding: 12,
      fontSize: 12,
      width: "100%",
      maxWidth: "100%",
      boxSizing: "border-box",
    }}>
      {/* Header: Step-Name + Counter */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8, marginBottom: 10,
        paddingBottom: 8, borderBottom: "1px solid var(--color-hermes-border)",
      }}>
        <span style={{
          background: "var(--color-hermes-accent)",
          color: "#000", borderRadius: 12, padding: "2px 10px",
          fontSize: 11, fontWeight: 700,
        }}>
          Step {stepIdx + 1} / {totalSteps}
        </span>
        <strong style={{ fontSize: 14, color: "var(--color-hermes-text)" }}>{step.name}</strong>
      </div>

      {/* Phase */}
      <div style={{ marginBottom: 8 }}>
        <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 2 }}>PHASE</div>
        <span style={{
          display: "inline-block", padding: "2px 8px", borderRadius: 4,
          background: step.phase === "End" ? "var(--color-hermes-accent)" :
                      step.phase === "Sub-SOP" ? "var(--color-hermes-accent-orange)" :
                      "var(--color-hermes-accent-blue)",
          color: "#fff", fontSize: 11, fontWeight: 600,
        }}>{step.phase}</span>
      </div>

      {/* Was passiert: ausführliche Beschreibung */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 2 }}>WAS PASSIERT</div>
        <div style={{ fontSize: 12, lineHeight: 1.5 }}>
          {step.description ? (
            <span>{step.description}</span>
          ) : (
            <span style={{ color: "var(--color-hermes-text-secondary)" }}>—</span>
          )}
        </div>
      </div>

      {/* Trigger → Action → Agent → Expected Result */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>DETAILS</div>
        <div style={{ display: "grid", gridTemplateColumns: "70px 1fr", gap: "4px 8px", fontSize: 11 }}>
          <span style={{ color: "var(--color-hermes-text-secondary)" }}>Trigger:</span>
          <span><code style={{ wordBreak: "break-all" }}>{step.trigger || "—"}</code></span>

          <span style={{ color: "var(--color-hermes-text-secondary)" }}>Action:</span>
          <span><code>{step.action || "—"}</code></span>

          <span style={{ color: "var(--color-hermes-text-secondary)" }}>Agent:</span>
          <span><code>{step.agent || "—"}</code></span>

          <span style={{ color: "var(--color-hermes-text-secondary)" }}>Delay:</span>
          <span><strong style={{ color: "var(--color-hermes-accent)" }}>⏱ {step.delay_s}s</strong></span>

          {step.expected_result && (
            <>
              <span style={{ color: "var(--color-hermes-text-secondary)" }}>Erwartet:</span>
              <span>{step.expected_result}</span>
            </>
          )}
        </div>
      </div>

      {/* Wenn-Dann-Regeln */}
      {rules.length > 0 && (
        <div>
          <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
            WENN-DANN-REGELN ({rules.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {rules.map((r: any, idx: number) => (
              <div key={r.id || idx} style={{
                padding: 8, borderRadius: 4,
                background: "var(--color-hermes-surface)",
                border: "1px solid var(--color-hermes-border)",
                fontSize: 11,
              }}>
                <div style={{ fontFamily: "var(--font-mono)" }}>
                  <span style={{ color: "var(--color-hermes-accent-orange)" }}>if</span>{" "}
                  <strong>{r.condition_field}</strong>{" "}
                  <span style={{ color: "var(--color-hermes-text-secondary)" }}>{r.condition_operator}</span>{" "}
                  <strong>{JSON.stringify(r.condition_value)}</strong>
                </div>
                <div style={{ fontFamily: "var(--font-mono)", marginTop: 2 }}>
                  <span style={{ color: "var(--color-hermes-accent)" }}>→ then</span>{" "}
                  <strong>{r.action_type}</strong>(
                  <span style={{ color: "var(--color-hermes-accent)" }}>{r.action_target || "—"}</span>)
                </div>
                {r.description && (
                  <div style={{
                    marginTop: 4, paddingTop: 4, borderTop: "1px dashed var(--color-hermes-border)",
                    fontSize: 10, color: "var(--color-hermes-text-secondary)", fontStyle: "italic",
                    fontFamily: "inherit",
                  }}>
                    💬 {r.description}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Success Criteria */}
      {step.success_criteria && step.success_criteria.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
            ERFOLGSKRITERIEN
          </div>
          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11 }}>
            {step.success_criteria.map((sc: any, i: number) => (
              <li key={i} style={{ marginBottom: 2 }}>
                {typeof sc === "string" ? sc : sc.text || JSON.stringify(sc)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* === CIO-Triage-Felder (User-Direktive 16.06.2026, Schritt 0) === */}
      {step.task_types && step.task_types.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
            🏷️ TASK-TYP-KLASSIFIZIERUNG ({step.task_types.length})
          </div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {step.task_types.map((t: string, i: number) => (
              <span key={i} className="badge badge-blue" style={{ fontSize: 10 }}>{t}</span>
            ))}
          </div>
          <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)", marginTop: 4, fontStyle: "italic" }}>
            CIO klassifiziert den Task in einen dieser Typen
          </div>
        </div>
      )}

      {step.standards_refs && step.standards_refs.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
            📜 STANDARDVORGABEN-PRÜFUNG ({step.standards_refs.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11 }}>
            {step.standards_refs.map((ref: string, i: number) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span className="badge badge-orange" style={{ fontSize: 9 }}>{ref}</span>
                <span style={{ color: "var(--color-hermes-text-secondary)", fontSize: 10 }}>
                  OpenBrain-Referenz
                </span>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)", marginTop: 4, fontStyle: "italic" }}>
            CIO prüft Konformität mit den geladenen Standardvorgaben
          </div>
        </div>
      )}

      {step.change_requirements && step.change_requirements.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
            🛠️ ÄNDERUNGSBESCHREIBUNG — ERFORDERLICH ({step.change_requirements.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11 }}>
            {step.change_requirements.map((cr: any, i: number) => (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
                <span style={{ color: cr.required ? "var(--color-hermes-danger)" : "var(--color-hermes-text-secondary)", fontSize: 11 }}>
                  {cr.required ? "✗" : "○"}
                </span>
                <div style={{ flex: 1 }}>
                  <code style={{ fontSize: 10, color: "var(--color-hermes-accent-blue)" }}>{cr.field}</code>
                  {cr.description && (
                    <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 1 }}>
                      {cr.description}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {step.subagent_requirements && step.subagent_requirements.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
            🤖 SUBAGENT-READINESS ({step.subagent_requirements.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11 }}>
            {step.subagent_requirements.map((sr: any, i: number) => (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
                <span style={{ color: sr.required ? "var(--color-hermes-danger)" : "var(--color-hermes-text-secondary)", fontSize: 11 }}>
                  {sr.required ? "✗" : "○"}
                </span>
                <div style={{ flex: 1 }}>
                  <code style={{ fontSize: 10, color: "var(--color-hermes-accent-orange)" }}>{sr.name}</code>
                  {sr.description && (
                    <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 1 }}>
                      {sr.description}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─────────────── SOP-Builder (Wizard) ───────────────
function SopBuilder({ onCreated, onCancel }: { onCreated: (sop: any) => void; onCancel: () => void }) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [category, setCategory] = useState("task")
  const [defaultDelay, setDefaultDelay] = useState(5.0)
  const [steps, setSteps] = useState<any[]>([makeEmptyStep(0)])

  const createMut = useMutation({
    mutationFn: () => api.createSop({
      name, description, category, default_delay_s: defaultDelay,
      steps: steps.map((s, i) => ({
        ...s,
        next_step: i + 1 < steps.length ? i + 1 : null,
        fail_step: null,
      })),
    }),
    onSuccess: (sop: any) => onCreated(sop),
  })

  return (
    <div>
      <div className="page-header">
        <div className="workspace-header">
          <button className="btn btn-sm" onClick={onCancel} style={{ padding: "0 6px" }} title="Abbrechen">
            <ArrowLeft size={14} />
          </button>
          <Plus size={20} color="var(--color-hermes-accent-blue)" />
          <h1>SOP</h1>
          <span className="workspace-breadcrumb">/ Neue SOP</span>
        </div>
        <p>Erstellt eine neue Standard Operating Procedure mit Steps und Wenn-Dann-Regeln.</p>
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>📋 SOP-Definition</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <input className="input" placeholder="SOP-Name" value={name} onChange={(e) => setName(e.target.value)} />
          <select className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="task">task</option>
            <option value="review">review</option>
            <option value="release">release</option>
            <option value="incident">incident</option>
            <option value="custom">custom</option>
          </select>
        </div>
        <textarea className="input mt-2" placeholder="Beschreibung der SOP..." value={description} onChange={(e) => setDescription(e.target.value)} style={{ minHeight: 60 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
          <span style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>Default-Delay:</span>
          <input type="number" className="input" value={defaultDelay} onChange={(e) => setDefaultDelay(Number(e.target.value))} style={{ width: 80 }} step={0.5} min={0} max={60} />
          <span style={{ fontSize: 12 }}>Sekunden</span>
        </div>
      </div>

      <h3 style={{ fontSize: 14, margin: "12px 0 8px" }}>Steps ({steps.length})</h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {steps.map((s, i) => (
          <StepEditor
            key={i}
            step={s}
            index={i}
            onChange={(updated: any) => {
              const ns = [...steps]
              ns[i] = updated
              setSteps(ns)
            }}
            onRemove={() => setSteps(steps.filter((_, idx) => idx !== i))}
          />
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button className="btn btn-sm" onClick={() => setSteps([...steps, makeEmptyStep(steps.length)])}>
          <Plus size={12} /> Step hinzufügen
        </button>
        <div style={{ flex: 1 }} />
        <button className="btn" onClick={onCancel}>
          <X size={12} /> Abbrechen
        </button>
        <button className="btn btn-primary" onClick={() => createMut.mutate()} disabled={!name || createMut.isPending}>
          {createMut.isPending ? "Erstelle…" : "SOP erstellen"}
        </button>
      </div>
    </div>
  )
}

function makeEmptyStep(order: number) {
  return {
    name: `Step ${order + 1}`,
    phase: "Task",
    trigger: "manual",
    action: "noop",
    action_params: {},
    agent: "system",
    model: "minimax-direct/minimax-m3",
    expected_result: "",
    success_criteria: [],
    delay_s: 5.0,
    description: "",
    rules: [],
  }
}

function StepEditor({ step, index, onChange, onRemove }: any) {
  const [showRules, setShowRules] = useState(false)
  return (
    <div className="card" style={{ borderLeft: "3px solid var(--color-hermes-accent)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
        <span className="badge badge-orange">#{index + 1}</span>
        <input className="input" value={step.name} onChange={(e) => onChange({ ...step, name: e.target.value })} placeholder="Step-Name" style={{ flex: 1 }} />
        <select className="select" value={step.phase} onChange={(e) => onChange({ ...step, phase: e.target.value })} style={{ width: 120 }}>
          <option>Task</option>
          <option>Decision</option>
          <option>Sub-SOP</option>
          <option>End</option>
          <option>Wait</option>
          <option>Notification</option>
        </select>
        <AgentSelect value={step.agent} onChange={(agent) => onChange({ ...step, agent })} style={{ width: 140 }} />
        <AgentModelDisplay agent={step.agent} style={{ width: 200 }} />
        <button className="btn btn-sm" onClick={onRemove}><X size={12} /></button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 100px", gap: 6, marginBottom: 6 }}>
        <input className="input" value={step.trigger} onChange={(e) => onChange({ ...step, trigger: e.target.value })} placeholder="Trigger (z.B. status_changed:todo)" />
        <input className="input" value={step.action} onChange={(e) => onChange({ ...step, action: e.target.value })} placeholder="Action (z.B. move_status)" />
        <input type="number" className="input" value={step.delay_s} onChange={(e) => onChange({ ...step, delay_s: Number(e.target.value) })} placeholder="Delay" step={0.5} min={0} max={60} />
      </div>
      <textarea className="input" value={step.expected_result} onChange={(e) => onChange({ ...step, expected_result: e.target.value })} placeholder="Erwartetes Ergebnis..." style={{ minHeight: 30, fontSize: 11 }} />

      {/* === Acceptance Criteria (User-Direktive 18.06.2026) === */}
      <div style={{ marginTop: 6, padding: 6, background: "rgba(124, 58, 237, 0.05)", borderRadius: 4, border: "1px solid rgba(124, 58, 237, 0.2)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#7c3aed" }}>
            ✅ Acceptance Criteria ({(step.action_params?.acceptance_criteria || []).length})
          </div>
          <button
            className="btn btn-sm"
            onClick={() => {
              const criteria = step.action_params?.acceptance_criteria || [];
              onChange({ ...step, action_params: { ...step.action_params, acceptance_criteria: [...criteria, ""] } });
            }}
            style={{ fontSize: 10, padding: "2px 6px" }}
          >
            + Kriterium
          </button>
        </div>
        {(step.action_params?.acceptance_criteria || []).map((crit: string, ci: number) => (
          <div key={ci} style={{ display: "flex", gap: 4, marginBottom: 4 }}>
            <input
              className="input"
              value={crit}
              onChange={(e) => {
                const arr = [...(step.action_params?.acceptance_criteria || [])];
                arr[ci] = e.target.value;
                onChange({ ...step, action_params: { ...step.action_params, acceptance_criteria: arr } });
              }}
              placeholder="z.B. test_coverage >= 80"
              style={{ flex: 1, fontSize: 11 }}
            />
            <button
              className="btn btn-sm"
              onClick={() => {
                const arr = (step.action_params?.acceptance_criteria || []).filter((_: any, i: number) => i !== ci);
                onChange({ ...step, action_params: { ...step.action_params, acceptance_criteria: arr } });
              }}
              style={{ fontSize: 10, padding: "2px 6px", color: "var(--color-hermes-danger)" }}
            >
              ×
            </button>
          </div>
        ))}
        {(step.action_params?.acceptance_criteria || []).length === 0 && (
          <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", fontStyle: "italic" }}>
            Keine Kriterien. Klicke "+ Kriterium" um eines hinzuzufügen.
          </div>
        )}
      </div>

      <div style={{ marginTop: 6 }}>
        <button className="btn btn-sm" onClick={() => setShowRules(!showRules)}>
          <GitBranch size={12} /> Rules ({step.rules?.length || 0}) {showRules ? "▼" : "▶"}
        </button>
      </div>
      {showRules && (
        <div style={{ marginTop: 6, paddingTop: 6, borderTop: "1px solid var(--color-hermes-border)" }}>
          {(step.rules || []).map((r: any, ri: number) => (
            <div key={ri} style={{ display: "grid", gridTemplateColumns: "1fr 80px 1fr 1fr 1fr 30px", gap: 4, marginBottom: 4, fontSize: 11 }}>
              <input className="input" value={r.condition_field || ""} onChange={(e) => {
                const nr = [...step.rules]; nr[ri] = { ...r, condition_field: e.target.value }; onChange({ ...step, rules: nr })
              }} placeholder="condition_field" />
              <select className="select" value={r.condition_operator || "eq"} onChange={(e) => {
                const nr = [...step.rules]; nr[ri] = { ...r, condition_operator: e.target.value }; onChange({ ...step, rules: nr })
              }}>
                <option>eq</option><option>ne</option><option>gt</option><option>lt</option>
                <option>in</option><option>not_in</option><option>contains</option>
                <option>is_true</option><option>is_false</option>
              </select>
              <input className="input" value={JSON.stringify(r.condition_value) || ""} onChange={(e) => {
                try { const nr = [...step.rules]; nr[ri] = { ...r, condition_value: JSON.parse(e.target.value) }; onChange({ ...step, rules: nr }) } catch {}
              }} placeholder="condition_value (JSON)" />
              <input className="input" value={r.action_type || ""} onChange={(e) => {
                const nr = [...step.rules]; nr[ri] = { ...r, action_type: e.target.value }; onChange({ ...step, rules: nr })
              }} placeholder="action_type" />
              <input className="input" value={r.action_target || ""} onChange={(e) => {
                const nr = [...step.rules]; nr[ri] = { ...r, action_target: e.target.value }; onChange({ ...step, rules: nr })
              }} placeholder="action_target" />
              <button className="btn btn-sm" onClick={() => {
                const nr = step.rules.filter((_: any, idx: number) => idx !== ri); onChange({ ...step, rules: nr })
              }}><X size={10} /></button>
            </div>
          ))}
          <button className="btn btn-sm" onClick={() => onChange({ ...step, rules: [...(step.rules || []), { condition_field: "step_ok", condition_operator: "is_true", condition_value: true, action_type: "approve_triage", action_target: "todo" }] })}>
            <Plus size={10} /> Rule
          </button>
        </div>
      )}
    </div>
  )
}

// ─────────────── Helpers ───────────────
function statusColor(status: string): string {
  if (status === "completed") return "var(--color-hermes-accent)"
  if (status === "failed") return "var(--color-hermes-danger)"
  if (status === "running") return "var(--color-hermes-accent-blue)"
  if (status === "waiting_sub_sop") return "var(--color-hermes-accent-orange)"
  return "var(--color-hermes-text-secondary)"
}

// ─────────────── Editierbare Description (User-Direktive 16.06.2026) ───────────────
function EditableDescription({
  sopId, stepId, step, description, expectedResult,
}: {
  sopId: string
  stepId: string
  step?: any
  description?: string
  expectedResult?: string
}) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState("")
  const [which, setWhich] = useState<"description" | "expected_result">("description")
  const [saving, setSaving] = useState(false)

  // Welcher Text wird angezeigt (Prioritaet: description > expected_result)
  const currentText = (description || expectedResult || "").trim()
  const isEmpty = !currentText

  function startEdit(field: "description" | "expected_result") {
    setWhich(field)
    setDraft(field === "description" ? (description || "") : (expectedResult || ""))
    setEditing(true)
  }

  // === AI-Prompt-Helper (User-Direktive 16.06.2026) ===
  // Oeffnet das AI-Helper-Modal. User beschreibt in einfacher Sprache, was im
  // Schritt gemacht werden soll. KI generiert daraus die optimale Description +
  // Expected Result. User kann anschliessend verfeinern oder speichern.
  const [showAiHelper, setShowAiHelper] = useState(false)
  const [aiDraft, setAiDraft] = useState<{ description: string; expected_result: string } | null>(null)

  function startEditWithAi(field: "description" | "expected_result") {
    setWhich(field)
    setAiDraft({
      description: description || "",
      expected_result: expectedResult || "",
    })
    setShowAiHelper(true)
  }

  function cancelAiHelper() {
    setShowAiHelper(false)
    setAiDraft(null)
  }

  function applyAiResult(result: { description: string; expected_result: string }) {
    setAiDraft(result)
  }

  async function saveAiResult() {
    if (!aiDraft) return
    setSaving(true)
    try {
      await api.updateSopStep(sopId, stepId, aiDraft)
      qc.invalidateQueries({ queryKey: ["sop", sopId] })
      qc.invalidateQueries({ queryKey: ["sop-uml", sopId] })
      qc.invalidateQueries({ queryKey: ["sop-bpmn", sopId] })
      setShowAiHelper(false)
      setAiDraft(null)
    } catch (e) {
      console.error("Save fehlgeschlagen:", e)
      alert("Speichern fehlgeschlagen: " + (e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  function cancelEdit() {
    setEditing(false)
    setDraft("")
  }

  async function saveEdit() {
    setSaving(true)
    try {
      await api.updateSopStep(sopId, stepId, { [which]: draft })
      qc.invalidateQueries({ queryKey: ["sop", sopId] })
      qc.invalidateQueries({ queryKey: ["sop-uml", sopId] })
      qc.invalidateQueries({ queryKey: ["sop-bpmn", sopId] })
      setEditing(false)
      setDraft("")
    } catch (e) {
      console.error("Save fehlgeschlagen:", e)
      alert("Speichern fehlgeschlagen: " + (e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div style={{
        display: "flex", alignItems: "center", gap: 6, marginBottom: 4,
      }}>
        <div style={{
          fontSize: 10, color: "var(--color-hermes-text-secondary)",
          textTransform: "uppercase", letterSpacing: 0.5, flex: 1,
        }}>
          Was passiert hier?
        </div>
        {!editing && currentText && (
          <>
            <SpeakButton
              text={currentText}
              label="Beschreibung vorlesen"
              showLabel={false}
            />
            <button
              className="btn btn-sm"
              onClick={() => startEdit(description ? "description" : "expected_result")}
              style={{ padding: "1px 6px", fontSize: 10 }}
              title="Text bearbeiten (wird im BPMN/UML angezeigt)"
            >
              ✏ Bearbeiten
            </button>
            <button
              className="btn btn-sm btn-primary"
              onClick={() => startEditWithAi(description ? "description" : "expected_result")}
              style={{ padding: "1px 8px", fontSize: 10 }}
              title="KI-Helper: User-Notiz in einfachem Deutsch eingeben, KI generiert die optimale Description"
            >
              🤖 AI-Helper
            </button>
          </>
        )}
        {!editing && isEmpty && (
          <button
            className="btn btn-sm"
            onClick={() => startEdit("description")}
            style={{ padding: "1px 6px", fontSize: 10 }}
            title="Beschreibung hinzufuegen"
          >
            + Hinzufuegen
          </button>
        )}
      </div>

      {editing ? (
        <div style={{
          padding: 8, background: "var(--color-hermes-muted)",
          border: "1px solid var(--color-hermes-accent-blue)", borderRadius: 4,
          display: "flex", flexDirection: "column", width: "100%",
        }}>
          <div style={{ display: "flex", gap: 4, marginBottom: 4, fontSize: 10, flexWrap: "wrap" }}>
            <button
              className={`btn btn-sm ${which === "description" ? "btn-primary" : ""}`}
              onClick={() => setWhich("description")}
              style={{ fontSize: 10, padding: "1px 8px" }}
            >
              Was passiert hier?
            </button>
            <button
              className={`btn btn-sm ${which === "expected_result" ? "btn-primary" : ""}`}
              onClick={() => setWhich("expected_result")}
              style={{ fontSize: 10, padding: "1px 8px" }}
            >
              Erwartet
            </button>
          </div>
          <textarea
            className="input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={which === "description" ? "Was passiert in diesem Schritt?" : "Was ist das erwartete Ergebnis?"}
            style={{
              minHeight: 80,
              width: "100%",
              maxWidth: "100%",
              boxSizing: "border-box",
              resize: "vertical",
              fontSize: 12,
              lineHeight: 1.5,
              marginBottom: 6,
              fontFamily: "inherit",
            }}
            autoFocus
          />
          <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
            <button
              className="btn btn-primary btn-sm"
              onClick={saveEdit}
              disabled={saving}
              style={{ fontSize: 11 }}
            >
              {saving ? "Speichert..." : "💾 Speichern"}
            </button>
            <button
              className="btn btn-sm"
              onClick={cancelEdit}
              disabled={saving}
              style={{ fontSize: 11 }}
            >
              Abbrechen
            </button>
            <div style={{ flex: 1, minWidth: 8 }} />
            <SpeakButton
              text={draft || "(leer)"}
              label="Vorschau vorlesen"
              showLabel={false}
            />
            <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", whiteSpace: "nowrap" }}>
              {draft.length} Zeichen
            </span>
          </div>
        </div>
      ) : currentText ? (
        <p style={{
          fontSize: 12, lineHeight: 1.5, margin: 0,
          color: "var(--color-hermes-text)",
          whiteSpace: "pre-wrap",
        }}>
          {currentText}
        </p>
      ) : (
        <p style={{
          fontSize: 12, fontStyle: "italic",
          color: "var(--color-hermes-text-secondary)", margin: 0,
        }}>
          Keine Beschreibung vorhanden. Klicke „+ Hinzufügen“ um eine zu erstellen.
        </p>
      )}

      {/* === AI-Prompt-Helper-Modal (User-Direktive 16.06.2026) === */}
      {showAiHelper && (
        <AiPromptHelperModal
          sopId={sopId}
          stepId={stepId}
          which={which}
          initialDraft={aiDraft!}
          stepName={step?.name}
          agent={step?.agent}
          onApply={applyAiResult}
          onClose={cancelAiHelper}
          onSave={saveAiResult}
          saving={saving}
        />
      )}
    </div>
  )
}

// ─────────────── AI-Prompt-Helper-Modal ───────────────
// User-Direktive 16.06.2026: Modal mit KI-Optimierung der Description.
// User gibt grobe Notiz ein, KI macht daraus eine praezise Description + Expected Result.
function AiPromptHelperModal({
  sopId, stepId, which, initialDraft, stepName, agent,
  onApply, onClose, onSave, saving,
}: {
  sopId: string
  stepId: string
  which: "description" | "expected_result"
  initialDraft: { description: string; expected_result: string }
  stepName?: string
  agent?: string
  onApply: (r: { description: string; expected_result: string }) => void
  onClose: () => void
  onSave: () => Promise<void>
  saving: boolean
}) {
  const [userInput, setUserInput] = useState("")
  const [aiResult, setAiResult] = useState<{ description: string; expected_result: string; questions: string[]; suggestions: string[] } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editingAi, setEditingAi] = useState(false)
  const [editedDescription, setEditedDescription] = useState("")
  const [editedExpected, setEditedExpected] = useState("")

  async function runAi() {
    if (!userInput.trim() || userInput.trim().length < 5) {
      setError("Bitte mind. 5 Zeichen Beschreibung eingeben.")
      return
    }
    setLoading(true)
    setError(null)
    try {
      const result = await api.aiStepHelper(sopId, stepId, userInput)
      if (result.ok) {
        setAiResult({
          description: result.description || "",
          expected_result: result.expected_result || "",
          questions: result.questions || [],
          suggestions: result.suggestions || [],
        })
        setEditedDescription(result.description || "")
        setEditedExpected(result.expected_result || "")
        onApply({
          description: result.description || "",
          expected_result: result.expected_result || "",
        })
      } else {
        setError("KI-Aufruf fehlgeschlagen (kein 'ok'-Feld)")
      }
    } catch (e) {
      setError("KI-Fehler: " + (e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  function applyEdits() {
    onApply({
      description: editedDescription,
      expected_result: editedExpected,
    })
    setEditingAi(false)
  }

  return (
    <div
      className="modal-backdrop"
      onClick={onClose}
      style={{ zIndex: 1000 }}
    >
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: 720,
          width: "90%",
          maxHeight: "85vh",
          overflowY: "auto",
          padding: 20,
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 24 }}>🤖</span>
          <h3 style={{ margin: 0, fontSize: 16, flex: 1 }}>AI-Prompt-Helper</h3>
          <button className="btn btn-sm" onClick={onClose} title="Schliessen">
            <X size={12} />
          </button>
        </div>
        <p style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", margin: "0 0 12px" }}>
          Beschreibe in einfacher Sprache, was in diesem Arbeitsschritt gemacht werden soll.
          Die KI ergaenzt deine Notiz zu einer optimalen, praezisen Beschreibung, die ein Worker-Agent direkt umsetzen kann.
        </p>

        {/* Kontext */}
        <div style={{
          padding: 8, marginBottom: 10, fontSize: 11,
          background: "var(--color-hermes-muted)", borderRadius: 4,
          border: "1px solid var(--color-hermes-border)",
        }}>
          <strong>Kontext:</strong> {stepName || "?"} · {which === "description" ? "Was passiert hier?" : "Erwartetes Ergebnis"} · Agent: {agent || "?"}
        </div>

        {/* User-Input */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
            Deine Notiz (einfache Sprache)
          </div>
          <textarea
            className="input"
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            placeholder="z.B. 'Der CIO soll den Task pruefen, ob er vollstaendig ist und keine Konflikte hat.'"
            style={{
              width: "100%", maxWidth: "100%", boxSizing: "border-box",
              minHeight: 80, resize: "vertical", fontSize: 12, lineHeight: 1.5,
              fontFamily: "inherit",
            }}
            disabled={loading}
          />
          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <button
              className="btn btn-primary btn-sm"
              onClick={runAi}
              disabled={loading || userInput.trim().length < 5}
              style={{ fontSize: 12 }}
            >
              {loading ? "⏳ KI denkt nach..." : "🤖 KI-Optimierung starten"}
            </button>
            <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", alignSelf: "center" }}>
              {userInput.length} Zeichen
            </span>
          </div>
        </div>

        {error && (
          <div style={{
            padding: 8, marginBottom: 12, fontSize: 12,
            background: "rgba(255, 88, 88, 0.1)", border: "1px solid var(--color-hermes-danger)",
            borderRadius: 4, color: "var(--color-hermes-danger)",
          }}>
            ⚠ {error}
          </div>
        )}

        {/* KI-Result */}
        {aiResult && (
          <div style={{ borderTop: "1px solid var(--color-hermes-border)", paddingTop: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
              <span style={{ fontSize: 16 }}>✨</span>
              <strong style={{ fontSize: 13 }}>KI-generiertes Ergebnis</strong>
              <div style={{ flex: 1 }} />
              {!editingAi ? (
                <button
                  className="btn btn-sm"
                  onClick={() => setEditingAi(true)}
                  style={{ fontSize: 11 }}
                >
                  ✏ Manuelle Anpassung
                </button>
              ) : (
                <button
                  className="btn btn-sm btn-primary"
                  onClick={applyEdits}
                  style={{ fontSize: 11 }}
                >
                  ✓ Änderungen übernehmen
                </button>
              )}
            </div>

            {/* Description (editierbar oder read-only) */}
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
                Was passiert hier?
              </div>
              {editingAi ? (
                <textarea
                  className="input"
                  value={editedDescription}
                  onChange={(e) => setEditedDescription(e.target.value)}
                  style={{
                    width: "100%", maxWidth: "100%", boxSizing: "border-box",
                    minHeight: 100, resize: "vertical", fontSize: 12, lineHeight: 1.5,
                    fontFamily: "inherit",
                  }}
                />
              ) : (
                <div style={{
                  padding: 8, fontSize: 12, lineHeight: 1.5,
                  background: "var(--color-hermes-muted)", borderRadius: 4,
                  whiteSpace: "pre-wrap",
                }}>
                  {aiResult.description}
                </div>
              )}
            </div>

            {/* Expected Result (editierbar oder read-only) */}
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
                Erwartetes Ergebnis
              </div>
              {editingAi ? (
                <textarea
                  className="input"
                  value={editedExpected}
                  onChange={(e) => setEditedExpected(e.target.value)}
                  style={{
                    width: "100%", maxWidth: "100%", boxSizing: "border-box",
                    minHeight: 60, resize: "vertical", fontSize: 12, lineHeight: 1.5,
                    fontFamily: "inherit",
                  }}
                />
              ) : (
                <div style={{
                  padding: 8, fontSize: 12, lineHeight: 1.5,
                  background: "var(--color-hermes-muted)", borderRadius: 4,
                  whiteSpace: "pre-wrap",
                }}>
                  {aiResult.expected_result || <em style={{ color: "var(--color-hermes-text-secondary)" }}>(nicht definiert)</em>}
                </div>
              )}
            </div>

            {/* Rückfragen */}
            {aiResult.questions && aiResult.questions.length > 0 && (
              <details style={{ marginBottom: 8, fontSize: 11 }}>
                <summary style={{ cursor: "pointer", color: "var(--color-hermes-text-secondary)" }}>
                  ❓ {aiResult.questions.length} Rückfrage(n) der KI
                </summary>
                <ul style={{ margin: "4px 0 0 0", paddingLeft: 20, fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                  {aiResult.questions.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </details>
            )}

            {/* Suggestions */}
            {aiResult.suggestions && aiResult.suggestions.length > 0 && (
              <details style={{ marginBottom: 10, fontSize: 11 }}>
                <summary style={{ cursor: "pointer", color: "var(--color-hermes-text-secondary)" }}>
                  💡 {aiResult.suggestions.length} Verbesserungsvorschlag/Vorschläge der KI
                </summary>
                <ul style={{ margin: "4px 0 0 0", paddingLeft: 20, fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                  {aiResult.suggestions.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </details>
            )}

            {/* Action-Buttons */}
            <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
              <button
                className="btn btn-primary btn-sm"
                onClick={onSave}
                disabled={saving}
                style={{ fontSize: 12 }}
              >
                {saving ? "Speichert..." : "💾 Übernehmen & Speichern"}
              </button>
              <button
                className="btn btn-sm"
                onClick={onClose}
                disabled={saving}
                style={{ fontSize: 12 }}
              >
                Abbrechen
              </button>
              <div style={{ flex: 1 }} />
              <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", alignSelf: "center" }}>
                Tipp: Vor dem Speichern manuell verfeinern
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// =====================================================
//  AddStepModal — User-Direktive 17.06.2026
//  Modal zum Anlegen eines neuen SOP-Steps (in Detail + BPMN-View).
// =====================================================
function AddStepModal({ sopId, steps, onClose, onCreated }: {
  sopId: string
  steps: any[]
  onClose: () => void
  onCreated: (newStepId: string) => void
}) {
  const qc = useQueryClient()
  const [name, setName] = useState("")
  const [agent, setAgent] = useState("pi-coder")
  const [phase, setPhase] = useState("Task")
  const [trigger, setTrigger] = useState("step_completed")
  const [action, setAction] = useState("noop")
  const [description, setDescription] = useState("")
  const [expectedResult, setExpectedResult] = useState("")
  const [insertAfterId, setInsertAfterId] = useState<string>("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // User-Direktive 22.06.2026: Modell wird automatisch aus SubAgent-Konfiguration abgeleitet,
  // nicht mehr manuell gewaehlt. Backend erhaelt das abgeleitete Modell fuer historische Speicherung.
  const { data: agentConfigsData } = useQuery({
    queryKey: ["subagent-configs"],
    queryFn: () => api.subagents.listConfigs(),
    staleTime: 60_000,
  })
  const modelFromAgent = useMemo(() => {
    if (!agent || agent === "system" || agent === "user") return ""
    const cfg = (agentConfigsData || []).find((c: any) => c.name === agent)
    if (!cfg) return ""
    const m = cfg.model || cfg.default_model || ""
    return cfg.provider && m ? `${cfg.provider}/${m}` : m
  }, [agent, agentConfigsData])

  async function handleSave() {
    if (!name.trim()) {
      setError("Bitte einen Namen eingeben.")
      return
    }
    setSaving(true)
    setError(null)
    try {
      const body: any = {
        name: name.trim(),
        phase,
        agent,
        model: modelFromAgent,
        trigger,
        action,
        description: description.trim() || null,
        expected_result: expectedResult.trim() || null,
      }
      if (insertAfterId) {
        body.insert_after_step_id = insertAfterId
      }
      const resp = await api.createSopStep(sopId, body)
      // SOP-Daten neu laden (Detail-View + BPMN-View)
      qc.invalidateQueries({ queryKey: ["sop", sopId] })
      qc.invalidateQueries({ queryKey: ["sop-bpmn", sopId] })
      qc.invalidateQueries({ queryKey: ["sops"] })
      onCreated(resp?.step?.id || "")
      onClose()
    } catch (e: any) {
      console.error("AddStep-Fehler:", e)
      setError(e?.message || String(e))
      setSaving(false)
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
          borderRadius: 10, padding: 20, maxWidth: 640, width: "92%",
          maxHeight: "90vh", overflowY: "auto",
          boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
          <PlusCircle size={22} color="var(--color-hermes-accent, #7c3aed)" />
          <h2 style={{ margin: 0, fontSize: 18 }}>Neuen Step hinzufügen</h2>
          <div style={{ flex: 1 }} />
          <button
            onClick={onClose}
            style={{ background: "transparent", border: "none", color: "#999", cursor: "pointer", padding: 4 }}
            title="Schliessen"
          >
            <X size={18} />
          </button>
        </div>

        {error && (
          <div style={{ background: "rgba(220,38,38,0.15)", border: "1px solid #dc2626", padding: 10, borderRadius: 6, marginBottom: 12, fontSize: 12, color: "#fca5a5" }}>
            ⚠ {error}
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", display: "block", marginBottom: 4 }}>
              Step-Name *
            </label>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. 'Detaillierte Anforderungsanalyse'"
              autoFocus
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div>
              <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", display: "block", marginBottom: 4 }}>
                Phase
              </label>
              <select className="input" value={phase} onChange={(e) => setPhase(e.target.value)}>
                <option value="Task">Task</option>
                <option value="Sub-SOP">Sub-SOP</option>
                <option value="End">End</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", display: "block", marginBottom: 4 }}>
                Worker / Agent
              </label>
              <AgentSelect value={agent} onChange={setAgent} />
            </div>
          </div>

          <div>
            <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", display: "block", marginBottom: 4 }}>
              Modell (aus SubAgent-Konfiguration)
            </label>
            <AgentModelDisplay agent={agent} style={{ width: "100%" }} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div>
              <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", display: "block", marginBottom: 4 }}>
                Trigger
              </label>
              <select className="input" value={trigger} onChange={(e) => setTrigger(e.target.value)}>
                <option value="manual">manual</option>
                <option value="sop_start">sop_start</option>
                <option value="step_completed">step_completed</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", display: "block", marginBottom: 4 }}>
                Action
              </label>
              <select className="input" value={action} onChange={(e) => setAction(e.target.value)}>
                <option value="noop">noop (warten)</option>
                <option value="set_status">set_status</option>
                <option value="ask_user">ask_user (Rückfrage)</option>
                <option value="spawn_sop">spawn_sop (Sub-SOP)</option>
                <option value="llm_call">llm_call (KI-Aufruf)</option>
              </select>
            </div>
          </div>

          <div>
            <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", display: "block", marginBottom: 4 }}>
              Einfügen nach (optional)
            </label>
            <select className="input" value={insertAfterId} onChange={(e) => setInsertAfterId(e.target.value)}>
              <option value="">— Am Ende anhängen —</option>
              {steps.map((s: any) => (
                <option key={s.id} value={s.id}>
                  #{s.step_order}: {s.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", display: "block", marginBottom: 4 }}>
              Beschreibung (optional)
            </label>
            <textarea
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Was soll dieser Step konkret tun?"
            />
          </div>

          <div>
            <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", display: "block", marginBottom: 4 }}>
              Expected Result (optional)
            </label>
            <textarea
              className="input"
              value={expectedResult}
              onChange={(e) => setExpectedResult(e.target.value)}
              rows={2}
              placeholder="Woran erkennt man, dass der Step erfolgreich war?"
            />
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 16, paddingTop: 12, borderTop: "1px solid var(--color-hermes-border)" }}>
          <button
            className="btn btn-sm btn-primary"
            onClick={handleSave}
            disabled={saving}
            style={{ fontSize: 12 }}
          >
            {saving ? "Speichert..." : "➕ Step hinzufügen"}
          </button>
          <button
            className="btn btn-sm"
            onClick={onClose}
            disabled={saving}
            style={{ fontSize: 12 }}
          >
            Abbrechen
          </button>
        </div>
      </div>
    </div>
  )
}

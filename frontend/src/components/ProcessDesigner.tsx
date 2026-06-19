import { useState, useRef, useEffect, useMemo } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../api"
import {
  Play, Square, Diamond, Circle, GitBranch, GitMerge, Save, Trash2,
  Plus, X, Download, Upload, ChevronRight, MoreVertical
} from "lucide-react"

// === BPMN Node Types ===
type NodeType = "start" | "end" | "task" | "decision" | "parallel" | "merge"

interface BpmnNode {
  id: string
  type: NodeType
  label: string
  x: number
  y: number
  properties: {
    assigned_role?: string
    priority?: number
    success_criteria?: string[]
    description?: string
    [key: string]: any
  }
}

interface BpmnEdge {
  id: string
  from: string
  to: string
  label?: string
  condition?: string
  target_status?: string  // Status der nach diesem Edge gesetzt wird (z.B. 'rueckfrage', 'todo', 'block', ...)
}

const STATUS_OPTIONS = [
  { value: "", label: "Process-Flow (default)" },
  { value: "triage", label: "Triage" },
  { value: "todo", label: "GO" },
  { value: "in_progress", label: "In Progress" },
  { value: "review", label: "Review" },
  { value: "block", label: "Block (Rückfragen)" },
  { value: "rueckfrage", label: "Rückfragen (block)" },
  { value: "done", label: "Done" },
]

// === Palette Items (BPMN 2.0) ===
const PALETTE_ITEMS: { type: NodeType; label: string; Icon: any; color: string; defaultProps: any }[] = [
  { type: "start",    label: "Start",      Icon: Play,       color: "#2ea043", defaultProps: { is_marker: true } },
  { type: "task",     label: "Task",       Icon: Square,     color: "#58a6ff", defaultProps: { assigned_role: "pi-coder", priority: 50, success_criteria: [] } },
  { type: "decision", label: "Decision",   Icon: Diamond,    color: "#d29922", defaultProps: { description: "Bedingung?" } },
  { type: "parallel", label: "Parallel",   Icon: GitBranch,  color: "#a371f7", defaultProps: { is_marker: true } },
  { type: "merge",    label: "Merge",      Icon: GitMerge,   color: "#a371f7", defaultProps: { is_marker: true } },
  { type: "end",      label: "Ende",       Icon: Circle,     color: "#f85149", defaultProps: { is_marker: true } },
]

const NODE_W = 140
const NODE_H = 60

function getNodeStyle(type: NodeType, color: string): React.CSSProperties {
  if (type === "start") return { background: "#1a3a23", borderColor: "#2ea043", borderRadius: 30, color: "#7ee787" }
  if (type === "end") return { background: "#3a1a1a", borderColor: "#f85149", borderRadius: 30, color: "#ffa198" }
  if (type === "decision") return { background: "#3a2e1a", borderColor: "#d29922", transform: "rotate(45deg)", color: "#f0c674" }
  if (type === "parallel" || type === "merge") return { background: "#2a1f3a", borderColor: "#a371f7", color: "#d2b8ff" }
  return { background: "#1a2a3a", borderColor: "#58a6ff", color: "#9ec5fe" }
}

function getNodeLabel(type: NodeType, label: string, color: string): React.ReactElement {
  if (type === "decision") {
    return <span style={{ transform: "rotate(-45deg)", display: "block", textAlign: "center", fontSize: 11, color }}>{label}</span>
  }
  return <span style={{ fontSize: 11, color }}>{label}</span>
}

interface ProcessDesignerProps {
  template: {
    id?: string
    project_id: string
    name: string
    description?: string
    nodes: BpmnNode[]
    edges: BpmnEdge[]
  }
  onSave: (data: any) => void
  onApplyToTask?: (taskId: string) => void
  availableTasks?: any[]
  isSaving?: boolean
}

export function ProcessDesigner({ template, onSave, onApplyToTask, availableTasks, isSaving }: ProcessDesignerProps) {
  const [nodes, setNodes] = useState<BpmnNode[]>(template.nodes || [])
  const [edges, setEdges] = useState<BpmnEdge[]>(template.edges || [])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null)
  const [connectFrom, setConnectFrom] = useState<string | null>(null)
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null)
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })
  const [name, setName] = useState(template.name)
  const [description, setDescription] = useState(template.description || "")
  const [showApplyModal, setShowApplyModal] = useState(false)
  const canvasRef = useRef<HTMLDivElement>(null)

  // Sync mit template wenn sich ID aendert
  useEffect(() => {
    setNodes(template.nodes || [])
    setEdges(template.edges || [])
    setName(template.name)
    setDescription(template.description || "")
    setSelectedNodeId(null)
    setConnectFrom(null)
  }, [template.id])

  const selectedNode = nodes.find(n => n.id === selectedNodeId)
  const selectedEdge = edges.find(e => e.id === selectedEdgeId)

  // === Drag & Drop: Palette → Canvas ===
  function onCanvasDragOver(e: React.DragEvent) {
    e.preventDefault()
  }
  function onCanvasDrop(e: React.DragEvent) {
    e.preventDefault()
    const type = e.dataTransfer.getData("bpmn-type") as NodeType
    if (!type) return
    const item = PALETTE_ITEMS.find(p => p.type === type)
    if (!item) return
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    const x = e.clientX - rect.left - NODE_W / 2
    const y = e.clientY - rect.top - NODE_H / 2
    const newNode: BpmnNode = {
      id: `n${Date.now()}`,
      type,
      label: item.label,
      x: Math.max(20, x),
      y: Math.max(20, y),
      properties: { ...item.defaultProps },
    }
    setNodes(prev => [...prev, newNode])
    setSelectedNodeId(newNode.id)
  }

  // === Drag Node innerhalb Canvas ===
  function onNodeMouseDown(e: React.MouseEvent, node: BpmnNode) {
    if (connectFrom) {
      // Connect-Mode: zweiter Klick = Zielfenster
      if (connectFrom !== node.id) {
        const newEdge: BpmnEdge = {
          id: `e${Date.now()}`,
          from: connectFrom,
          to: node.id,
        }
        setEdges(prev => [...prev, newEdge])
        setConnectFrom(null)
      }
      return
    }
    // Drag starten
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    setDraggingNodeId(node.id)
    setDragOffset({ x: e.clientX - rect.left - node.x, y: e.clientY - rect.top - node.y })
    setSelectedNodeId(node.id)
    e.stopPropagation()
  }

  function onCanvasMouseMove(e: React.MouseEvent) {
    if (!draggingNodeId) return
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    const x = e.clientX - rect.left - dragOffset.x
    const y = e.clientY - rect.top - dragOffset.y
    setNodes(prev => prev.map(n => n.id === draggingNodeId ? { ...n, x: Math.max(20, x), y: Math.max(20, y) } : n))
  }

  function onCanvasMouseUp() {
    setDraggingNodeId(null)
  }

  // === Connect-Button (auf einem Node) ===
  function onConnectClick(e: React.MouseEvent, node: BpmnNode) {
    e.stopPropagation()
    if (connectFrom === node.id) {
      setConnectFrom(null)
    } else {
      setConnectFrom(node.id)
    }
  }

  // === Delete Node/Edge ===
  function deleteNode(id: string) {
    setNodes(prev => prev.filter(n => n.id !== id))
    setEdges(prev => prev.filter(e => e.from !== id && e.to !== id))
    if (selectedNodeId === id) setSelectedNodeId(null)
  }
  function deleteEdge(id: string) {
    setEdges(prev => prev.filter(e => e.id !== id))
  }

  // === Update Property ===
  function updateNodeProperty(key: string, value: any) {
    if (!selectedNode) return
    setNodes(prev => prev.map(n => n.id === selectedNode.id ? { ...n, properties: { ...n.properties, [key]: value } } : n))
  }

  // === Auto-Layout (topological) ===
  function autoLayout() {
    const fromMap: Record<string, string[]> = {}
    const toCount: Record<string, number> = {}
    nodes.forEach(n => { fromMap[n.id] = []; toCount[n.id] = 0 })
    edges.forEach(e => { fromMap[e.from]?.push(e.to); toCount[e.to] = (toCount[e.to] || 0) + 1 })
    const levels: Record<string, number> = {}
    const queue: string[] = nodes.filter(n => toCount[n.id] === 0).map(n => n.id)
    queue.forEach(n => { levels[n] = 0 })
    while (queue.length > 0) {
      const cur = queue.shift()!
      fromMap[cur]?.forEach(next => {
        if (levels[next] === undefined || levels[next] < levels[cur] + 1) {
          levels[next] = levels[cur] + 1
        }
        if (!queue.includes(next)) queue.push(next)
      })
    }
    // Gruppierung nach Level
    const byLevel: Record<number, string[]> = {}
    Object.entries(levels).forEach(([nid, lvl]) => {
      byLevel[lvl] = byLevel[lvl] || []
      byLevel[lvl].push(nid)
    })
    const COL_W = NODE_W + 80
    const ROW_H = NODE_H + 60
    const newNodes = nodes.map(n => ({
      ...n,
      x: (levels[n.id] || 0) * COL_W + 60,
      y: ((byLevel[levels[n.id] || 0]?.indexOf(n.id) || 0) + 1) * ROW_H,
    }))
    setNodes(newNodes)
  }

  // === Save ===
  function handleSave() {
    onSave({ name, description, nodes, edges })
  }

  // === Edge-Pfad-Berechnung (mit Kurven) ===
  function getEdgePath(e: BpmnEdge): string {
    const from = nodes.find(n => n.id === e.from)
    const to = nodes.find(n => n.id === e.to)
    if (!from || !to) return ""
    const fx = from.x + NODE_W
    const fy = from.y + NODE_H / 2
    const tx = to.x
    const ty = to.y + NODE_H / 2
    const dx = Math.abs(tx - fx) * 0.4
    return `M ${fx} ${fy} C ${fx + dx} ${fy}, ${tx - dx} ${ty}, ${tx} ${ty}`
  }

  return (
    <div style={{ display: "flex", height: "100%", minHeight: 600, background: "var(--color-hermes-bg)" }}>
      {/* === LINKS: Palette === */}
      <div style={{ width: 180, borderRight: "1px solid var(--color-hermes-border)", padding: 10, overflowY: "auto" }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-hermes-text-secondary)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>BPMN 2.0 Palette</div>
        {PALETTE_ITEMS.map(item => (
          <div
            key={item.type}
            draggable
            onDragStart={(e) => e.dataTransfer.setData("bpmn-type", item.type)}
            style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "8px 10px", marginBottom: 6,
              background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)",
              borderRadius: 6, cursor: "grab", fontSize: 12,
            }}
          >
            <item.Icon size={14} color={item.color} />
            <span>{item.label}</span>
          </div>
        ))}
        <div style={{ marginTop: 16, fontSize: 10, color: "var(--color-hermes-text-secondary)", lineHeight: 1.4 }}>
          💡 <strong>Tipp:</strong> Symbole auf die Arbeitsfläche ziehen. Verbinde-Punkte (oben/unten) klicken um zu verknüpfen.
        </div>
      </div>

      {/* === MITTE: Canvas === */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {/* Top Toolbar */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderBottom: "1px solid var(--color-hermes-border)", background: "var(--color-hermes-surface)" }}>
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Process-Name"
            style={{ flex: 1, maxWidth: 300, fontSize: 13 }}
          />
          <button className="btn btn-sm" onClick={autoLayout} title="Auto-Layout">📐 Auto-Layout</button>
          <button className="btn btn-sm btn-primary" onClick={handleSave} disabled={isSaving}>
            <Save size={12} /> {isSaving ? "Speichere..." : "Speichern"}
          </button>
          {onApplyToTask && (
            <button className="btn btn-sm" onClick={() => setShowApplyModal(true)}>
              <Download size={12} /> Auf Task anwenden
            </button>
          )}
        </div>

        {/* Canvas-Bereich */}
        <div
          ref={canvasRef}
          onDragOver={onCanvasDragOver}
          onDrop={onCanvasDrop}
          onMouseMove={onCanvasMouseMove}
          onMouseUp={onCanvasMouseUp}
          onMouseLeave={onCanvasMouseUp}
          onClick={() => { setSelectedNodeId(null); setConnectFrom(null) }}
          style={{
            flex: 1, position: "relative", overflow: "auto",
            background: "repeating-linear-gradient(0deg, transparent, transparent 19px, rgba(255,255,255,0.03) 19px, rgba(255,255,255,0.03) 20px), repeating-linear-gradient(90deg, transparent, transparent 19px, rgba(255,255,255,0.03) 19px, rgba(255,255,255,0.03) 20px)",
            backgroundColor: "var(--color-hermes-bg)",
          }}
        >
          {/* SVG-Layer fuer Edges */}
          <svg style={{ position: "absolute", top: 0, left: 0, width: 4000, height: 4000, pointerEvents: "none" }}>
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-hermes-accent-blue)" />
              </marker>
            </defs>
            {edges.map(e => {
              const isEdgeSelected = e.id === selectedEdgeId
              const edgeColor = e.target_status === "rueckfrage" || e.target_status === "block"
                ? "var(--color-hermes-danger)"
                : e.target_status === "in_progress"
                ? "var(--color-hermes-accent)"
                : e.target_status === "review"
                ? "var(--color-hermes-accent-blue)"
                : "var(--color-hermes-accent-blue)"
              return (
                <g key={e.id} style={{ pointerEvents: "all", cursor: "pointer" }} onClick={(ev) => { ev.stopPropagation(); setSelectedEdgeId(e.id); setSelectedNodeId(null); }}>
                  <title>Klicken zum Bearbeiten · Shift+Klick zum Löschen</title>
                  <path d={getEdgePath(e)} stroke={edgeColor} strokeWidth={isEdgeSelected ? "3" : "2"} fill="none" markerEnd="url(#arrow)" style={{ cursor: "pointer" }} />
                  {(e.label || e.target_status) && (
                    <g>
                      <rect x={(nodes.find(n => n.id === e.from)!.x + NODE_W + nodes.find(n => n.id === e.to)!.x) / 2 - 40}
                            y={(nodes.find(n => n.id === e.from)!.y + nodes.find(n => n.id === e.to)!.y) / 2 - 20}
                            width="80" height="22" rx="4" fill="var(--color-hermes-surface-2)" stroke={edgeColor} />
                      <text x={(nodes.find(n => n.id === e.from)!.x + NODE_W + nodes.find(n => n.id === e.to)!.x) / 2}
                            y={(nodes.find(n => n.id === e.from)!.y + nodes.find(n => n.id === e.to)!.y) / 2 - 6}
                            fill="var(--color-hermes-text)" fontSize="10" textAnchor="middle">
                        {e.target_status ? `→ ${e.target_status}` : e.label || ""}
                      </text>
                    </g>
                  )}
                </g>
              )
            })}
          </svg>

          {/* Nodes */}
          {nodes.map(n => {
            const item = PALETTE_ITEMS.find(p => p.type === n.type)
            const isSelected = n.id === selectedNodeId
            const isConnecting = n.id === connectFrom
            const transform = n.type === "decision" ? `translate(0,0) rotate(45deg)` : undefined
            return (
              <div
                key={n.id}
                onMouseDown={(e) => onNodeMouseDown(e, n)}
                onClick={(e) => { e.stopPropagation(); if (!connectFrom) setSelectedNodeId(n.id) }}
                style={{
                  position: "absolute",
                  left: n.x,
                  top: n.y,
                  width: NODE_W,
                  height: NODE_H,
                  border: `2px solid ${item?.color || "var(--color-hermes-border)"}`,
                  background: n.type === "start" || n.type === "end" ? item?.color : "var(--color-hermes-surface)",
                  transform: transform,
                  ...(n.type === "start" || n.type === "end" ? { borderRadius: NODE_H / 2 } : {}),
                  display: "flex", alignItems: "center", justifyContent: "center",
                  cursor: draggingNodeId === n.id ? "grabbing" : "grab",
                  boxShadow: isSelected ? "0 0 0 3px var(--color-hermes-accent-blue)" : isConnecting ? "0 0 0 3px var(--color-hermes-accent-orange)" : "none",
                  zIndex: isSelected || isConnecting ? 10 : 1,
                }}
              >
                {n.type === "decision" ? (
                  getNodeLabel(n.type, n.label, item?.color)
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 8px", textAlign: "center" }}>
                    {item && <item.Icon size={14} color={item.color} />}
                    <span style={{ fontSize: 11, color: n.type === "start" || n.type === "end" ? "#0d1117" : item?.color, fontWeight: 600 }}>{n.label}</span>
                  </div>
                )}

                {/* Connection-Punkte (oben + unten) */}
                {!item?.defaultProps.is_marker || n.type === "start" || n.type === "end" ? null : (
                  <>
                    <div onClick={(e) => onConnectClick(e, n)} title="Verbindung starten (oben)"
                      style={{ position: "absolute", top: -6, left: NODE_W / 2 - 6, width: 12, height: 12, background: connectFrom === n.id ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-accent-blue)", borderRadius: "50%", cursor: "pointer", zIndex: 2, border: "2px solid var(--color-hermes-bg)" }} />
                    <div onClick={(e) => onConnectClick(e, n)} title="Verbindung starten (unten)"
                      style={{ position: "absolute", bottom: -6, left: NODE_W / 2 - 6, width: 12, height: 12, background: "var(--color-hermes-accent-blue)", borderRadius: "50%", cursor: "pointer", zIndex: 2, border: "2px solid var(--color-hermes-bg)" }} />
                  </>
                )}
                {/* Start: nur Output (unten), End: nur Input (oben) */}
                {n.type === "start" && (
                  <div onClick={(e) => onConnectClick(e, n)} title="Output (Start)"
                    style={{ position: "absolute", bottom: -6, left: NODE_W / 2 - 6, width: 12, height: 12, background: "var(--color-hermes-accent-blue)", borderRadius: "50%", cursor: "pointer", zIndex: 2, border: "2px solid var(--color-hermes-bg)" }} />
                )}
                {n.type === "end" && (
                  <div onClick={(e) => onConnectClick(e, n)} title="Input (Ende)"
                    style={{ position: "absolute", top: -6, left: NODE_W / 2 - 6, width: 12, height: 12, background: "var(--color-hermes-accent-blue)", borderRadius: "50%", cursor: "pointer", zIndex: 2, border: "2px solid var(--color-hermes-bg)" }} />
                )}
                {n.type !== "start" && n.type !== "end" && !item?.defaultProps.is_marker && (
                  <>
                    <div onClick={(e) => onConnectClick(e, n)} title="Verbindung (oben)"
                      style={{ position: "absolute", top: -6, left: NODE_W / 2 - 6, width: 12, height: 12, background: connectFrom === n.id ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-accent-blue)", borderRadius: "50%", cursor: "pointer", zIndex: 2, border: "2px solid var(--color-hermes-bg)" }} />
                    <div onClick={(e) => onConnectClick(e, n)} title="Verbindung (unten)"
                      style={{ position: "absolute", bottom: -6, left: NODE_W / 2 - 6, width: 12, height: 12, background: "var(--color-hermes-accent-blue)", borderRadius: "50%", cursor: "pointer", zIndex: 2, border: "2px solid var(--color-hermes-bg)" }} />
                  </>
                )}

                {isSelected && (
                  <button onClick={(e) => { e.stopPropagation(); deleteNode(n.id) }} title="Loeschen"
                    style={{ position: "absolute", top: -10, right: -10, width: 20, height: 20, background: "var(--color-hermes-danger)", color: "white", border: "none", borderRadius: "50%", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 3 }}>
                    <X size={12} />
                  </button>
                )}
              </div>
            )
          })}

          {connectFrom && (
            <div style={{ position: "absolute", top: 10, right: 10, padding: "6px 12px", background: "var(--color-hermes-accent-orange)", color: "#0d1117", borderRadius: 6, fontSize: 12, fontWeight: 600 }}>
              Klicke auf das Ziel-Symbol zum Verbinden (Klick irgendwo zum Abbrechen)
            </div>
          )}

          {nodes.length === 0 && (
            <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", color: "var(--color-hermes-text-secondary)", textAlign: "center", pointerEvents: "none" }}>
              <GitBranch size={48} style={{ opacity: 0.3, marginBottom: 12 }} />
              <p>Ziehe Symbole aus der linken Palette hierher</p>
              <p style={{ fontSize: 11, opacity: 0.7 }}>Start mit "Start" und "Ende", dann Tasks dazwischen</p>
            </div>
          )}
        </div>
      </div>

      {/* === RECHTS: Properties Sidebar === */}
      <div style={{ width: 320, borderLeft: "1px solid var(--color-hermes-border)", padding: 12, overflowY: "auto", background: "var(--color-hermes-surface)" }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-hermes-text-secondary)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>Process-Einstellungen</div>
        <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Name</label>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} style={{ marginBottom: 10, fontSize: 12 }} />
        <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Beschreibung</label>
        <textarea className="input" value={description} onChange={(e) => setDescription(e.target.value)} style={{ minHeight: 50, fontSize: 12, marginBottom: 16 }} />

        <hr style={{ border: 0, borderTop: "1px solid var(--color-hermes-border)", margin: "12px 0" }} />

        {selectedEdge ? (
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-hermes-text-secondary)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
              🔗 Verbindungs-Spezifikation
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
              <span className="badge badge-blue">{selectedEdge.from.slice(0, 8)}</span>
              <span style={{ color: "var(--color-hermes-text-secondary)" }}>→</span>
              <span className="badge badge-green">{selectedEdge.to.slice(0, 8)}</span>
            </div>

            <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Label (optional)</label>
            <input
              className="input"
              value={selectedEdge.label || ""}
              onChange={(e) => setEdges(prev => prev.map(x => x.id === selectedEdge.id ? { ...x, label: e.target.value } : x))}
              style={{ marginBottom: 10, fontSize: 12 }}
              placeholder="z.B. 'ja' / 'nein' / 'erfolgreich'"
            />

            <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Bedingung (optional)</label>
            <input
              className="input"
              value={selectedEdge.condition || ""}
              onChange={(e) => setEdges(prev => prev.map(x => x.id === selectedEdge.id ? { ...x, condition: e.target.value } : x))}
              style={{ marginBottom: 10, fontSize: 12 }}
              placeholder="z.B. success==true"
            />

            <label style={{ fontSize: 11, color: "var(--color-hermes-accent-blue)", fontWeight: 600 }}>
              ⚡ Transition Target Status
            </label>
            <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 6 }}>
              Beim Durchlaufen dieser Verbindung wird der Task auf den gewaehlten Status gesetzt (sonst Standard-Workflow).
            </div>
            <select
              className="select"
              value={selectedEdge.target_status || ""}
              onChange={(e) => setEdges(prev => prev.map(x => x.id === selectedEdge.id ? { ...x, target_status: e.target.value || undefined } : x))}
              style={{ width: "100%", marginBottom: 10, fontSize: 12 }}
            >
              {STATUS_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            {selectedEdge.target_status && (
              <div style={{ fontSize: 10, padding: "6px 8px", background: "rgba(88, 166, 255, 0.1)", borderLeft: "2px solid var(--color-hermes-accent-blue)", borderRadius: 4, marginBottom: 10 }}>
                <strong>Aktiver Override:</strong> Task wird auf <code>{selectedEdge.target_status}</code> gesetzt, sobald diese Verbindung durchlaufen wird.
              </div>
            )}

            <button onClick={() => { setEdges(prev => prev.filter(x => x.id !== selectedEdge.id)); setSelectedEdgeId(null) }} className="btn btn-sm btn-danger" style={{ width: "100%", marginTop: 10 }}>
              Verbindung loeschen
            </button>
          </div>
        ) : selectedNode ? (
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-hermes-text-secondary)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
              Schritt-Spezifikation
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
              <span className="badge badge-blue">{selectedNode.type}</span>
              <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>ID: {selectedNode.id.slice(0, 8)}</span>
            </div>

            <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Label (Schritt-Name)</label>
            <input
              className="input"
              value={selectedNode.label}
              onChange={(e) => setNodes(prev => prev.map(n => n.id === selectedNode.id ? { ...n, label: e.target.value } : n))}
              style={{ marginBottom: 10, fontSize: 12 }}
            />

            {!PALETTE_ITEMS.find(p => p.type === selectedNode.type)?.defaultProps.is_marker && (
              <>
                <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Worker (assigned_role)</label>
                <select
                  className="select"
                  value={selectedNode.properties.assigned_role || "pi-coder"}
                  onChange={(e) => updateNodeProperty("assigned_role", e.target.value)}
                  style={{ width: "100%", marginBottom: 10, fontSize: 12 }}
                >
                  <option value="pi-coder">👨‍💻 pi-coder</option>
                  <option value="pi-tester">🧪 pi-tester</option>
                  <option value="pi-reviewer">🔍 pi-reviewer</option>
                  <option value="pi-fixer">🔧 pi-fixer</option>
                  <option value="CIO">👔 CIO</option>
                  <option value="CEO-digital">📱 CEO-digital</option>
                </select>

                <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Priority</label>
                <input
                  type="number" min={0} max={100}
                  className="input"
                  value={selectedNode.properties.priority ?? 50}
                  onChange={(e) => updateNodeProperty("priority", Number(e.target.value))}
                  style={{ marginBottom: 10, fontSize: 12, width: 80 }}
                />

                <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Success Criteria (eines pro Zeile)</label>
                <textarea
                  className="input"
                  value={(selectedNode.properties.success_criteria || []).join("\n")}
                  onChange={(e) => updateNodeProperty("success_criteria", e.target.value.split("\n").filter(s => s.trim()))}
                  style={{ minHeight: 70, fontSize: 11, marginBottom: 10 }}
                  placeholder="z.B. Login funktioniert mit OAuth2"
                />
              </>
            )}

            <button onClick={() => deleteNode(selectedNode.id)} className="btn btn-sm btn-danger" style={{ width: "100%", marginTop: 10 }}>
              <Trash2 size={12} /> Schritt loeschen
            </button>
          </div>
        ) : (
          <div style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12, textAlign: "center", padding: 20 }}>
            <MoreVertical size={32} style={{ opacity: 0.3, marginBottom: 8 }} />
            <p>Klicke auf einen Schritt im Canvas, um die Spezifikationen zu bearbeiten.</p>
          </div>
        )}

        <hr style={{ border: 0, borderTop: "1px solid var(--color-hermes-border)", margin: "12px 0" }} />

        <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
          <strong>Statistik:</strong> {nodes.length} Schritte, {edges.length} Verbindungen
        </div>
      </div>

      {/* Apply-to-Task Modal */}
      {showApplyModal && onApplyToTask && (
        <div className="modal-backdrop" onClick={() => setShowApplyModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ minWidth: 400 }}>
            <h3 style={{ margin: "0 0 12px" }}>Process auf Task anwenden</h3>
            <p style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12, marginBottom: 12 }}>
              Waehle einen Task aus. Fuer jeden "Task"-Node im Process wird ein Sub-Task erstellt.
            </p>
            <div style={{ maxHeight: 300, overflowY: "auto", border: "1px solid var(--color-hermes-border)", borderRadius: 6 }}>
              {(availableTasks || []).map((t: any) => (
                <div key={t.id} onClick={() => { onApplyToTask(t.id); setShowApplyModal(false) }}
                  style={{ padding: 10, cursor: "pointer", borderBottom: "1px solid var(--color-hermes-border)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-hermes-muted)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                  <div style={{ fontWeight: 500, fontSize: 12 }}>{t.title}</div>
                  <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>Status: {t.status} · Prio: {t.priority}</div>
                </div>
              ))}
            </div>
            <button className="btn btn-sm" style={{ marginTop: 12 }} onClick={() => setShowApplyModal(false)}>Abbrechen</button>
          </div>
        </div>
      )}
    </div>
  )
}

import { Workflow } from "lucide-react"

export default function BrainGraph() {
  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Workflow size={22} color="var(--color-hermes-accent-blue)" />
          <h1 style={{ margin: 0 }}>Brain Graph</h1>
        </div>
        <p>Visualisierung der OpenBrain-Gedaechtnisstruktur als Graph</p>
      </div>
      <div className="card">
        <p style={{ margin: 0, color: "var(--color-hermes-text-secondary)" }}>
          OpenBrain-Graph-Visualisierung folgt in v2.1. Geplant: Force-directed
          Graph mit Thought-Types (code, architecture, knowledge, sop, etc.) und
          Tag-Cluster.
        </p>
      </div>
    </div>
  )
}

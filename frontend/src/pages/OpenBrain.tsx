import { useQuery } from "@tanstack/react-query"
import { api } from "../api"
import { Brain } from "lucide-react"

export default function OpenBrain() {
  const { data: stats } = useQuery({ queryKey: ["brain-stats"], queryFn: () => api.getAnalytics() })
  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Brain size={22} color="var(--color-hermes-accent-blue)" />
          <h1 style={{ margin: 0 }}>OpenBrain</h1>
        </div>
        <p>Zentraler Gedächtnisspeicher für den Agent</p>
      </div>
      <div className="card">
        <p style={{ margin: 0, color: "var(--color-hermes-text-secondary)" }}>
          OpenBrain-Integration folgt in v2.1. Aktuell: {((stats as any)?.totals?.history_entries ?? 0).toLocaleString("de-DE")} History-Einträge in der SQL-DB.
        </p>
      </div>
    </div>
  )
}

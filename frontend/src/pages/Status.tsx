import { useQuery } from "@tanstack/react-query"
import { api } from "../api"
import { Activity, Server, Cpu, HardDrive, Database } from "lucide-react"

export default function Status() {
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: () => api.getAnalytics() })
  const { data: gateway } = useQuery({ queryKey: ["gateway"], queryFn: () => api.getGatewayStatus() })

  return (
    <div>
      <div className="page-header">
        <h1>Status</h1>
        <p>System-Health & laufende Services</p>
      </div>
      <div className="card-grid">
        <div className="stat-card">
          <span className="label"><Activity size={11} style={{ display: "inline", marginRight: 4 }} /> Backend</span>
          <span className="value" style={{ color: "var(--color-hermes-accent)" }}>Online</span>
          <span className="sublabel">127.0.0.1:9220</span>
        </div>
        <div className="stat-card">
          <span className="label"><Database size={11} style={{ display: "inline", marginRight: 4 }} /> Datenbank</span>
          <span className="value" style={{ color: "var(--color-hermes-accent)" }}>SQLite</span>
          <span className="sublabel">v2.0-rc · 12 Tabellen</span>
        </div>
        <div className="stat-card">
          <span className="label"><Cpu size={11} style={{ display: "inline", marginRight: 4 }} /> PI Agent</span>
          <span className="value">{gateway?.pi?.version || "—"}</span>
          <span className="sublabel">{gateway?.pi?.running ? "running" : "stopped"}</span>
        </div>
        <div className="stat-card">
          <span className="label"><Server size={11} style={{ display: "inline", marginRight: 4 }} /> Ollama</span>
          <span className="value">{gateway?.ollama?.running ? `${gateway.ollama.model_count} models` : "—"}</span>
          <span className="sublabel">{gateway?.ollama?.running ? "running" : "not detected"}</span>
        </div>
        <div className="stat-card">
          <span className="label"><HardDrive size={11} style={{ display: "inline", marginRight: 4 }} /> Tasks</span>
          <span className="value">{(health as any)?.totals?.tasks ?? 0}</span>
        </div>
        <div className="stat-card">
          <span className="label">Gesamtkosten</span>
          <span className="value" style={{ color: "var(--color-hermes-danger)" }}>${(health as any)?.totals?.cost_usd?.toFixed(4) ?? "0.0000"}</span>
        </div>
      </div>
    </div>
  )
}

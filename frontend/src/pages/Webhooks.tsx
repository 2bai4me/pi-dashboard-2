import { Activity } from "lucide-react"

export default function Webhooks() {
  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Activity size={22} color="var(--color-hermes-accent-blue)" />
          <h1 style={{ margin: 0 }}>Webhooks</h1>
        </div>
        <p>Eingehende Webhooks (GitHub, Plane, etc.)</p>
      </div>
      <div className="card">
        <p style={{ margin: 0, color: "var(--color-hermes-text-secondary)" }}>
          Webhook-Registry folgt in v2.1. Aktuell: GitHub-Push-Events ueber hermes-openclaw-bridge.
        </p>
      </div>
    </div>
  )
}

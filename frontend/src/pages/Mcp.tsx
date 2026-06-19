import { Network } from "lucide-react"

export default function Mcp() {
  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Network size={22} color="var(--color-hermes-accent-blue)" />
          <h1 style={{ margin: 0 }}>MCP</h1>
        </div>
        <p>Model Context Protocol Server-Verwaltung</p>
      </div>
      <div className="card">
        <p style={{ margin: 0, color: "var(--color-hermes-text-secondary)" }}>
          MCP-Server-Registry folgt in v2.1. Aktuelle MCP-Server: PI-Agent (50001), OpenClaw-Bridge (50005).
        </p>
      </div>
    </div>
  )
}

import { Terminal } from "lucide-react"

export default function TerminalPage() {
  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Terminal size={22} color="var(--color-hermes-accent-blue)" />
          <h1 style={{ margin: 0 }}>Terminal</h1>
        </div>
        <p>Integriertes Terminal fuer den PI Agent</p>
      </div>
      <div className="card">
        <p style={{ margin: 0, color: "var(--color-hermes-text-secondary)" }}>
          Terminal-Emulator (xterm.js + WebSocket) folgt in v2.1.
        </p>
      </div>
    </div>
  )
}

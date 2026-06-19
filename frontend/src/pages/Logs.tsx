export default function Logs() {
  return (
    <div>
      <div className="page-header">
        <h1>Logs</h1>
        <p>System- und Agent-Logs</p>
      </div>
      <div className="card">
        <p style={{ margin: 0, color: "var(--color-hermes-text-secondary)" }}>
          Live-Log-Viewer folgt in v2.1. Backend loggt nach JSON (ELK/Loki-kompatibel).
        </p>
      </div>
    </div>
  )
}

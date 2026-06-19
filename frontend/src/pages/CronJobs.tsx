import { Activity } from "lucide-react"

export default function CronJobs() {
  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Activity size={22} color="var(--color-hermes-accent-blue)" />
          <h1 style={{ margin: 0 }}>Cron Jobs</h1>
        </div>
        <p>Geplante Aufgaben (z.B. taegliche Backups, Auto-Triage)</p>
      </div>
      <div className="card">
        <p style={{ margin: 0, color: "var(--color-hermes-text-secondary)" }}>
          Cron-Management-UI folgt in v2.1. Backend-Scheduler laeuft bereits (taegliches SQLite-Backup um 02:00 UTC).
        </p>
      </div>
    </div>
  )
}

import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { api } from "../api"
import {
  Activity,
  CheckCircle2,
  Inbox,
  Loader2,
  MessageSquare,
  Radio,
  Wrench,
  XCircle,
} from "lucide-react"

export default function Tools() {
  // Schnell-Status: offene Fragen + aktive Operatoren
  const { data: pending } = useQuery({
    queryKey: ["agent-questions-pending"],
    queryFn: () => api.agentQuestions.pendingCount(),
    refetchInterval: 30000,
  })
  const { data: ops } = useQuery({
    queryKey: ["operators"],
    queryFn: () => api.operators.list(),
    refetchInterval: 30000,
  })

  const items = (ops?.items || []) as any[]
  const activeOps = items.filter((o) => o.agent_status === "active" || o.agent_status === "starting").length
  const staleOps = items.filter((o) => o.agent_status === "stale" || o.live_label === "stale").length
  const errorOps = items.filter((o) => o.agent_status === "error").length

  return (
    <div>
      <div className="page-header">
        <h1>
          <Wrench size={20} style={{ marginRight: 8, verticalAlign: "text-bottom" }} />
          Tools
        </h1>
        <p>Interaktion zwischen User und Agent &middot; Live-Operatoren</p>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: 16,
          marginTop: 16,
        }}
      >
        <ToolCard
          to="/tools"
          icon={<MessageSquare size={28} />}
          title="User Input Tool"
          subtitle="Agenten koennen dir Fragen stellen, du antwortest mit Text, Dateien oder Bildern."
          stat={
            pending
              ? `${pending.pending} offen${
                  pending.unseen > 0 ? `, ${pending.unseen} ungesehen` : ""
                }`
              : "—"
          }
          statColor={pending && pending.unseen > 0 ? "#f59e0b" : "var(--color-hermes-text-secondary, #999)"}
        />

        <ToolCard
          to="/tools"
          icon={<Radio size={28} />}
          title="Live-Operatoren"
          subtitle="Watchdog-Instanzen pro Live-Board. Ueberwachen haengende Tasks und fragen ggf. nach."
          stat={
            ops
              ? `${activeOps} aktiv${staleOps > 0 ? `, ${staleOps} stale` : ""}${
                  errorOps > 0 ? `, ${errorOps} fehler` : ""
                }`
              : "—"
          }
          statColor={
            errorOps > 0
              ? "#dc2626"
              : staleOps > 0
              ? "#f59e0b"
              : activeOps > 0
              ? "#10b981"
              : "var(--color-hermes-text-secondary, #999)"
          }
        />

        <ToolCard
          to="/sops"
          icon={<Activity size={28} />}
          title="SOP-Designer"
          subtitle="Regelprozesse definieren — mit Schritten, Tools-Whitelist, RACI und KI-Support."
          stat="Oeffnen"
          statColor="var(--color-hermes-accent, #7c3aed)"
        />
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h3 style={{ marginTop: 0 }}>
          <Inbox size={16} style={{ marginRight: 6, verticalAlign: "text-bottom" }} />
          Hinweise
        </h3>
        <ul style={{ fontSize: 13, lineHeight: 1.6, color: "var(--color-hermes-text-secondary, #999)" }}>
          <li>
            <strong>User Input Tool</strong>: Agenten jeder Ebene (C-Level, Worker, Subagent) koennen via
            <code> POST /api/tools/agent-questions/</code> Fragen stellen. Du siehst sie hier in Echtzeit
            (Polling 5s) und antwortest mit Text, Dateien (Drag & Drop) oder Bildern.
          </li>
          <li>
            <strong>Live-Operatoren</strong>: Sobald ein Board auf <code>mode=live</code> steht,
            startet automatisch eine eigenstaendige Watchdog-Instanz. Sie sendet alle 5s einen Heartbeat
            und prueft alle 30s die Tasks des Boards auf haengende States
            (<code>in_progress</code> &gt; 30min, <code>rueckfrage</code> &gt; 30min, etc.).
            Bei Bedarf erstellt sie selbst eine User-Frage.
          </li>
          <li>
            <strong>Live-Icon</strong>: Im Board-Header siehst du den Live-Status (gruen = Heartbeat
            &lt; 15s, gelb = stale, rot = error). Das Icon leuchtet nur dann gruen, wenn die
            Watchdog-Instanz tatsaechlich laeuft.
          </li>
        </ul>
      </div>
    </div>
  )
}

function ToolCard({ to, icon, title, subtitle, stat, statColor }: {
  to: string
  icon: React.ReactNode
  title: string
  subtitle: string
  stat: string
  statColor: string
}) {
  return (
    <Link
      to={to}
      style={{
        display: "block",
        background: "var(--color-hermes-bg-card, #1a1a1a)",
        border: "1px solid var(--color-hermes-border, #333)",
        borderRadius: 8,
        padding: 20,
        textDecoration: "none",
        color: "var(--color-hermes-text, #e5e5e5)",
        transition: "all 0.15s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = "var(--color-hermes-accent, #7c3aed)"
        e.currentTarget.style.transform = "translateY(-2px)"
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "var(--color-hermes-border, #333)"
        e.currentTarget.style.transform = "translateY(0)"
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <div
          style={{
            background: "rgba(124, 58, 237, 0.1)",
            color: "var(--color-hermes-accent, #7c3aed)",
            padding: 12,
            borderRadius: 8,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {icon}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 4 }}>{title}</div>
          <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary, #999)", lineHeight: 1.4 }}>
            {subtitle}
          </div>
        </div>
      </div>
      <div
        style={{
          marginTop: 12,
          paddingTop: 12,
          borderTop: "1px solid var(--color-hermes-border, #333)",
          fontSize: 13,
          color: statColor,
          fontWeight: 600,
        }}
      >
        {stat}
      </div>
    </Link>
  )
}

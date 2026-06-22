// AgentModelDisplay.tsx — Read-only Anzeige des Modells eines SubAgents
//
// User-Direktive 22.06.2026: Im SOP-Step-Editor wird das Modell NICHT mehr ausgewaehlt,
// sondern aus der gewaehlten SubAgent-Konfiguration uebernommen und nur angezeigt.
// Aenderung des Modells erfolgt ausschliesslich in der SubAgent-Ansicht.

import { useQuery } from "@tanstack/react-query"
import { api } from "../api"

export interface AgentOption {
  name: string
  role_type?: string
  is_subagent: boolean
  emoji?: string
  model?: string
  provider?: string
  default_model?: string
}

export interface AgentModelDisplayProps {
  agent: string
  style?: React.CSSProperties
}

/**
 * Read-only Anzeige des Modells eines SubAgents.
 *
 * Render-Varianten:
 * 1. `agent` ist leer / "system" / "user"        → "⚙️ System-Aktion" / "👤 User-Aktion"
 * 2. `agent` nicht in SubAgent-Configs gefunden   → Warnung (rot)
 * 3. SubAgent ohne `model` und `default_model`    → Hinweis (gelb)
 * 4. Normalfall                                    → `provider/model` als Code
 */
export function AgentModelDisplay({ agent, style }: AgentModelDisplayProps) {
  const { data } = useQuery({
    queryKey: ["subagent-configs"],
    queryFn: () => api.subagents.listConfigs(),
    staleTime: 60_000,
  })
  const configs: AgentOption[] = (data as any) || []

  // Basis-Styles fuer alle Anzeigevarianten
  const baseStyle: React.CSSProperties = {
    ...style,
    fontSize: 11,
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "4px 8px",
    border: "1px solid var(--color-hermes-border)",
    borderRadius: 4,
    cursor: "help",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  }

  // Variante 1: System / User-Aktion (kein LLM-Aufruf)
  if (!agent || agent === "system" || agent === "user") {
    const isSystem = agent === "system"
    return (
      <div
        className="input"
        data-testid="agent-model-display"
        data-variant={isSystem ? "system" : "user"}
        style={{
          ...baseStyle,
          background: "var(--color-hermes-bg-secondary)",
          color: "var(--color-hermes-text-secondary)",
          fontStyle: "italic",
        }}
        title={isSystem ? "System-Aktion (kein LLM-Aufruf)" : "User-Aktion (manuell)"}
      >
        <span>{isSystem ? "⚙️" : "👤"}</span>
        <span>{isSystem ? "System-Aktion — kein Modell" : "User-Aktion — manuell"}</span>
      </div>
    )
  }

  // Variante 2: Agent nicht in SubAgent-Konfigurationen gefunden
  const cfg = configs.find((c) => c.name === agent)
  if (!cfg) {
    return (
      <div
        className="input"
        data-testid="agent-model-display"
        data-variant="unknown"
        style={{
          ...baseStyle,
          background: "rgba(239, 68, 68, 0.08)",
          color: "var(--color-hermes-danger, #ef4444)",
          borderColor: "var(--color-hermes-danger, #ef4444)",
        }}
        title={`Agent "${agent}" wurde nicht in den SubAgent-Konfigurationen gefunden. Bitte in SubAgenten anlegen.`}
      >
        <span>⚠️</span>
        <span>Agent unbekannt — SubAgent-Konfiguration fehlt</span>
      </div>
    )
  }

  // Variante 3: SubAgent vorhanden, aber kein Modell konfiguriert
  const modelName = cfg.model || cfg.default_model || ""
  const providerName = cfg.provider || ""
  const fullName = providerName && modelName ? `${providerName}/${modelName}` : modelName

  if (!fullName) {
    return (
      <div
        className="input"
        data-testid="agent-model-display"
        data-variant="no-model"
        style={{
          ...baseStyle,
          background: "rgba(245, 158, 11, 0.08)",
          color: "var(--color-hermes-warning, #f59e0b)",
          borderColor: "rgba(245, 158, 11, 0.4)",
        }}
        title={`SubAgent "${agent}" hat kein Modell konfiguriert. Bitte in SubAgenten ergaenzen.`}
      >
        <span>🟡</span>
        <span>Kein Modell in SubAgent konfiguriert</span>
      </div>
    )
  }

  // Variante 4: Normalfall — Modell wird read-only angezeigt
  return (
    <div
      className="input"
      data-testid="agent-model-display"
      data-variant="model"
      data-model={fullName}
      data-is-subagent={cfg.is_subagent}
      style={{
        ...baseStyle,
        background: "var(--color-hermes-bg-secondary)",
        color: "var(--color-hermes-text)",
      }}
      title={`Modell wird automatisch aus SubAgent-Konfiguration uebernommen. Aenderung in SubAgenten vornehmen.`}
    >
      <span style={{ fontSize: 10 }}>🧠</span>
      <code style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{fullName}</code>
      {!cfg.is_subagent && (
        <span
          style={{
            fontSize: 9,
            color: "var(--color-hermes-text-secondary)",
            marginLeft: 2,
            padding: "0 4px",
            background: "var(--color-hermes-bg)",
            borderRadius: 3,
          }}
        >
          Org
        </span>
      )}
    </div>
  )
}
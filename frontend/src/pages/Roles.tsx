import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "../api"
import { Check, X, Send } from "lucide-react"

const FALLBACK_EMOJI: Record<string, string> = {
  "pi-coder": "💻", "pi-tester": "🧪", "pi-reviewer": "👁️", "pi-fixer": "🔧",
  "CEO-digital": "👑", "CIO": "🏗️", "CMO": "📢", "CFO": "💰",
}

type Role = {
  id?: string
  name: string
  emoji?: string
  description?: string
  role_type: "sub_agent" | "org"
  provider?: string
  model?: string
  system_prompt?: string
  tool_whitelist?: string[]
  timeout_sec?: number
  fresh_context?: boolean
  estimated_savings_usd?: number
}

function borderColorForOrg(role: Role): string {
  // CEO-digital: gold. Ollama-Modelle: gruen. Sonst: blau.
  if (role.name === "CEO-digital") return "gold"
  if (role.provider === "ollama") return "var(--color-hermes-accent)"
  return "var(--color-hermes-accent-blue)"
}

function borderColorForSub(role: Role): string {
  if (role.provider === "ollama") return "var(--color-hermes-accent)"
  return "var(--color-hermes-danger)"
}

function providerBadgeClass(provider?: string): string {
  return provider === "ollama" ? "badge-green" : "badge-blue"
}

export default function Roles() {
  const { data: orgData, isLoading: l1 } = useQuery({
    queryKey: ["org-roles"],
    queryFn: () => api.listOrgRoles(),
  })
  const { data: subData, isLoading: l2 } = useQuery({
    queryKey: ["sub-roles"],
    queryFn: () => api.listSubAgents(),
  })

  const orgRoles: Role[] = (orgData as any)?.items || []
  const subAgents: Role[] = (subData as any)?.items || []

  if (l1 || l2) {
    return (
      <div style={{ color: "var(--color-hermes-text-secondary)" }}>
        Lade Rollen...
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1>Rollen</h1>
        <p>Sub-Agenten (swarm-spawner) + Organisationale Rollen</p>
      </div>

      {/* === Sektion 1: Organisationale Rollen === */}
      <div className="page-header" style={{ marginBottom: 12 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>
          🏢 Organisationale Rollen
        </h2>
        <p>Strategische Perspektiven für den PI Agent (CEO-digital, CIO, CMO, CFO)</p>
      </div>
      <div className="card-grid" style={{ marginBottom: 24 }}>
        {orgRoles.map((role) => (
          <div
            key={role.id || role.name}
            className="card"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 8,
              borderTop: `3px solid ${borderColorForOrg(role)}`,
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <span style={{ fontSize: 24, lineHeight: 1 }}>
                {role.emoji || FALLBACK_EMOJI[role.name] || "🏢"}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 16 }}>{role.name}</div>
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--color-hermes-accent-orange)",
                    marginTop: 1,
                    lineHeight: 1.4,
                  }}
                >
                  {role.description}
                </div>
              </div>
              <span className={`badge ${providerBadgeClass(role.provider)}`}>
                {role.provider}/{role.model}
              </span>
            </div>
            <details>
              <summary
                style={{
                  cursor: "pointer",
                  fontSize: 13,
                  fontWeight: 500,
                  color: "var(--color-hermes-accent-blue)",
                }}
              >
                ▸ System Prompt
              </summary>
              <pre
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  margin: "8px 0 0",
                  color: "var(--color-hermes-text-secondary)",
                  maxHeight: 200,
                  overflow: "auto",
                  lineHeight: 1.4,
                  padding: 8,
                  background: "var(--color-hermes-muted)",
                  borderRadius: 4,
                }}
              >
                {role.system_prompt || "(kein System Prompt hinterlegt)"}
              </pre>
            </details>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {(role.tool_whitelist || []).map((t) => (
                <span key={t} className="badge badge-blue">
                  {t}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* === Sektion 2: Sub-Agenten (swarm-spawner) === */}
      <div className="page-header" style={{ marginBottom: 12 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>
          🤖 Sub-Agenten (swarm-spawner)
        </h2>
        <p>
          {subAgents.length} Rollen die als Subprozesse mit ollama/gemma4:12b laufen
        </p>
      </div>
      <div className="card-grid" style={{ marginBottom: 24 }}>
        {subAgents.map((role) => (
          <div
            key={role.id || role.name}
            className="card"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 10,
              borderTop: `3px solid ${borderColorForSub(role)}`,
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <span style={{ fontSize: 24, lineHeight: 1 }}>
                {role.emoji || FALLBACK_EMOJI[role.name] || "🤖"}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 16 }}>{role.name}</div>
                <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap" }}>
                  <span className={`badge ${providerBadgeClass(role.provider)}`}>
                    {role.provider}/{role.model}
                  </span>
                  <span className="badge badge-blue">{role.timeout_sec}s</span>
                </div>
              </div>
            </div>
            <div
              style={{
                padding: "6px 8px",
                borderRadius: 6,
                fontSize: 12,
                background:
                  role.provider === "ollama"
                    ? "rgba(46,160,67,0.08)"
                    : "rgba(248,81,73,0.08)",
                color:
                  role.provider === "ollama"
                    ? "var(--color-hermes-accent)"
                    : "var(--color-hermes-danger)",
              }}
            >
              {role.provider === "ollama"
                ? "🆓 Lokal (0 Token-Kosten)"
                : "💰 MiniMax (kostenpflichtig)"}
              {(role.estimated_savings_usd ?? 0) > 0 && (
                <span> · ~${role.estimated_savings_usd!.toFixed(2)}/call</span>
              )}
            </div>
            <details>
              <summary
                style={{
                  cursor: "pointer",
                  fontSize: 13,
                  fontWeight: 500,
                  color: "var(--color-hermes-accent-blue)",
                }}
              >
                ▸ System Prompt
              </summary>
              <pre
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  margin: "8px 0 0",
                  color: "var(--color-hermes-text-secondary)",
                  maxHeight: 200,
                  overflow: "auto",
                  lineHeight: 1.4,
                  padding: 8,
                  background: "var(--color-hermes-muted)",
                  borderRadius: 4,
                }}
              >
                {role.system_prompt || "(kein System Prompt hinterlegt)"}
              </pre>
            </details>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {(role.tool_whitelist || []).map((t) => (
                <span key={t} className="badge badge-blue">
                  {t}
                </span>
              ))}
            </div>
            <div
              style={{
                fontSize: 12,
                display: "flex",
                gap: 12,
                color: "var(--color-hermes-text-secondary)",
              }}
            >
              <span>
                Fresh:{" "}
                {role.fresh_context ? (
                  <Check
                    size={12}
                    color="var(--color-hermes-accent)"
                    style={{ display: "inline", verticalAlign: -1 }}
                  />
                ) : (
                  <X
                    size={12}
                    color="var(--color-hermes-text-secondary)"
                    style={{ display: "inline", verticalAlign: -1 }}
                  />
                )}
              </span>
              <span>Timeout: {role.timeout_sec}s</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

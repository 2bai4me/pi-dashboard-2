import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "../api"
import {
  Lightbulb, TrendingUp, BookOpen, ExternalLink, CheckCircle,
  ArrowRight, Wrench, ListChecks, Brain,
} from "lucide-react"

type Framework = {
  name: string
  stars?: string
  description?: string
  url?: string
  approach?: string
  key_insight?: string
  applicable?: boolean
  rationale?: string
}

type Phase = {
  phase: number
  name: string
  description?: string
  implementation?: string
  effort?: string
  impact?: string
  packages?: string
}

const PHASE_COLORS: Record<number, string> = {
  1: "var(--color-hermes-accent)",         // grün
  2: "var(--color-hermes-accent-blue)",   // blau
  3: "var(--color-hermes-accent-orange)", // orange
  4: "var(--color-hermes-danger)",        // rot
  5: "var(--color-hermes-text-secondary)", // grau
}

const PHASE_BADGE_CLASS: Record<number, string> = {
  1: "badge-green",
  2: "badge-blue",
  3: "badge-orange",
  4: "badge-blue",
  5: "badge-gray",
}

export default function SelfImprovement() {
  const [activeFramework, setActiveFramework] = useState<string | null>(null)
  const [activePhase, setActivePhase] = useState<number | null>(null)

  const { data: frameworks, isLoading } = useQuery({
    queryKey: ["selfimprovement-frameworks"],
    queryFn: () => api.listSelfImprovementFrameworks(),
  })

  const { data: strategy } = useQuery({
    queryKey: ["selfimprovement-strategy"],
    queryFn: () => api.getSelfImprovementStrategy(),
  })

  if (isLoading) {
    return (
      <div style={{ color: "var(--color-hermes-text-secondary)" }}>
        Lade Self-Improvement-Recherche...
      </div>
    )
  }

  const fwList: Framework[] = frameworks || []
  const phases: Phase[] = strategy?.phases || []

  return (
    <div>
      <div className="page-header">
        <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Lightbulb size={20} color="var(--color-hermes-accent-orange)" />
          Self-Improvement
        </h1>
        <p>Research & strategy for making PI Agent smarter over time</p>
      </div>

      {/* === Strategy Overview === */}
      <div
        className="card"
        style={{
          marginBottom: 24,
          borderLeft: "3px solid var(--color-hermes-accent)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <TrendingUp size={16} color="var(--color-hermes-accent)" />
          <span style={{ fontWeight: 600 }}>
            {strategy?.title || "Pi Agent Self-Improvement Strategy"}
          </span>
        </div>
        <p
          style={{
            fontSize: 13,
            color: "var(--color-hermes-text-secondary)",
            margin: 0,
            lineHeight: 1.6,
          }}
        >
          Basierend auf Recherche von{" "}
          <strong>10+ aktiven Projekten</strong> (GenericAgent 12.8K ★, AutoAgent
          9.3K ★, EvoAgentX 3K ★, Agent0 1.2K ★, AgentEvolver 1K ★, Huxley-Gödel
          Machine ICLR 2026, Lumos, Midas Agent, SII CLI, DGM) und{" "}
          <strong>9+ Papers</strong> (ExpeL, Agent0, EvoAgentX, DGM, HGM,
          GenericAgent, AutoAgent, Survey on Self-Evolving Agents).
        </p>
      </div>

      {/* === Action Plan (Phases) === */}
      {strategy && phases.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div className="page-header" style={{ marginBottom: 12 }}>
            <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Action Plan</h2>
            <p>Recommended phases for implementing self-improvement</p>
          </div>
          <div className="card-grid">
            {phases.map((phase) => (
              <div
                key={phase.phase}
                className="card"
                style={{
                  cursor: "pointer",
                  borderLeft: `3px solid ${PHASE_COLORS[phase.phase] ?? "var(--color-hermes-text-secondary)"}`,
                }}
                onClick={() => setActivePhase(activePhase === phase.phase ? null : phase.phase)}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <span className={`badge ${PHASE_BADGE_CLASS[phase.phase] ?? "badge-blue"}`}>
                    Phase {phase.phase}
                  </span>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{phase.name}</span>
                </div>
                <p
                  style={{
                    fontSize: 12,
                    color: "var(--color-hermes-text-secondary)",
                    margin: "4px 0",
                    lineHeight: 1.5,
                  }}
                >
                  {(phase.description || "").slice(0, 120)}...
                </p>
                <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                  ⏱ {phase.effort} · 📈 {phase.impact}
                </div>

                {activePhase === phase.phase && (
                  <div
                    style={{
                      marginTop: 10,
                      padding: 8,
                      background: "var(--color-hermes-muted)",
                      borderRadius: 6,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 4, fontWeight: 500, fontSize: 12, marginBottom: 4 }}>
                      <ListChecks size={12} /> Implementation
                    </div>
                    <p
                      style={{
                        fontSize: 11,
                        color: "var(--color-hermes-text-secondary)",
                        margin: 0,
                        lineHeight: 1.5,
                      }}
                    >
                      {phase.implementation}
                    </p>
                    {phase.packages && (
                      <div
                        style={{
                          fontSize: 10,
                          color: "var(--color-hermes-text-secondary)",
                          marginTop: 6,
                          display: "flex",
                          alignItems: "flex-start",
                          gap: 4,
                        }}
                      >
                        <Wrench size={10} style={{ marginTop: 2, flexShrink: 0 }} />
                        <span><strong>Packages:</strong> {phase.packages}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
          {strategy.recommended_start && (
            <div
              className="card"
              style={{
                marginTop: 12,
                borderLeft: "3px solid var(--color-hermes-accent)",
                background: "rgba(46,160,67,0.05)",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <CheckCircle size={14} color="var(--color-hermes-accent)" />
              <span style={{ fontSize: 13 }}>{strategy.recommended_start}</span>
            </div>
          )}
        </div>
      )}

      {/* === Framework Research === */}
      <div style={{ marginBottom: 24 }}>
        <div className="page-header" style={{ marginBottom: 12 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Framework Research</h2>
          <p>{fwList.length} self-improving agent frameworks analyzed</p>
        </div>

        <div className="card-grid">
          {fwList.map((fw) => (
            <div
              key={fw.name}
              className="card"
              style={{
                cursor: "pointer",
                borderTop: `3px solid ${fw.applicable ? "var(--color-hermes-accent)" : "var(--color-hermes-text-secondary)"}`,
                opacity: fw.applicable ? 1 : 0.6,
              }}
              onClick={() => setActiveFramework(activeFramework === fw.name ? null : fw.name)}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 4,
                }}
              >
                <span style={{ fontWeight: 600, fontSize: 14 }}>{fw.name}</span>
                <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <span className={`badge ${fw.applicable ? "badge-green" : "badge-orange"}`}>
                    {fw.applicable ? "✓ Applicable" : "Research"}
                  </span>
                  {fw.stars && (
                    <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                      ★{fw.stars}
                    </span>
                  )}
                </div>
              </div>

              <p
                style={{
                  fontSize: 12,
                  color: "var(--color-hermes-text-secondary)",
                  margin: "4px 0",
                  lineHeight: 1.4,
                }}
              >
                {fw.description}
              </p>

              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {fw.url && (
                  <a
                    href={fw.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      fontSize: 11,
                      color: "var(--color-hermes-accent-blue)",
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <ExternalLink size={10} /> GitHub
                  </a>
                )}
                <ArrowRight size={10} color="var(--color-hermes-text-secondary)" />
              </div>

              {activeFramework === fw.name && (
                <div
                  style={{
                    marginTop: 8,
                    padding: 8,
                    background: "var(--color-hermes-muted)",
                    borderRadius: 6,
                    fontSize: 11,
                    lineHeight: 1.5,
                  }}
                >
                  <div style={{ marginBottom: 4 }}>
                    <strong>Approach:</strong> {fw.approach}
                  </div>
                  <div style={{ marginBottom: 4 }}>
                    <strong>Key Insight:</strong> {fw.key_insight}
                  </div>
                  <div
                    style={{
                      padding: "4px 6px",
                      borderRadius: 4,
                      background: fw.applicable ? "rgba(46,160,67,0.1)" : "rgba(210,153,34,0.1)",
                      marginTop: 4,
                    }}
                  >
                    <strong>Rationale:</strong> {fw.rationale}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* === Key Papers === */}
      {strategy?.key_papers && (
        <div className="card">
          <h3
            style={{
              fontSize: 14,
              fontWeight: 600,
              margin: "0 0 8px",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <BookOpen size={14} /> Key Papers
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {strategy.key_papers.map((p: any, i: number) => (
              <a
                key={i}
                href={p.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontSize: 12,
                  color: "var(--color-hermes-accent-blue)",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "4px 0",
                }}
              >
                <ExternalLink size={10} /> {p.title}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Hidden hint: Brain-Symbol für Self-Improvement Memory */}
      <div style={{ display: "none" }}>
        <Brain />
      </div>
    </div>
  )
}

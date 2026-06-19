// SopStepToolSelector.tsx — Tool-Auswahl im SOP-Step-Editor
//
// User-Direktive 17.06.2026:
//   Direkt unter den KI-Anweisungen kann der User pro Step festlegen,
//   welche Tools der Agent bei der Bearbeitung nutzen darf.
//
// Aktuell verfuegbar:
//   - user_input: User-Input-Tool (voll funktional, blockierend)
//
// Geplant (Platzhalter):
//   - mcp_browser, shell_exec, file_read, file_write, web_search, sql_query
//
// Wird in Sops.tsx im StepEditor eingebettet, unterhalb der KI-Anweisungen.

import { useState } from "react"
import { SopInputToolConfigurator } from "./SopInputToolConfigurator"
import {
  CheckCircle2, MessageSquare, Globe, Terminal, FileText, FileEdit, Search, Database,
  Wrench, ChevronDown, ChevronRight, Sparkles, AlertCircle, Info, Lock,
} from "lucide-react"

// Verfuegbare Tools (statisch definiert, spaeter dynamisch)
const AVAILABLE_TOOLS = [
  {
    id: "user_input",
    name: "User-Input",
    description: "Agent stellt eine Frage an den User und wartet BLOCKIEREND auf die Antwort.",
    icon: MessageSquare,
    color: "#7c3aed",
    implemented: true,
    configKey: "input_tool_required",
  },
  {
    id: "mcp_browser",
    name: "MCP-Browser",
    description: "Web-Browser-Zugriff via MCP (oeffentliche Webseiten, Recherche, Screenshots).",
    icon: Globe,
    color: "#3b82f6",
    implemented: false,
  },
  {
    id: "shell_exec",
    name: "Shell (Bash)",
    description: "Command-Line-Ausfuehrung (sicherheitsrelevant — nur in Dev-Umgebung).",
    icon: Terminal,
    color: "#f59e0b",
    implemented: false,
  },
  {
    id: "file_read",
    name: "File Read",
    description: "Liest Dateien aus dem Projekt-Verzeichnis (read-only).",
    icon: FileText,
    color: "#10b981",
    implemented: false,
  },
  {
    id: "file_write",
    name: "File Write",
    description: "Schreibt/erstellt Dateien im Projekt-Verzeichnis (Vorsicht: ueberschreibt).",
    icon: FileEdit,
    color: "#dc2626",
    implemented: false,
  },
  {
    id: "web_search",
    name: "Web-Suche",
    description: "Sucht im Web nach aktuellen Informationen (via Ollama/SearXNG).",
    icon: Search,
    color: "#06b6d4",
    implemented: false,
  },
  {
    id: "sql_query",
    name: "SQL-Query",
    description: "Liest Daten aus der Datenbank (read-only, strukturierte Queries).",
    icon: Database,
    color: "#a855f7",
    implemented: false,
  },
] as const

interface Props {
  sopId: string
  stepId: string
  step: {
    id: string
    name: string
    agent: string
    input_tool_required?: boolean
    input_tool_type?: string | null
    input_tool_prompt?: string | null
    input_tool_description?: string | null
    input_tool_recommendation?: string | null
    input_tool_options?: string | null
    input_tool_options_config?: string | null
    input_tool_context_key?: string | null
  }
}

export function SopStepToolSelector({ sopId, stepId, step }: Props) {
  // Welches Tool ist aufgeklappt (nur eines gleichzeitig)
  const [openToolId, setOpenToolId] = useState<string | null>(
    step.input_tool_required ? "user_input" : null
  )

  return (
    <div
      style={{
        background: "rgba(0,0,0,0.2)",
        border: "1px solid var(--color-hermes-border, #333)",
        borderRadius: 6,
        padding: 12,
        marginTop: 12,
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
        <Wrench size={14} color="var(--color-hermes-accent, #7c3aed)" />
        <strong style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5 }}>
          Agent-Tools
        </strong>
        <span style={{ fontSize: 10, color: "#999", marginLeft: "auto" }}>
          Welche Tools darf der Agent ({step.agent}) nutzen?
        </span>
      </div>

      {/* Tool-Liste */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {AVAILABLE_TOOLS.map((tool) => {
          const Icon = tool.icon
          const isOpen = openToolId === tool.id
          const isActive = tool.id === "user_input" ? !!step.input_tool_required : false
          return (
            <div
              key={tool.id}
              style={{
                background: isOpen ? "rgba(124, 58, 237, 0.1)" : "rgba(0,0,0,0.2)",
                border: `1px solid ${isOpen ? "var(--color-hermes-accent, #7c3aed)" : "#333"}`,
                borderRadius: 4,
                overflow: "hidden",
              }}
            >
              {/* Tool-Header */}
              <div
                onClick={() => setOpenToolId(isOpen ? null : tool.id)}
                style={{
                  display: "flex", alignItems: "center", gap: 8, padding: "8px 10px",
                  cursor: "pointer",
                }}
              >
                <Icon size={14} color={isActive ? tool.color : "#999"} />
                <strong style={{ fontSize: 12, flex: 1 }}>{tool.name}</strong>
                {isActive && (
                  <span style={{
                    background: tool.color, color: "#fff", fontSize: 9, padding: "1px 6px",
                    borderRadius: 3, fontWeight: 600, textTransform: "uppercase",
                  }}>
                    aktiv
                  </span>
                )}
                {!tool.implemented && (
                  <span style={{
                    background: "rgba(245, 158, 11, 0.2)", color: "#f59e0b",
                    fontSize: 9, padding: "1px 6px", borderRadius: 3,
                    border: "1px solid #f59e0b",
                  }}>
                    bald
                  </span>
                )}
                {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              </div>

              {/* Tool-Description (immer sichtbar wenn aktiv, sonst einklappbar) */}
              {!isOpen && (
                <div style={{ fontSize: 10, color: "#999", padding: "0 10px 8px 32px", lineHeight: 1.4 }}>
                  {tool.description}
                </div>
              )}

              {/* Tool-Config (aufgeklappt) */}
              {isOpen && (
                <div style={{ padding: "0 10px 10px 10px", borderTop: "1px solid #333" }}>
                  <div style={{ fontSize: 10, color: "#999", marginTop: 8, marginBottom: 8, lineHeight: 1.4 }}>
                    {tool.description}
                  </div>
                  {tool.implemented ? (
                    tool.id === "user_input" ? (
                      <SopInputToolConfigurator
                        sopId={sopId}
                        stepId={stepId}
                        step={step}
                        embedded
                      />
                    ) : (
                      <div style={{ color: "#999", fontSize: 11 }}>Konfig folgt</div>
                    )
                  ) : (
                    <div style={{
                      background: "rgba(245, 158, 11, 0.05)", border: "1px solid rgba(245, 158, 11, 0.3)",
                      borderRadius: 4, padding: 10, fontSize: 11, color: "#f59e0b",
                    }}>
                      <Info size={11} style={{ marginRight: 4, verticalAlign: "text-bottom" }} />
                      Dieses Tool ist noch nicht implementiert. Es wird in einer spaeteren Iteration verfuegbar.
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div style={{ fontSize: 10, color: "#999", marginTop: 8, lineHeight: 1.4 }}>
        <Info size={10} style={{ marginRight: 4, verticalAlign: "text-bottom" }} />
        Hinweis: Pro Step koennen mehrere Tools aktiviert werden. Der Agent nutzt nur die hier erlaubten Tools.
      </div>
    </div>
  )
}

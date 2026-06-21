import { NavLink } from "react-router-dom";
import {
  Activity,
  Beaker,
  BookOpen,
  Brain,
  ChevronDown,
  ChevronRight,
  Cpu,
  Bot,
  Sparkles,
  DollarSign,
  FileCode2,
  GitBranch,
  FileText,
  Key,
  LayoutDashboard,
  Lightbulb,
  MessagesSquare,
  Network,
  Puzzle,
  Server,
  Settings2,
  Shield,
  Terminal,
  Wrench,
  Workflow,
} from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { GatewayStatusBar } from "./GatewayStatusBar";

const NAV_ITEMS = [
  { section: "Overview", items: [
    { to: "/status", label: "Status", icon: LayoutDashboard },
    { to: "/system", label: "System", icon: Server },
    { to: "/kanban", label: "Projekte", icon: LayoutDashboard },
    { to: "/sops", label: "SOP", icon: BookOpen },
    { to: "/raci", label: "Config", icon: FileCode2 },
    { to: "/performance", label: "Performance", icon: Activity },
    { to: "/selfimprovment", label: "Selfimprovment", icon: FileCode2 },
  ]},
  { section: "Agent", items: [
    { to: "/sessions", label: "Sessions", icon: MessagesSquare },
    { to: "/terminal", label: "Terminal", icon: Terminal },
    { to: "/models", label: "Models", icon: Cpu },
    { to: "/subagents", label: "SubAgents", icon: Bot },
    { to: "/tasks/draft", label: "Task-Drafts", icon: Sparkles },
    { to: "/tools", label: "Tools", icon: Wrench },
    { to: "/skills", label: "Skills", icon: BookOpen },
    { to: "/test-runner", label: "Test Tool", icon: Beaker },
  ]},
  { section: "Management", items: [
    { to: "/config", label: "Config", icon: Settings2 },
    { to: "/process", label: "Prozesse (BPMN)", icon: GitBranch },
    { to: "/cron", label: "Cron Jobs", icon: Activity },
    { to: "/mcp", label: "MCP", icon: Network },
    { to: "/extensions", label: "Extensions", icon: Puzzle },
    { to: "/cost", label: "Cost & Usage", icon: DollarSign },
    { to: "/logs", label: "Logs", icon: FileText },
    { to: "/webhooks", label: "Webhooks", icon: Activity },
  ]},
  { section: "Growth", items: [
    { to: "/self-improve", label: "Self-Improve", icon: Lightbulb },
  ]},
  { section: "Integrations", items: [
    { to: "/api-keys", label: "API Keys", icon: Key },
    { to: "/openbrain", label: "OpenBrain", icon: Brain },
    { to: "/brain-graph", label: "Brain Graph", icon: Workflow },
  ]},
];

export function Layout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  // Ungesehene AgentQuestions fuer Badge im Tools-NavLink
  const { data: pending } = useQuery({
    queryKey: ["agent-questions-pending"],
    queryFn: () => api.agentQuestions.pendingCount(),
    refetchInterval: 5000,
  });
  const unseenCount = pending?.unseen ?? 0;

  function toggleSection(section: string) {
    setCollapsed((prev) => ({ ...prev, [section]: !prev[section] }));
  }

  return (
    <div className="dashboard-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <Cpu size={18} color="var(--color-hermes-accent-blue)" />
          <span>Pi Dashboard 2.0</span>
        </div>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map((section) => {
            const isCollapsed = collapsed[section.section];
            return (
              <div key={section.section}>
                <div
                  className="sidebar-section-title"
                  onClick={() => toggleSection(section.section)}
                  style={{ cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", userSelect: "none" }}
                >
                  <span>{section.section}</span>
                  {isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
                </div>
                {!isCollapsed && section.items.map((item) => {
                  // Badge nur fuer /tools mit ungesehenen Fragen
                  const badge = item.to === "/tools" && unseenCount > 0 ? unseenCount : null
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      className={({ isActive }) =>
                        `sidebar-link${isActive ? " active" : ""}`
                      }
                    >
                      <item.icon size={16} />
                      <span style={{ flex: 1 }}>{item.label}</span>
                      {badge !== null && (
                        <span
                          style={{
                            background: "#f59e0b",
                            color: "#000",
                            borderRadius: 10,
                            padding: "0 6px",
                            fontSize: 10,
                            fontWeight: 700,
                            minWidth: 18,
                            textAlign: "center",
                          }}
                          title={`${unseenCount} ungesehene User-Input-Fragen`}
                        >
                          {badge}
                        </span>
                      )}
                    </NavLink>
                  )
                })}
              </div>
            );
          })}
        </nav>

        <div style={{ flex: 1 }} />
      </aside>

      <main className="main-content">
        <GatewayStatusBar />
        <div style={{ padding: 24, flex: 1, overflowY: "auto" }}>
          {children}
        </div>
      </main>
    </div>
  );
}

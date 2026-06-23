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
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { GatewayStatusBar } from "./GatewayStatusBar";
import { useDevSettings } from "./DevSettingsContext";

const NAV_ITEMS = [
  { section: "Overview", items: [
    { to: "/status", label: "Status", icon: LayoutDashboard },
    { to: "/system", label: "System", icon: Server },
    { to: "/idee", label: "Idee", icon: Lightbulb },
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
    { to: "/openbrain", label: "OpenBrain", icon: Brain },
    { to: "/brain-graph", label: "Brain Graph", icon: Workflow },
  ]},
];

function DevRolloverTooltip() {
  const { showElementRollover } = useDevSettings();
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number; visible: boolean }>({
    text: "", x: 0, y: 0, visible: false,
  });
  const tooltipRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!showElementRollover) return;

    function getName(target: HTMLElement): string | null {
      const el = target.closest("[data-name], [data-route], [data-label]") as HTMLElement | null;
      if (!el) return null;
      return el.dataset.name || el.dataset.route || el.dataset.label || null;
    }

    function onMouseOver(e: MouseEvent) {
      const text = getName(e.target as HTMLElement);
      if (text) {
        setTooltip((prev) => ({ ...prev, text, visible: true }));
      }
    }

    function onMouseOut(e: MouseEvent) {
      const text = getName(e.relatedTarget as HTMLElement);
      if (!text) {
        setTooltip((prev) => ({ ...prev, visible: false }));
      } else {
        setTooltip((prev) => ({ ...prev, text, visible: true }));
      }
    }

    function onMouseMove(e: MouseEvent) {
      setTooltip((prev) => ({
        ...prev,
        x: e.clientX + 12,
        y: e.clientY + 12,
      }));
    }

    document.addEventListener("mouseover", onMouseOver);
    document.addEventListener("mouseout", onMouseOut);
    document.addEventListener("mousemove", onMouseMove);
    return () => {
      document.removeEventListener("mouseover", onMouseOver);
      document.removeEventListener("mouseout", onMouseOut);
      document.removeEventListener("mousemove", onMouseMove);
    };
  }, [showElementRollover]);

  if (!showElementRollover || !tooltip.visible) return null;

  return (
    <div
      ref={tooltipRef}
      style={{
        position: "fixed",
        left: tooltip.x,
        top: tooltip.y,
        zIndex: 9999,
        background: "rgba(0,0,0,0.85)",
        color: "#fff",
        border: "1px solid var(--color-hermes-accent, #7c3aed)",
        borderRadius: 4,
        padding: "4px 8px",
        fontSize: 11,
        pointerEvents: "none",
        whiteSpace: "nowrap",
        boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
      }}
    >
      {tooltip.text}
    </div>
  );
}

export function Layout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const { showVariableNames } = useDevSettings();

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
    <>
      <DevRolloverTooltip />
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
                      data-route={item.to}
                      data-label={item.label}
                      data-name={item.label}
                      className={({ isActive }) =>
                        `sidebar-link${isActive ? " active" : ""}`
                      }
                    >
                      <item.icon size={16} />
                      <span style={{ flex: 1, display: "flex", flexDirection: "column" }}>
                        <span>{item.label}</span>
                        {showVariableNames && (
                          <span style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)", opacity: 0.7 }}>
                            {item.to}
                          </span>
                        )}
                      </span>
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
    </>
  );
}

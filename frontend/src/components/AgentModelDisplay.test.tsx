// Tests fuer AgentModelDisplay — 4 Render-Varianten der read-only Modell-Anzeige
// User-Direktive 22.06.2026: Modell wird aus SubAgent-Konfiguration gezogen, NICHT ausgewaehlt.

import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AgentModelDisplay } from "./AgentModelDisplay"

// Mock der api.subagents.listConfigs() — wird im AgentModelDisplay per useQuery aufgerufen
vi.mock("../api", () => ({
  api: {
    subagents: {
      listConfigs: vi.fn(),
    },
  },
}))
import { api } from "../api"

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe("AgentModelDisplay", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // === Variante 1: System / User-Aktionen ===
  describe("System / User Aktionen", () => {
    it('rendert "System-Aktion — kein Modell" fuer agent="system"', async () => {
      ;(api.subagents.listConfigs as any).mockResolvedValue([])
      renderWithQuery(<AgentModelDisplay agent="system" />)
      const el = await screen.findByTestId("agent-model-display")
      expect(el).toHaveAttribute("data-variant", "system")
      expect(el.textContent).toContain("System-Aktion — kein Modell")
    })

    it('rendert "User-Aktion — manuell" fuer agent="user"', async () => {
      ;(api.subagents.listConfigs as any).mockResolvedValue([])
      renderWithQuery(<AgentModelDisplay agent="user" />)
      const el = await screen.findByTestId("agent-model-display")
      expect(el).toHaveAttribute("data-variant", "user")
      expect(el.textContent).toContain("User-Aktion — manuell")
    })

    it('rendert "User-Aktion — manuell" fuer leeren agent-String', async () => {
      ;(api.subagents.listConfigs as any).mockResolvedValue([])
      renderWithQuery(<AgentModelDisplay agent="" />)
      const el = await screen.findByTestId("agent-model-display")
      // agent="" faellt in den User-Fallback (agent !== "system")
      expect(el).toHaveAttribute("data-variant", "user")
    })
  })

  // === Variante 2: Unbekannter Agent ===
  describe("Unbekannter Agent", () => {
    it('zeigt Warnung wenn Agent nicht in SubAgent-Configs existiert', async () => {
      ;(api.subagents.listConfigs as any).mockResolvedValue([
        { name: "pi-coder", is_subagent: true, model: "minimax-m3", provider: "minimax-direct" },
      ])
      renderWithQuery(<AgentModelDisplay agent="nonexistent-agent" />)
      const el = await screen.findByTestId("agent-model-display")
      // waitFor ist nötig, weil useQuery erst nach erstem Render die Daten liefert
      // und die Komponente initial mit leeren Configs "unknown" rendert.
      await waitFor(() => expect(el).toHaveAttribute("data-variant", "unknown"))
      expect(el.textContent).toContain("Agent unbekannt")
    })
  })

  // === Variante 3: SubAgent ohne Modell ===
  describe("SubAgent ohne Modell", () => {
    it("zeigt Hinweis wenn SubAgent kein model und kein default_model hat", async () => {
      ;(api.subagents.listConfigs as any).mockResolvedValue([
        { name: "pi-empty", is_subagent: true, model: "", provider: "" },
      ])
      renderWithQuery(<AgentModelDisplay agent="pi-empty" />)
      const el = await screen.findByTestId("agent-model-display")
      await waitFor(() => expect(el).toHaveAttribute("data-variant", "no-model"))
      expect(el.textContent).toContain("Kein Modell in SubAgent konfiguriert")
    })

    it("faellt auf default_model zurueck wenn model leer ist", async () => {
      ;(api.subagents.listConfigs as any).mockResolvedValue([
        { name: "pi-default-only", is_subagent: true, model: "", default_model: "gemma4:12b", provider: "ollama" },
      ])
      renderWithQuery(<AgentModelDisplay agent="pi-default-only" />)
      const el = await screen.findByTestId("agent-model-display")
      await waitFor(() => expect(el).toHaveAttribute("data-variant", "model"))
      expect(el.textContent).toContain("ollama/gemma4:12b")
    })
  })

  // === Variante 4: Normalfall ===
  describe("Normalfall: Modell vorhanden", () => {
    it("zeigt provider/model fuer SubAgent mit model", async () => {
      ;(api.subagents.listConfigs as any).mockResolvedValue([
        { name: "pi-coder", is_subagent: true, model: "minimax-m3", provider: "minimax-direct" },
      ])
      renderWithQuery(<AgentModelDisplay agent="pi-coder" />)
      const el = await screen.findByTestId("agent-model-display")
      await waitFor(() => expect(el).toHaveAttribute("data-variant", "model"))
      expect(el).toHaveAttribute("data-model", "minimax-direct/minimax-m3")
      expect(el.textContent).toContain("minimax-direct/minimax-m3")
    })

    it("zeigt nur model wenn provider leer ist", async () => {
      ;(api.subagents.listConfigs as any).mockResolvedValue([
        { name: "pi-no-provider", is_subagent: true, model: "custom-model", provider: "" },
      ])
      renderWithQuery(<AgentModelDisplay agent="pi-no-provider" />)
      const el = await screen.findByTestId("agent-model-display")
      await waitFor(() => expect(el).toHaveAttribute("data-variant", "model"))
      expect(el).toHaveAttribute("data-model", "custom-model")
    })

    it("zeigt 'Org'-Badge fuer Nicht-SubAgent-Rollen", async () => {
      ;(api.subagents.listConfigs as any).mockResolvedValue([
        { name: "ceo-digital", is_subagent: false, model: "minimax-m3", provider: "minimax-direct" },
      ])
      renderWithQuery(<AgentModelDisplay agent="ceo-digital" />)
      const el = await screen.findByTestId("agent-model-display")
      await waitFor(() => expect(el).toHaveAttribute("data-variant", "model"))
      expect(el).toHaveAttribute("data-is-subagent", "false")
      expect(el.textContent).toContain("Org")
    })

    it("zeigt KEIN 'Org'-Badge fuer SubAgent-Rollen", async () => {
      ;(api.subagents.listConfigs as any).mockResolvedValue([
        { name: "pi-coder", is_subagent: true, model: "minimax-m3", provider: "minimax-direct" },
      ])
      renderWithQuery(<AgentModelDisplay agent="pi-coder" />)
      const el = await screen.findByTestId("agent-model-display")
      await waitFor(() => expect(el).toHaveAttribute("data-variant", "model"))
      expect(el).toHaveAttribute("data-is-subagent", "true")
      expect(el.textContent).not.toContain("Org")
    })

    it("bevorzugt model vor default_model", async () => {
      ;(api.subagents.listConfigs as any).mockResolvedValue([
        {
          name: "pi-both",
          is_subagent: true,
          model: "primary-model",
          default_model: "fallback-model",
          provider: "minimax-direct",
        },
      ])
      renderWithQuery(<AgentModelDisplay agent="pi-both" />)
      const el = await screen.findByTestId("agent-model-display")
      await waitFor(() => expect(el).toHaveAttribute("data-variant", "model"))
      expect(el).toHaveAttribute("data-model", "minimax-direct/primary-model")
      expect(el.textContent).not.toContain("fallback-model")
    })
  })

  // === Allgemeine Eigenschaften ===
  describe("Allgemein", () => {
    it("rendert ohne Daten (Loading-State nicht blockierend)", async () => {
      // listConfigs haengt — Komponente soll trotzdem rendern (System/User-Fallback)
      ;(api.subagents.listConfigs as any).mockImplementation(() => new Promise(() => {}))
      renderWithQuery(<AgentModelDisplay agent="system" />)
      const el = await screen.findByTestId("agent-model-display")
      expect(el).toBeInTheDocument()
    })

    it("ist read-only (kein Input/Button/Edit-Element)", async () => {
      ;(api.subagents.listConfigs as any).mockResolvedValue([
        { name: "pi-coder", is_subagent: true, model: "minimax-m3", provider: "minimax-direct" },
      ])
      const { container } = renderWithQuery(<AgentModelDisplay agent="pi-coder" />)
      await screen.findByTestId("agent-model-display")
      // Es darf kein input/select/textarea/button vorhanden sein
      expect(container.querySelector("input")).toBeNull()
      expect(container.querySelector("select")).toBeNull()
      expect(container.querySelector("textarea")).toBeNull()
      expect(container.querySelector("button")).toBeNull()
    })
  })
})
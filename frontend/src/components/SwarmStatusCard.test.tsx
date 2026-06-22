// Tests fuer SwarmStatusCard (Phase 6 + 9)
// User-Direktive 22.06.2026: Frontend zeigt Swarm-Status mit Workern und Score.

import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { SwarmStatusCard } from "./SwarmStatusCard"

vi.mock("../api", () => ({
  api: {
    swarms: {
      listByTask: vi.fn(),
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

describe("SwarmStatusCard", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("zeigt nichts wenn keine Swarms existieren", async () => {
    ;(api.swarms.listByTask as any).mockResolvedValue([])
    const { container } = renderWithQuery(<SwarmStatusCard taskId="t1" />)
    await waitFor(() => {
      expect(container.querySelector('[data-testid="swarm-status-card"]')).toBeNull()
    })
  })

  it("zeigt Swarm mit Workern und Score", async () => {
    const mockSwarms = [{
      id: "swarm-1",
      task_id: "t1",
      swarm_type: "parallel",
      status: "completed",
      merge_strategy: "reviewer_picks_best",
      total_cost_usd: 0.15,
      consensus_threshold: 75,
      auto_approve_threshold: 90,
      result: {
        merged_output: {
          avg_score: 87.5,
          auto_approve: false,
        },
      },
      workers: [
        { id: "w1", subagent_role: "pi-coder", variant: "minimalist",
          weight: 1.0, status: "completed", cost_usd: 0.05, score: 90 },
        { id: "w2", subagent_role: "pi-coder", variant: "robust",
          weight: 1.0, status: "completed", cost_usd: 0.05, score: 85 },
        { id: "w3", subagent_role: "pi-coder", variant: "performant",
          weight: 1.0, status: "completed", cost_usd: 0.05, score: 88 },
      ],
    }]
    ;(api.swarms.listByTask as any).mockResolvedValue(mockSwarms)
    renderWithQuery(<SwarmStatusCard taskId="t1" />)
    await waitFor(() => {
      const card = screen.getByTestId("swarm-status-card")
      expect(card).toHaveAttribute("data-count", "1")
    })
    const item = screen.getByTestId("swarm-item")
    expect(item).toHaveAttribute("data-status", "completed")
    const workers = screen.getAllByTestId("worker-bar")
    expect(workers).toHaveLength(3)
    expect(workers[0]).toHaveAttribute("data-worker-status", "completed")
  })

  it("zeigt running-Status mit partiellem Progress", async () => {
    const mockSwarms = [{
      id: "swarm-2",
      task_id: "t2",
      swarm_type: "competitive",
      status: "running",
      merge_strategy: "consensus_score",
      total_cost_usd: 0.05,
      consensus_threshold: 75,
      auto_approve_threshold: 90,
      workers: [
        { id: "w1", subagent_role: "pi-reviewer", variant: "quality",
          weight: 1.0, status: "running", cost_usd: 0.02 },
        { id: "w2", subagent_role: "pi-tester", variant: "bugs",
          weight: 1.0, status: "pending", cost_usd: 0 },
        { id: "w3", subagent_role: "pi-fixer", variant: "robustness",
          weight: 1.0, status: "pending", cost_usd: 0 },
      ],
    }]
    ;(api.swarms.listByTask as any).mockResolvedValue(mockSwarms)
    renderWithQuery(<SwarmStatusCard taskId="t2" />)
    await waitFor(() => {
      const item = screen.getByTestId("swarm-item")
      expect(item).toHaveAttribute("data-status", "running")
    })
    const workers = screen.getAllByTestId("worker-bar")
    expect(workers[0]).toHaveAttribute("data-worker-status", "running")
    expect(workers[1]).toHaveAttribute("data-worker-status", "pending")
  })

  it("zeigt mehrere Swarms wenn vorhanden", async () => {
    const mockSwarms = [
      { id: "s1", task_id: "t3", swarm_type: "parallel", status: "completed",
        merge_strategy: "merge_all", total_cost_usd: 0.10,
        consensus_threshold: 75, auto_approve_threshold: 90,
        workers: [{ id: "w1", subagent_role: "pi-coder", variant: "v1",
                   weight: 1.0, status: "completed", cost_usd: 0.10 }] },
      { id: "s2", task_id: "t3", swarm_type: "competitive", status: "running",
        merge_strategy: "consensus_score", total_cost_usd: 0.05,
        consensus_threshold: 75, auto_approve_threshold: 90,
        workers: [{ id: "w2", subagent_role: "pi-reviewer", variant: "r1",
                   weight: 1.0, status: "running", cost_usd: 0.02 }] },
    ]
    ;(api.swarms.listByTask as any).mockResolvedValue(mockSwarms)
    renderWithQuery(<SwarmStatusCard taskId="t3" />)
    await waitFor(() => {
      const card = screen.getByTestId("swarm-status-card")
      expect(card).toHaveAttribute("data-count", "2")
    })
    const items = screen.getAllByTestId("swarm-item")
    expect(items).toHaveLength(2)
  })
})
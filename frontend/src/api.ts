// API-Client fuer Pi Dashboard 2.0
const API = ""  // Nutzt Vite-Proxy (alles unter /api geht zu Backend auf 9220)

async function request<T>(method: string, path: string, body?: any): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  if (res.status === 204) return null as T
  return res.json()
}

export const api = {
  // Projects
  listProjects: () => request<any>("GET", "/api/kanban/projects"),
  getProject: (id: string) => request<any>("GET", `/api/kanban/projects/${id}`),
  createProject: (data: any) => request<any>("POST", "/api/kanban/projects", data),
  setProjectMode: (id: string, mode: string, note?: string) =>
    request<any>("PUT", `/api/kanban/projects/${id}/mode`, { mode, note }),
  setProjectCategory: (id: string, category: string) =>
    request<any>("PUT", `/api/kanban/projects/${id}/category`, { category }),
  getCompletionReport: (id: string) =>
    request<any>("GET", `/api/kanban/projects/${id}/completion-report`),

  // Tasks
  listTasks: (params?: { project_id?: string; status?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams()
    if (params?.project_id) q.set("project_id", params.project_id)
    if (params?.status) q.set("status", params.status)
    if (params?.limit) q.set("limit", String(params.limit))
    if (params?.offset) q.set("offset", String(params.offset))
    const qs = q.toString()
    return request<any>("GET", `/api/kanban/tasks${qs ? "?" + qs : ""}`)
  },
  getTask: (id: string) => request<any>("GET", `/api/kanban/tasks/${id}`),
  updateTask: (id: string, data: any) => request<any>("PATCH", `/api/kanban/tasks/${id}`, data),
  createTask: (data: any) => request<any>("POST", "/api/kanban/tasks", data),
  setTaskStatus: (id: string, status: string) =>
    request<any>("PUT", `/api/kanban/tasks/${id}/status`, { status }),
  setTaskPriority: (id: string, priority: number) =>
    request<any>("PUT", `/api/kanban/tasks/${id}/priority`, { priority }),
  reportTaskUsage: (id: string, data: { tokens_in: number; tokens_out: number; model?: string; role?: string }) =>
    request<any>("POST", `/api/kanban/tasks/${id}/usage`, data),
  getTaskStats: (id: string) => request<any>("GET", `/api/kanban/tasks/${id}/stats`),
  getTaskHistory: (id: string) => request<any>("GET", `/api/kanban/tasks/${id}/history`),

  // Models / Pricing
  listModels: () => request<any[]>("GET", "/api/models"),
  listProviders: () => request<any[]>("GET", "/api/models/providers"),
  getPricing: () => request<any>("GET", "/api/models/pricing"),
  refreshPricing: () => request<any>("POST", "/api/models/pricing/refresh"),
  updatePricing: (data: { provider: string; model_id?: string; input_per_1m: number; output_per_1m: number; note?: string }) =>
    request<any>("POST", "/api/models/pricing/update", data),

  // Roles
  listRoles: () => request<any>("GET", "/api/roles"),

  // Analytics
  getAnalytics: () => request<any>("GET", "/api/analytics/summary"),
}

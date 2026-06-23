// API-Client fuer Pi Dashboard 2.0
const API = ""  // Nutzt Vite-Proxy (alles unter /api geht zu Backend auf 9220)

async function request<T>(method: string, path: string, body?: any): Promise<T> {
  // LLM-Validierung darf bis zu 120s dauern (minimax-m3 kann langsam sein)
  const isLlmCall = path.includes("validate-with-llm") || path.includes("/llm/")
  const timeoutMs = isLlmCall ? 120000 : 30000
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${API}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`HTTP ${res.status}: ${text}`)
    }
    if (res.status === 204) return null as T
    return res.json()
  } catch (e: any) {
    if (e?.name === "AbortError") {
      throw new Error(`Request timeout nach ${timeoutMs/1000}s. Bitte erneut versuchen.`)
    }
    throw e
  } finally {
    clearTimeout(timeout)
  }
}

export const api = {
  post: <T = any>(path: string, body?: any) => request<T>("POST", path, body),
  get: <T = any>(path: string) => request<T>("GET", path),
  put: <T = any>(path: string, body?: any) => request<T>("PUT", path, body),
  patch: <T = any>(path: string, body?: any) => request<T>("PATCH", path, body),
  delete: <T = any>(path: string) => request<T>("DELETE", path),
  // Multi-Agent-Swarm (User-Direktive 22.06.2026)
  swarms: {
    listByTask: (taskId: string) =>
      request<any>("GET", `/api/swarms?task_id=${taskId}`),
    get: (id: string) => request<any>("GET", `/api/swarms/${id}`),
    spawn: (config: any) => request<any>("POST", "/api/swarms", config),
  },
  // Idee-Page (User-Direktive 23.06.2026)
  ideas: {
    list: (status?: string) =>
      request<any>("GET", `/api/ideas${status ? `?status=${status}` : ""}`),
    get: (id: string) => request<any>("GET", `/api/ideas/${id}`),
    create: (data: any) => request<any>("POST", "/api/ideas", data),
    update: (id: string, data: any) =>
      request<any>("PUT", `/api/ideas/${id}`, data),
    delete: (id: string) => request<any>("DELETE", `/api/ideas/${id}`),
    convertToTask: (id: string) =>
      request<any>("POST", `/api/ideas/${id}/umsetzen`, {}),
  },
  // Sub-Tasks mit Planung (User-Direktive 23.06.2026, Task 61ab3dfe26d3)
  subtasks: {
    list: (parentTaskId: string) =>
      request<any>("GET", `/api/subtasks?parent_task_id=${parentTaskId}`),
    get: (id: string) => request<any>("GET", `/api/subtasks/${id}`),
    create: (data: any) => request<any>("POST", "/api/subtasks", data),
    updatePlan: (id: string, plan: any) =>
      request<any>("PUT", `/api/subtasks/${id}/plan`, plan),
    submitResult: (id: string, result: any) =>
      request<any>("POST", `/api/subtasks/${id}/result`, result),
    delete: (id: string) => request<any>("DELETE", `/api/subtasks/${id}`),
  },
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
  setProjectDefaultSop: (id: string, sopId: string | null) =>
    request<any>("PATCH", `/api/kanban/projects/${id}`, { default_sop_id: sopId }),

  // === SubAgents (User-Direktive 18.06.2026) ===
  subagents: {
    listConfigs: () => request<any>("GET", "/api/subagents/configs"),
    buildAgent: (roleName: string, taskId?: string, overrideModel?: string) => {
      const params = new URLSearchParams({ role_name: roleName });
      if (taskId) params.set("task_id", taskId);
      if (overrideModel) params.set("override_model", overrideModel);
      return request<any>("POST", `/api/subagents/build?${params.toString()}`);
    },
    updateModel: (roleName: string, model: string, provider?: string, apiKeyId?: string | null) =>
      request<any>("PATCH", `/api/subagents/${roleName}/model`, { model, provider, api_key_id: apiKeyId }),
    updatePrompt: (roleName: string, systemPrompt: string) =>
      request<any>("PATCH", `/api/subagents/${roleName}/prompt`, { system_prompt: systemPrompt }),
    updateName: (roleName: string, displayName: string) =>
      request<any>("PATCH", `/api/subagents/${roleName}/name`, { display_name: displayName }),
    updateSop: (roleName: string, sopId: string | null) =>
      request<any>("PATCH", `/api/subagents/${roleName}/sop`, { sop_id: sopId || null }),
    updateConfig: (roleName: string, data: {
      display_name?: string | null;
      sop_id?: string | null;
      model?: string | null;
      provider?: string | null;
      api_key_id?: string | null;
      system_prompt?: string | null;
    }) => request<any>("PATCH", `/api/subagents/${roleName}/config`, data),
    delete: (roleName: string) => request<any>("DELETE", `/api/subagents/${roleName}`),
  },

  // === CIO-Triage (Schritt 0, User-Direktive 16.06.2026) ===
  setTaskType: (id: string, taskType: string) =>
    request<any>("PUT", `/api/kanban/tasks/${id}/task-type`, { task_type: taskType }),
  setImplementationPlan: (id: string, plan: any) =>
    request<any>("PUT", `/api/kanban/tasks/${id}/implementation-plan`, { implementation_plan: plan }),
  setStandardsCheck: (id: string, check: any) =>
    request<any>("PUT", `/api/kanban/tasks/${id}/standards-check`, { standards_check: check }),
  setSubagentReadiness: (id: string, readiness: any) =>
    request<any>("PUT", `/api/kanban/tasks/${id}/subagent-readiness`, { subagent_readiness: readiness }),

  // Architecture Rules (Standardvorgaben)
  listRules: (params?: { category?: string; severity?: string; active_only?: boolean }) => {
    const q = new URLSearchParams()
    if (params?.category) q.set("category", params.category)
    if (params?.severity) q.set("severity", params.severity)
    if (params?.active_only !== undefined) q.set("active_only", String(params.active_only))
    const qs = q.toString()
    return request<any>("GET", `/api/architecture-rules${qs ? "?" + qs : ""}`)
  },

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

  // Sub-Tasks
  getSubtasks: (taskId: string) => request<any>("GET", `/api/kanban/tasks/${taskId}/stats`).then((s: any) => s?.subtasks || []),
  aggregateSubtasks: (taskId: string) => request<any>("POST", `/api/kanban/tasks/${taskId}/aggregate`),
  deleteTask: (taskId: string) => request<null>("DELETE", `/api/kanban/tasks/${taskId}`),

  // Triage (korrekte v2-Backend-Endpoints mit /tasks/ prefix)
  processTriage: (projectId: string) => request<any>("POST", `/api/kanban/tasks/triage/${projectId}/process`),
  moveAllToTriage: (projectId: string) => request<any>("POST", `/api/kanban/tasks/bulk-triage/${projectId}`),

  // Brainstorming
  listBrainstorm: (projectId: string) => request<any[]>("GET", `/api/kanban/projects/${projectId}/brainstorm`),
  addBrainstorm: (projectId: string, role: "user" | "assistant", text: string) =>
    request<any>("POST", `/api/kanban/projects/${projectId}/brainstorm`, { role, text }),

  // Requirements
  listRequirements: (projectId: string) => request<any[]>("GET", `/api/kanban/projects/${projectId}/requirements`),
  generateRequirements: (projectId: string) => request<any>("POST", `/api/kanban/projects/${projectId}/requirements`, {}),

  // Implementation Plan
  listImplementation: (projectId: string) => request<any[]>("GET", `/api/kanban/projects/${projectId}/implementation`),

  // ─────────────── Standard-Workflow ───────────────
  // TRIAGE → GO (CIO approved)
  wfTriageApprove: (taskId: string, agent: string = "CIO", note?: string) =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/triage-approve`, { agent, note }),
  // TRIAGE → BLOCK + Frage (Auto-CIO, Live-Modus)
  wfTriageEvaluate: (taskId: string, agent: string = "CIO", autoMode: boolean = true) =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/triage-evaluate`, { agent, auto_mode: autoMode }),
  // CEO antwortet auf CIO-Frage (Block → Todo/Triage/InProgress)
  wfCeoAnswer: (taskId: string, answer: string, targetStatus: "todo" | "triage" | "in_progress" = "todo", agent: string = "CEO") =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/ceo-answer`, { agent, answer, target_status: targetStatus }),
  // Recommendation anwenden (CEO setzt editierte Empfehlung um)
  wfApplyRecommendation: (taskId: string, recommendation: string, kind: "title" | "description" | "general" = "description", issueIndex?: number) =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/apply-recommendation`, { agent: "CEO", recommendation, kind, issue_index: issueIndex }),
  // Task zurueck in Triage (Soft-Reset, loescht NICHT, durchlaeuft Standard-Workflow neu)
  wfReopen: (taskId: string, agent: string = "CEO", reason: string = "Wieder in Triage", resetIteration: boolean = true) =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/reopen`, { agent, reason, reset_iteration: resetIteration }),

  // ─────────────── Process-Templates (BPMN) ───────────────
  listProcessTemplates: (projectId?: string) =>
    request<any[]>("GET", `/api/process-templates${projectId ? `?project_id=${projectId}` : ""}`),
  getProcessTemplate: (id: string) => request<any>("GET", `/api/process-templates/${id}`),
  createProcessTemplate: (data: any) => request<any>("POST", "/api/process-templates", data),
  updateProcessTemplate: (id: string, data: any) => request<any>("PUT", `/api/process-templates/${id}`, data),
  deleteProcessTemplate: (id: string) => request<any>("DELETE", `/api/process-templates/${id}`),
  applyProcessTemplate: (templateId: string, taskId: string) =>
    request<any>("POST", `/api/process-templates/${templateId}/apply-to-task/${taskId}`),
  activateProcessTemplate: (templateId: string, projectId: string, note?: string) =>
    request<any>("POST", `/api/process-templates/${templateId}/activate`, { project_id: projectId, agent: "CEO", note }),
  deactivateProcessTemplate: (templateId: string) =>
    request<any>("POST", `/api/process-templates/${templateId}/deactivate`),
  getActiveTemplate: (projectId: string) =>
    request<any>("GET", `/api/process-templates/active/${projectId}`),
  // TRIAGE → ? (CIO rejected with feedback, status bleibt 'triage')
  wfTriageReject: (taskId: string, agent: string = "CIO", reason: string = "") =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/triage-reject`, { agent, reason }),
  // GO: Worker zuweisen
  wfAssign: (taskId: string, agent: string = "CIO", worker: string) =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/assign`, { agent, worker }),
  // GO → IN_PROGRESS (Worker startet)
  // === Bugfix 19.06.2026 (Task 921bba39d13f) ===
  // agent ist optional — das Backend loest den Agent aus dem Task auf
  // (assigned_subagent, assigned_role, Fallback "system").
  wfStart: (taskId: string, agent?: string | null) =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/start`, { agent: agent ?? null }),
  // IN_PROGRESS → REVIEW (Worker done)
  wfSubmitReview: (taskId: string, agent: string = "system", note?: string) =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/submit-review`, { agent, note }),
  // REVIEW → IN_PROGRESS (Tester findet Bugs)
  wfTesterReject: (taskId: string, agent: string = "pi-tester", issues: string, note?: string) =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/tester-reject`, { agent, issues, note }),
  // REVIEW → BLOCK + Auto-Create Freigabe-Task
  wfTesterApprove: (taskId: string, agent: string = "pi-tester", note?: string) =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/tester-approve`, { agent, note }),
  // BLOCK → DONE (CIO final + Freigabe-Task done)
  wfCioApprove: (taskId: string, agent: string = "CIO", note?: string) =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/cio-approve`, { agent, note }),
  // BLOCK → in_progress|todo (CIO rejected)
  wfCioReject: (taskId: string, agent: string = "CIO", reason: string, targetStatus: "in_progress" | "todo" = "in_progress") =>
    request<any>("POST", `/api/workflow/tasks/${taskId}/cio-reject`, { agent, reason, target_status: targetStatus }),

  // Models / Pricing
  listModels: () => request<any[]>("GET", "/api/models"),
  listProviders: () => request<any[]>("GET", "/api/models/providers"),
  getPricing: () => request<any>("GET", "/api/models/pricing"),
  refreshPricing: () => request<any>("POST", "/api/models/pricing/refresh"),
  updatePricing: (data: { provider: string; model_id?: string; input_per_1m: number; output_per_1m: number; note?: string }) =>
    request<any>("POST", "/api/models/pricing/update", data),

  // Roles
  listRoles: () => request<any>("GET", "/api/roles"),
  listSubAgents: () => request<any>("GET", "/api/roles/sub-agents"),
  listOrgRoles: () => request<any>("GET", "/api/roles/org"),

  // SOPs (Standard Operating Procedures)
  listSops: (category?: string) => {
    const q = category ? `?category=${encodeURIComponent(category)}` : ""
    return request<any>("GET", `/api/sops${q}`)
  },
  getSop: (sopId: string) => request<any>("GET", `/api/sops/${sopId}`),
  createSop: (data: any) => request<any>("POST", "/api/sops", data),
  updateSop: (sopId: string, data: any) => request<any>("PUT", `/api/sops/${sopId}`, data),
  updateSopStep: (sopId: string, stepId: string, data: { description?: string; expected_result?: string; ai_instructions_md?: string; agent?: string; model?: string }) =>
    request<any>("PATCH", `/api/sops/${sopId}/steps/${stepId}`, data),
  createSopStep: (sopId: string, data: any) => request<any>("POST", `/api/sops/${sopId}/steps`, data),
  aiStepHelper: (sopId: string, stepId: string, userInput: string, model?: string) =>
    request<any>("POST", `/api/sops/${sopId}/steps/${stepId}/ai-helper`, { user_input: userInput, model }),
  // KI-Support-Designer (User-Direktive 16.06.2026): iterativer Chat-Modus
  // - user_input: der aktuelle User-Satz
  // - model: LLM-Auswahl
  // - auto_save: direkt in DB speichern
  // - current_md: bisheriger MD-Text (wird im Backend mit der neuen Nachricht kombiniert)
  // - conversation: Chat-History (fuer Kontext)
  aiStepEvaluate: (
    sopId: string, stepId: string,
    userInput: string, model?: string, autoSave = false,
    currentMd?: string, conversation?: Array<{ role: string; content: string }>
  ) => request<any>("POST", `/api/sops/${sopId}/steps/${stepId}/ai-evaluate`, {
    user_input: userInput, model, auto_save: autoSave,
    current_md: currentMd, conversation
  }),
  deleteSop: (sopId: string) => request<any>("DELETE", `/api/sops/${sopId}`),
  getSopBpmn: (sopId: string) => request<any>("GET", `/api/sops/${sopId}/bpmn`),
  getSopUml: (sopId: string) => request<any>("GET", `/api/sops/${sopId}/uml`),
  seedDefaultSops: () => request<any>("POST", "/api/sops/seed-defaults", {}),

  // SOP Instances
  startSopInstance: (sopId: string, data: any) =>
    request<any>("POST", `/api/sops/${sopId}/start`, data),
  listSopInstances: (params?: { project_id?: string; task_id?: string; status?: string }) => {
    const q = new URLSearchParams()
    if (params?.project_id) q.set("project_id", params.project_id)
    if (params?.task_id) q.set("task_id", params.task_id)
    if (params?.status) q.set("status", params.status)
    const qs = q.toString()
    return request<any>("GET", `/api/sops/instances/all${qs ? "?" + qs : ""}`)
  },
  getSopInstance: (instanceId: string) =>
    request<any>("GET", `/api/sops/instances/${instanceId}`),
  runSopInstance: (instanceId: string) =>
    request<any>("POST", `/api/sops/instances/${instanceId}/run`, {}),
  setSopInstanceContext: (instanceId: string, context: any) =>
    request<any>("POST", `/api/sops/instances/${instanceId}/context`, { context }),
  failSopInstance: (instanceId: string, reason: string) =>
    request<any>("POST", `/api/sops/instances/${instanceId}/fail?reason=${encodeURIComponent(reason)}`, {}),

  // Self-Improvement (Research & Strategy)
  listSelfImprovementFrameworks: () => request<any>("GET", "/api/selfimprovement/frameworks"),
  getSelfImprovementStrategy: () => request<any>("GET", "/api/selfimprovement/strategy"),

  // Self-Improvement: Schwachstellen + Subagent-Analyse (User-Direktive 17.06.2026)
  listWeaknesses: (params?: { project_id?: string; status?: string; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.project_id) q.set("project_id", params.project_id)
    if (params?.status) q.set("status", params.status)
    if (params?.limit) q.set("limit", String(params.limit))
    const qs = q.toString()
    return request<any>("GET", `/api/selfimprovement/weaknesses${qs ? "?" + qs : ""}`)
  },
  getWeakness: (id: string) => request<any>("GET", `/api/selfimprovement/weaknesses/${id}`),
  createWeakness: (data: {
    title: string
    description: string
    project_id: string
    severity?: string
    category?: string
    created_by?: string
  }) => request<any>("POST", "/api/selfimprovement/weaknesses", data),
  updateWeakness: (id: string, data: any) => request<any>("PUT", `/api/selfimprovement/weaknesses/${id}`, data),
  editAnalysis: (analysisId: string, data: { root_cause?: string; solution_proposal?: string }) =>
    request<any>("PUT", `/api/selfimprovement/analyses/${analysisId}`, data),
  reanalyzeWeakness: (id: string) => request<any>("POST", `/api/selfimprovement/weaknesses/${id}/reanalyze`),
  createTaskFromWeakness: (id: string) =>
    request<any>("POST", `/api/selfimprovement/weaknesses/${id}/create-task`),

  // Performance (Task-Transitions, zentrale Performance-Tabelle)
  listTransitions: (params?: { project_id?: string; task_id?: string; from_status?: string; to_status?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams()
    if (params?.project_id) q.set("project_id", params.project_id)
    if (params?.task_id) q.set("task_id", params.task_id)
    if (params?.from_status) q.set("from_status", params.from_status)
    if (params?.to_status) q.set("to_status", params.to_status)
    if (params?.limit) q.set("limit", String(params.limit))
    if (params?.offset) q.set("offset", String(params.offset))
    const qs = q.toString()
    return request<any>("GET", `/api/performance/transitions${qs ? "?" + qs : ""}`)
  },
  getProjectTimeline: (projectId: string, days: number = 7) =>
    request<any>("GET", `/api/performance/projects/${projectId}/timeline?days=${days}`),
  getProjectPerformanceStats: (projectId: string) =>
    request<any>("GET", `/api/performance/projects/${projectId}/stats`),
  getGlobalPerformanceStats: () => request<any>("GET", "/api/performance/stats"),

  // Analytics
  getAnalytics: () => request<any>("GET", "/api/analytics/summary"),
  getCostSummary: (days: number = 30) => request<any>("GET", `/api/cost/summary?days=${days}`),

  // TTS (MiniMax Text-to-Audio V2 via Backend)
  speakText: (text: string, options?: { voice_id?: string; speed?: number; vol?: number; pitch?: number; language_boost?: string; output_format?: "url" | "hex" }) =>
    request<any>("POST", "/api/tts/speak", { text, ...options }),

  // Gateway (Top-Bar Status) — v2 hat diese noch nicht, deshalb mit Fallback
  getGatewayStatus: async () => {
    try {
      return await request<any>("GET", "/api/gateway/status")
    } catch {
      // Fallback: statischer Mock-Status basierend auf Backend-Health
      try {
        const health = await request<any>("GET", "/api/health")
        return {
          dashboard: { running: health?.status === "ok" },
          ollama: { running: false, model_count: 0, models: [] },
          pi: { running: true, version: "2.0.0" },
        }
      } catch {
        return {
          dashboard: { running: false },
          ollama: { running: false, model_count: 0, models: [] },
          pi: { running: false, version: "?.?.?" },
        }
      }
    }
  },
  restartOllama: async () => {
    try {
      return await request<any>("POST", "/api/gateway/restart/ollama")
    } catch {
      return { status: "mocked", message: "Restart Ollama ist im v2-Backend nicht implementiert (Mock)" }
    }
  },

  // ─────────────── User <-> Agent Interaktionstool (User-Direktive 17.06.2026) ───────────────
  // AgentQuestion: Frage erstellen (vom Agent)
  agentQuestions: {
    list: (params?: { status?: string; agent_id?: string; agent_level?: string; priority?: string; unseen_only?: boolean; limit?: number; offset?: number }) => {
      const q = new URLSearchParams()
      if (params?.status) q.set("status", params.status)
      if (params?.agent_id) q.set("agent_id", params.agent_id)
      if (params?.agent_level) q.set("agent_level", params.agent_level)
      if (params?.priority) q.set("priority", params.priority)
      if (params?.unseen_only) q.set("unseen_only", "true")
      if (params?.limit) q.set("limit", String(params.limit))
      if (params?.offset) q.set("offset", String(params.offset))
      const qs = q.toString()
      return request<any>("GET", `/api/tools/agent-questions/${qs ? "?" + qs : ""}`)
    },
    get: (id: string) => request<any>("GET", `/api/tools/agent-questions/${id}`),
    pendingCount: () => request<{ pending: number; unseen: number }>("GET", "/api/tools/agent-questions/pending/count"),
    wait: (sinceId: number = 0, timeout: number = 30) =>
      request<any>("GET", `/api/tools/agent-questions/wait?since_id=${sinceId}&timeout=${timeout}`),
    answer: (id: string, data: { answer_text?: string; answer_choice?: string; answered_by?: string }) =>
      request<any>("POST", `/api/tools/agent-questions/${id}/answer`, data),
    cancel: (id: string) => request<any>("POST", `/api/tools/agent-questions/${id}/cancel`),
    markSeen: (id: string) => request<any>("POST", `/api/tools/agent-questions/${id}/seen`),
    // File-Upload (FormData)
    uploadAttachment: async (id: string, file: File, source: "agent" | "user" = "user", kind: "file" | "image" = "file") => {
      const formData = new FormData()
      formData.append("file", file)
      formData.append("source", source)
      formData.append("kind", kind)
      const res = await fetch(`${API}/api/tools/agent-questions/${id}/attachments`, {
        method: "POST",
        body: formData,
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(`HTTP ${res.status}: ${text}`)
      }
      return res.json()
    },
    // Anhang herunterladen (gibt URL zurück)
    attachmentUrl: (questionId: string, attId: string) =>
      `${API}/api/tools/agent-questions/${questionId}/attachments/${attId}`,
  },

  // ─────────────── Live-Board Operator (User-Direktive 17.06.2026) ───────────────
  operators: {
    list: (params?: { status?: string }) => {
      const q = params?.status ? `?status=${params.status}` : ""
      return request<any>("GET", `/api/operators/${q}`)
    },
    listActive: () => request<any>("GET", "/api/operators/active"),
    listActiveAgents: () => request<any>("GET", "/api/operators/agents/active"),
    get: (boardId: string) => request<any>("GET", `/api/operators/${boardId}`),
    start: (boardId: string) => request<any>("POST", `/api/operators/${boardId}/start`),
    stop: (boardId: string, reason: string = "user_request") =>
      request<any>("POST", `/api/operators/${boardId}/stop?reason=${encodeURIComponent(reason)}`),
    stats: (boardId: string) => request<any>("GET", `/api/operators/${boardId}/stats`),
  },

  // ─────────────── Test Runner (User-Direktive 17.06.2026) ───────────────
  // Navigator-Service zum Ausfuehren von Test-Aktionen (z.B. SOP starten, Task erstellen)
  testRunner: {
    listActions: () => request<any>("GET", "/api/test-runner/actions"),
    getAction: (id: string) => request<any>("GET", `/api/test-runner/actions/${id}`),
    executeAction: (id: string, params: Record<string, any> = {}) =>
      request<any>("POST", `/api/test-runner/actions/${id}/execute`, { params }),
    history: (limit: number = 20) =>
      request<any>("GET", `/api/test-runner/history?limit=${limit}`),
  },

  // ─────────────── Provider Credentials (API-Keys) ───────────────
  listProviderCredentials: () => request<any>("GET", "/api/provider-credentials"),
  getProviderCredential: (id: string) => request<any>("GET", `/api/provider-credentials/${id}`),
  createProviderCredential: (data: any) => request<any>("POST", "/api/provider-credentials", data),
  updateProviderCredential: (id: string, data: any) => request<any>("PUT", `/api/provider-credentials/${id}`, data),
  deleteProviderCredential: (id: string) => request<any>("DELETE", `/api/provider-credentials/${id}`),
  refreshProviderCredentialPricing: (id: string) =>
    request<any>("POST", `/api/provider-credentials/${id}/refresh-pricing`),
}

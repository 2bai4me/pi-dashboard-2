// utils/screenContext.ts — Aktueller Screen-Context (Project/Task aus URL)
// FIX 23.06.2026: Modul fehlte
// Liefert: { projectId?: string, taskId?: string, tab?: string }

export interface ScreenContext {
  projectId?: string
  taskId?: string
  tab?: string
}

export function getCurrentScreenContext(): ScreenContext {
  if (typeof window === "undefined") return {}
  try {
    const params = new URLSearchParams(window.location.search)
    const hash = window.location.hash
    // Auch Hash-Routing unterstuetzen: #/kanban?projectId=...&tab=...
    const hashParts = hash.split("?")
    const hashParams = hashParts.length > 1 ? new URLSearchParams(hashParts[1]) : new URLSearchParams()
    return {
      projectId: params.get("projectId") || hashParams.get("projectId") || undefined,
      taskId: params.get("task") || params.get("taskId") || hashParams.get("task") || hashParams.get("taskId") || undefined,
      tab: params.get("tab") || hashParams.get("tab") || undefined,
    }
  } catch {
    return {}
  }
}

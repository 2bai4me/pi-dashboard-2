/**
 * Page-ID-Registry (User-Direktive 24.06.2026)
 *
 * Zentrale Liste aller Seiten-IDs der PI Dashboard 2.0 App.
 * Format: PG-<NNN>-<KATEGORIE>
 *
 * Diese IDs werden:
 * 1. Unterhalb des Seitentitels als klickbare PageId-Komponente angezeigt
 * 2. In der Dokumentation verwendet, um die richtige Stelle zu finden
 * 3. Im Code (Dateinamen) referenziert
 *
 * Neue Seite hinzufuegen:
 *   1. PG-NNN in PAGE_IDS eintragen
 *   2. PageId-Komponente unter <h1> einbauen
 *   3. Diese Dokumentation aktualisieren
 */

export const PAGE_IDS = {
  // === Board / Tasks ===
  KANBAN: "PG-001-KANBAN",                  // Kanban-Board mit Drag&Drop
  TASK_DETAIL_PANEL: "PG-002-TASKDETAIL",   // Sidebar mit Task-Details

  // === SOPs ===
  SOPS: "PG-010-SOPS",                       // SOP-Liste + Editor
  SOP_AI_DESIGNER: "PG-011-AIDESIGNER",     // KI-Support Designer Modal

  // === Models / Provider ===
  MODELS: "PG-020-MODELS",                   // Model-Verwaltung
  API_KEYS: "PG-021-APIKEYS",                // API-Key-Verwaltung
  PROVIDER_CREDENTIALS: "PG-022-PROVCREDS",  // Provider-Credentials

  // === Roles / SubAgents ===
  ROLES: "PG-030-ROLES",                     // Rollen-Verwaltung
  SUB_AGENTS: "PG-031-SUBAGENTS",            // Sub-Agent Konfiguration

  // === Projects / Tasks ===
  PROJECTS: "PG-040-PROJECTS",               // Projekt-Liste
  TASKS: "PG-041-TASKS",                     // Task-Liste

  // === Process / Brainstorm / Ideas ===
  IDEAS: "PG-050-IDEAS",                     // Ideen-Board
  BRAINSTORM: "PG-051-BRAINSTORM",           // Brainstorming-Detail
  PROCESS_DESIGNER: "PG-052-PROCESS",       // Process-Designer

  // === Tools / Specials ===
  TOOLS: "PG-060-TOOLS",                     // Tools-Liste
  ARCHITECTURE: "PG-061-ARCHITECTURE",       // Architecture Rules
  STANDARDS: "PG-062-STANDARDS",             // Quality Standards
  OPENBRAIN: "PG-063-OPENBRAIN",             // OpenBrain-View

  // === Performance / Cost ===
  COST: "PG-070-COST",                       // Cost/Performance-View
  STATUS: "PG-071-STATUS",                   // System-Status
  METRICS: "PG-072-METRICS",                 // Live-Metriken

  // === Settings / Admin ===
  SETTINGS: "PG-080-SETTINGS",               // App-Settings
  INDEX: "PG-090-DASHBOARD",                 // Haupt-Dashboard
} as const

export type PageId = typeof PAGE_IDS[keyof typeof PAGE_IDS]

/**
 * Verzeichnis der Seiten-IDs nach Dateiname.
 *
 * Verwendung in Doku/Code:
 *   PG-001-KANBAN -> frontend/src/pages/Kanban.tsx
 *   PG-010-SOPS -> frontend/src/pages/Sops.tsx
 *
 * Neue Seite: hier eintragen, damit das Verzeichnis konsistent bleibt.
 */
export const PAGE_ID_TO_FILE: Record<string, string> = {
  "PG-001-KANBAN": "frontend/src/pages/Kanban.tsx",
  "PG-002-TASKDETAIL": "frontend/src/components/TaskDetailPanel.tsx",

  "PG-010-SOPS": "frontend/src/pages/Sops.tsx",
  "PG-011-AIDESIGNER": "frontend/src/pages/Sops.tsx (AiSupportDesignerModal)",

  "PG-020-MODELS": "frontend/src/pages/Models.tsx",
  "PG-021-APIKEYS": "frontend/src/pages/ApiKeys.tsx",
  "PG-022-PROVCREDS": "frontend/src/pages/ProviderCredentials.tsx",

  "PG-030-ROLES": "frontend/src/pages/Roles.tsx",
  "PG-031-SUBAGENTS": "frontend/src/pages/SubAgents.tsx",

  "PG-040-PROJECTS": "frontend/src/pages/Projects.tsx",
  "PG-041-TASKS": "frontend/src/pages/Tasks.tsx",

  "PG-050-IDEAS": "frontend/src/pages/Ideas.tsx",
  "PG-051-BRAINSTORM": "frontend/src/pages/Brainstorm.tsx",
  "PG-052-PROCESS": "frontend/src/pages/ProcessDesigner.tsx",

  "PG-060-TOOLS": "frontend/src/pages/Tools.tsx",
  "PG-061-ARCHITECTURE": "frontend/src/pages/Architecture.tsx",
  "PG-062-STANDARDS": "frontend/src/pages/Standards.tsx",
  "PG-063-OPENBRAIN": "frontend/src/pages/OpenBrain.tsx",

  "PG-070-COST": "frontend/src/pages/Cost.tsx",
  "PG-071-STATUS": "frontend/src/pages/Status.tsx",
  "PG-072-METRICS": "frontend/src/pages/Metrics.tsx",

  "PG-080-SETTINGS": "frontend/src/pages/Settings.tsx",
  "PG-090-DASHBOARD": "frontend/src/pages/Index.tsx",
}

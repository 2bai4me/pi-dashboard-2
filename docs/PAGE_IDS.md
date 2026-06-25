# PI Dashboard 2.0 — Page-ID-System (User-Direktive 24.06.2026)

## Zweck

Jede Seite der PI Dashboard 2.0 App hat eine **eineindeutige Page-ID** im Format `PG-<NNN>-<KATEGORIE>`.

Die ID wird:

1. **Im UI** unterhalb des Seitentitels angezeigt (klickbar → kopiert in Zwischenablage)
2. **Im Code** zur Identifikation der richtigen Datei/Stelle verwendet
3. **In der Dokumentation** zur Verlinkung zwischen Konzept und Implementation

## Verzeichnis

| Page-ID | Datei | Beschreibung |
|---------|-------|--------------|
| `PG-001-KANBAN` | `frontend/src/pages/Kanban.tsx` | Projekt-Board mit Drag&Drop |
| `PG-002-TASKDETAIL` | `frontend/src/components/TaskDetailPanel.tsx` | Sidebar mit Task-Details |
| `PG-010-SOPS` | `frontend/src/pages/Sops.tsx` | SOP-Liste + Editor |
| `PG-011-AIDESIGNER` | `frontend/src/pages/Sops.tsx` (AiSupportDesignerModal) | KI-Support Designer Modal |
| `PG-020-MODELS` | `frontend/src/pages/Models.tsx` | Model-Verwaltung |
| `PG-021-APIKEYS` | `frontend/src/pages/ApiKeys.tsx` | API-Key-Verwaltung |
| `PG-022-PROVCREDS` | `frontend/src/pages/ProviderCredentials.tsx` | Provider-Credentials |
| `PG-030-ROLES` | `frontend/src/pages/Roles.tsx` | Rollen-Verwaltung |
| `PG-031-SUBAGENTS` | `frontend/src/pages/SubAgents.tsx` | Sub-Agent Konfiguration |
| `PG-040-PROJECTS` | `frontend/src/pages/Projects.tsx` | Projekt-Liste |
| `PG-041-TASKS` | `frontend/src/pages/Tasks.tsx` | Task-Liste |
| `PG-050-IDEAS` | `frontend/src/pages/Ideas.tsx` | Ideen-Board |
| `PG-051-BRAINSTORM` | `frontend/src/pages/Brainstorm.tsx` | Brainstorming-Detail |
| `PG-052-PROCESS` | `frontend/src/pages/ProcessDesigner.tsx` | Process-Designer |
| `PG-060-TOOLS` | `frontend/src/pages/Tools.tsx` | Tools-Liste |
| `PG-061-ARCHITECTURE` | `frontend/src/pages/Architecture.tsx` | Architecture Rules |
| `PG-062-STANDARDS` | `frontend/src/pages/Standards.tsx` | Quality Standards |
| `PG-063-OPENBRAIN` | `frontend/src/pages/OpenBrain.tsx` | OpenBrain-View |
| `PG-070-COST` | `frontend/src/pages/Cost.tsx` | Cost/Performance-View |
| `PG-071-STATUS` | `frontend/src/pages/Status.tsx` | System-Status |
| `PG-072-METRICS` | `frontend/src/pages/Metrics.tsx` | Live-Metriken |
| `PG-080-SETTINGS` | `frontend/src/pages/Settings.tsx` | App-Settings |
| `PG-090-DASHBOARD` | `frontend/src/pages/Overview.tsx` | Haupt-Dashboard / Übersicht |

## Verwendung im Code

### 1. Page-ID in einer Seite anzeigen

```tsx
import { PageId } from "../components/PageId"
import { PAGE_IDS } from "../pageIds"

export default function MyPage() {
  return (
    <div>
      <h1>Meine Seite</h1>
      <PageId id={PAGE_IDS.MY_PAGE} />
      <p>Inhalt...</p>
    </div>
  )
}
```

### 2. Neue Page-ID registrieren

In `frontend/src/pageIds.ts`:

```typescript
export const PAGE_IDS = {
  // ... bestehende IDs ...
  MY_PAGE: "PG-NEW-MYPAGE",  // ← Neue ID
} as const
```

In `PAGE_ID_TO_FILE` Mapping hinzufügen:

```typescript
export const PAGE_ID_TO_FILE: Record<string, string> = {
  // ... bestehende Mappings ...
  "PG-NEW-MYPAGE": "frontend/src/pages/MyPage.tsx",
}
```

In `docs/PAGE_IDS.md` Tabelle ergänzen.

## Konventionen

### Format: `PG-<NNN>-<KATEGORIE>`

- **PG**: Prefix für "Page"
- **NNN**: Dreistellige Nummer, fortlaufend (001, 002, ...)
- **KATEGORIE**: Großbuchstaben, beschreibend (KANBAN, SOPS, MODELS, ...)

### Kategorie-Gruppen

- `PG-001-099` — Board / Tasks
- `PG-010-099` — SOPs
- `PG-020-099` — Models / Provider
- `PG-030-099` — Roles / SubAgents
- `PG-040-099` — Projects / Tasks
- `PG-050-099` — Process / Brainstorm / Ideas
- `PG-060-099` — Tools / Specials
- `PG-070-099` — Performance / Cost
- `PG-080-099` — Settings / Admin
- `PG-090-099` — Haupt-Dashboard

## Implementierung

- **Komponente**: `frontend/src/components/PageId.tsx`
- **Registry**: `frontend/src/pageIds.ts`
- **Dokumentation**: `docs/PAGE_IDS.md`

## Vorteile

1. **Schnellere Navigation im Code**: Mit `PG-001-KANBAN` weiß jeder Entwickler sofort, wo die Datei liegt
2. **Klare Kommunikation**: "Sieh dir PG-030-ROLES an" → eindeutig
3. **Dokumentation bleibt synchron**: Tabelle in `docs/PAGE_IDS.md` ist die Single Source of Truth
4. **Click-to-Copy im UI**: Entwickler können die ID schnell in Slack/Issues einfügen

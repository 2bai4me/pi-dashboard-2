import { useState, useMemo } from "react"
import { Brain, Search } from "lucide-react"

type BrainDevEntry = {
  id: string
  type: "architecture" | "knowledge" | "sop" | "dev"
  tags: string[]
  content: string
  date: string
}

// Mock-Daten — v2 hat kein OpenBrain-Backend
const MOCK_ENTRIES: BrainDevEntry[] = [
  {
    id: "8c4f0ceb",
    type: "architecture",
    tags: ["architecture", "openbrain"],
    content: "Hermes nutzt lokales openBrain als zentralen Wissensspeicher. pB (Port 9100) + bB (Port 9101) ueber Bridge Port 50005 erreichbar.",
    date: "2026-06-15"
  },
  {
    id: "9a2b1c4d",
    type: "architecture",
    tags: ["architecture", "openbrain"],
    content: "Lokale openBrain-Instanzen pB (privat) und bB (business) als zentraler Speicher via FastAPI+ChromaDB auf Ports 9100/9101. Auto-Routing entscheidet anhand thought_type.",
    date: "2026-06-14"
  },
  {
    id: "3e7f8a1b",
    type: "knowledge",
    tags: ["knowledge", "DEV", "Provider", "Evaluation", "Optimierung"],
    content: "Provider-Evaluation: Hermes fuehrt Buch darueber, welcher Provider fuer welchen Task-Typ die besten Ergebnisse liefert. Kriterien: Code-Qualitaet, Geschwindigkeit, Korrektheit, Fehlerquote. Ziel: Fuer jeden Task-Typ (Boilerplate, komplexe Logik, Refactoring, Testing, Security, Architektur) den optimalen Provider kennen und einsetzen. Ergebnisse werden in bB dokumentiert. Hermes optimiert kontinuierlich die Provider×Task-Zuordnung.",
    date: "2026-06-14"
  },
  {
    id: "5d9e2f8c",
    type: "sop",
    tags: ["sop", "skill", "meta", "dev", "architektur", "mirror"],
    content: "Dev/Architecture-Auszug gespiegelt. Volltext in pB ID 8c4f0ceb.",
    date: "2026-06-13"
  },
  {
    id: "7b3c1d9e",
    type: "knowledge",
    tags: ["knowledge", "DEV", "Agenten", "Hermes", "PI-Agent", "Agent Zero", "OpenClaw"],
    content: "Agenten-Uebersicht: HERMES (DeepSeek V4 Pro) = Manager/Chefarchitekt auf Tower + NAS, koordiniert via GitHub Issues und MCP. PI-AGENT (DeepSeek V4 Flash) = Senior-Entwickler, MCP-Server :50001, REST :50002, Zugriff auf NAS, Docker, Plane, Agent Zero. AGENT ZERO (DeepSeek) = Docker funny_almeida :32774, im plane-Netzwerk, Zugriff auf Plane, pB, NAS. OPENCLAW (Kimi/Moonshot) = Tester via hermes-openclaw-bridge auf GitHub.",
    date: "2026-06-12"
  },
  {
    id: "2a8f4b6c",
    type: "knowledge",
    tags: ["knowledge", "DEV", "Agenten", "Kommunikation", "MCP", "GitHub-Issues"],
    content: "Agent-Kommunikation: Hermes↔OpenClaw via hermes-openclaw-bridge (GitHub Issues, Labels task-review/analysis/research, status:pending|done). Hermes↔Agent Zero via MCP (PI-Agent Bridge auf :50001) oder direkt :32774. Hermes↔PI-Agent via MCP :50001 oder REST :50002. PI-Agent↔Plane via REST API (plane_api_4ce5_…). NAS-Agenten via SSH (tower-agents.py). Agent Zero↔pB via Supabase Cloud MCP. Alle Brain-Zugriffe: auto-routing (code/architecture→bB, personal→pB).",
    date: "2026-06-11"
  },
  {
    id: "4f6a2c1d",
    type: "architecture",
    tags: ["architecture", "microservices", "soa", "DEV"],
    content: "Service-Oriented-Architecture: 12 eigenstaendige Services (Pipeline, Service-Cockpit, openBRAIND, etc.) kommunizieren via REST + MCP. Jeder Service hat eigenen Port (50001-50010), eigenen Container (Docker), eigene DB-Zugriffe. Plane-API (plane_api_4ce5) ist zentral fuer Task-Tracking.",
    date: "2026-06-10"
  },
  {
    id: "6c8b3e5a",
    type: "knowledge",
    tags: ["knowledge", "code-standards", "TypeScript", "Python", "DEV"],
    content: "Code-Standards: TypeScript strict mode, Python 3.14+ mit Type-Hints, kein `any` auzer in Type-Guards, Pydantic v2 fuer Schemas, SQLAlchemy 2.0 mit Async, Alembic fuer Migrations. Tests: pytest + pytest-asyncio. Frontend: React 19 + Vite + TanStack Query, KEIN Tailwind ausser fuer Color-Tokens.",
    date: "2026-06-09"
  },
]

const TAG_COLORS: Record<string, string> = {
  architecture: "blue",
  knowledge: "blue",
  sop: "blue",
  dev: "orange",
  DEV: "orange",
  openbrain: "orange",
  Provider: "orange",
  Evaluation: "orange",
  Optimierung: "orange",
  skill: "orange",
  meta: "orange",
  architektur: "orange",
  mirror: "orange",
  Agenten: "orange",
  Hermes: "orange",
  "PI-Agent": "orange",
  "Agent Zero": "orange",
  OpenClaw: "orange",
  Kommunikation: "orange",
  MCP: "orange",
  "GitHub-Issues": "orange",
  microservices: "orange",
  soa: "orange",
  "code-standards": "orange",
  TypeScript: "orange",
  Python: "orange",
}

function tagClass(tag: string): string {
  const color = TAG_COLORS[tag] || "gray"
  return `badge badge-${color}`
}

export default function BrainDevTab() {
  const [search, setSearch] = useState("")

  const filtered = useMemo(() => {
    if (!search.trim()) return MOCK_ENTRIES
    const q = search.toLowerCase()
    return MOCK_ENTRIES.filter(e =>
      e.content.toLowerCase().includes(q) ||
      e.tags.some(t => t.toLowerCase().includes(q))
    )
  }, [search])

  // Sammle alle einzigartigen Topics
  const allTopics = useMemo(() => {
    const s = new Set<string>()
    MOCK_ENTRIES.forEach(e => e.tags.forEach(t => s.add(t)))
    return Array.from(s).sort()
  }, [])

  return (
    <div>
      <div className="page-header">
        <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <Brain size={18} color="var(--color-hermes-accent-blue)" /> OpenBrain DEV
        </h2>
        <p>Entwicklungs-Wissen aus dem OpenBrain — SOA, Microservices, Code Standards</p>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <div style={{ position: "relative", flex: 1, maxWidth: 400 }}>
          <Search size={12} style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", color: "var(--color-hermes-text-secondary)" }} />
          <input
            className="input"
            placeholder="thoughts found · Topics: ..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ paddingLeft: 26, fontSize: 12 }}
          />
        </div>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {allTopics.slice(0, 6).map(t => (
            <button key={t} className={tagClass(t)} onClick={() => setSearch(t)} style={{ fontSize: 10, cursor: "pointer", border: "none" }}>
              {t}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 40, color: "var(--color-hermes-text-secondary)" }}>
          Keine Treffer fuer „<strong>{search}</strong>".
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {filtered.map(entry => (
            <div key={entry.id} className="card" style={{ borderLeft: `3px solid var(--color-hermes-accent-blue)`, padding: 12 }}>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 6 }}>
                {entry.tags.map(tag => (
                  <span key={tag} className={tagClass(tag)} style={{ fontSize: 10 }}>
                    {tag}
                  </span>
                ))}
              </div>
              <div style={{ fontSize: 12, lineHeight: 1.6, whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)" }}>
                {entry.content}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

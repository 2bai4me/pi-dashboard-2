// providerDefaults.ts — Zentrale Liste der Default-Provider-Tiles (FIX 23.06.2026: Modul fehlte)
// Wird in ApiKeys.tsx und potentiell im SOP-ModelSelect genutzt.

export interface ProviderTile {
  provider: string
  model: string
  name: string
  label?: string
  description?: string
  isLocal?: boolean
  id?: string
  api_key?: string | null
  is_active?: boolean
}

export const DEFAULT_PROVIDER_TILES: ProviderTile[] = [
  {
    provider: "minimax-direct",
    model: "minimax-m3",
    name: "minimax-m3 (Default)",
    label: "minimax-m3 (Default)",
    description: "Schnelles, kostenguenstiges Modell fuer allgemeine Aufgaben",
  },
  {
    provider: "ollama",
    model: "gemma4:12b",
    name: "gemma4:12b (lokal)",
    label: "gemma4:12b (lokal)",
    description: "Lokal ausgefuehrtes Google-Gemma-Modell",
    isLocal: true,
  },
  {
    provider: "ollama",
    model: "qwen3:30b",
    name: "qwen3:30b (lokal)",
    label: "qwen3:30b (lokal)",
    description: "Groesseres Qwen-Modell fuer komplexere Aufgaben",
    isLocal: true,
  },
  {
    provider: "kimi",
    model: "kimi-k2.7-code",
    name: "kimi-k2.7-code",
    label: "kimi-k2.7-code",
    description: "Spezialisiert auf Code-Generierung",
  },
]

export function isLocalProvider(provider: string): boolean {
  return provider === "ollama" || provider.startsWith("local-")
}

// useAvailableModels.ts — Hook für verfügbare Modelle (Provider-Credentials + Default-Provider)
// FIX 23.06.2026 (Vite-Build-Fehler): Hook existierte nicht, wurde in SubAgents.tsx importiert
// Quelle: Provider-Credentials via /api/provider-credentials
//
// Liefert: Array<{ value: string, label: string, provider?: string, credential_id?: string }>
// value-Format: "model_id" oder "credential_id:model_id" je nach Quelle

import { useQuery } from "@tanstack/react-query"
import { api } from "../api"

export interface AvailableModel {
  value: string
  label: string
  provider?: string
  credential_id?: string
}

export function useAvailableModels() {
  const { data: credentialsData } = useQuery({
    queryKey: ["provider-credentials", "active"],
    queryFn: () => api.listProviderCredentials(),
    staleTime: 60_000,
  })

  const credentials: any[] = (credentialsData as any)?.items ||
    (Array.isArray(credentialsData) ? credentialsData : []) || []

  // Default-Modelle als Fallback (zentrale Provider-Liste)
  const defaults: AvailableModel[] = [
    { value: "minimax/minimax-m3", label: "minimax-m3 (Default)", provider: "minimax-direct" },
    { value: "ollama/gemma4:12b", label: "gemma4:12b (lokal)", provider: "ollama" },
    { value: "ollama/qwen3:30b", label: "qwen3:30b (lokal)", provider: "ollama" },
    { value: "kimi/kimi-k2.7-code", label: "kimi-k2.7-code", provider: "kimi" },
  ]

  // Aktive Credentials als Modelle
  const active = credentials
    .filter((c: any) => c.is_active !== false)
    .map((c: any): AvailableModel => ({
      value: `${c.id}:${c.model}`,
      label: `${c.name || c.model} (${c.provider})`,
      provider: c.provider,
      credential_id: c.id,
    }))

  // Deduplizieren: aktive Credentials zuerst, dann defaults
  const seen = new Set(active.map((m) => m.value))
  const merged = [...active]
  for (const d of defaults) {
    if (!seen.has(d.value)) merged.push(d)
  }
  return merged
}

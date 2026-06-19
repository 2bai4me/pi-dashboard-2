import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../api"
import { RefreshCw } from "lucide-react"

export default function Models() {
  const qc = useQueryClient()
  const { data: pricing } = useQuery({ queryKey: ["pricing"], queryFn: () => api.getPricing() })
  const refreshMut = useMutation({
    mutationFn: () => api.refreshPricing(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pricing"] }),
  })

  return (
    <div>
      <div className="page-header">
        <h1>Models</h1>
        <p>Provider-Preise und Modell-Liste</p>
      </div>
      <button className="btn btn-primary mb-3" onClick={() => refreshMut.mutate()} disabled={refreshMut.isPending}>
        <RefreshCw size={12} /> Preise aktualisieren
      </button>
      <table className="data-table">
        <thead>
          <tr>
            <th>Provider</th>
            <th>Modell</th>
            <th>Input $/M</th>
            <th>Output $/M</th>
            <th>Source</th>
            <th>Last updated</th>
          </tr>
        </thead>
        <tbody>
          {pricing && Object.entries(pricing).flatMap(([prov, models]: [string, any]) =>
            Object.entries(models).map(([model, p]: [string, any]) => (
              <tr key={`${prov}/${model}`}>
                <td className="mono">{prov}</td>
                <td className="mono">{model}</td>
                <td className="mono">${p.input_per_1m}</td>
                <td className="mono">${p.output_per_1m}</td>
                <td className="text-xs text-dim">{p.source}</td>
                <td className="text-xs">{p.last_updated ? new Date(p.last_updated).toLocaleString("de-DE") : "—"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

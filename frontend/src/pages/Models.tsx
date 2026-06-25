import ApiKeys from "./ApiKeys"
import { PageId } from "../components/PageId"
import { PAGE_IDS } from "../pageIds"

export default function Models() {
  return (
    <div>
      <div className="page-header">
        <h1>Models</h1>
        <PageId id={PAGE_IDS.MODELS} />
        <p>Provider-Übersicht und API-Key-Verwaltung</p>
      </div>

      <ApiKeys />
    </div>
  )
}
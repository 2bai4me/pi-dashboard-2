"""Auto-Component-Router (User-Direktive 24.06.2026).

Wenn ein neuer Task erstellt wird und keine component_id angegeben ist,
entscheidet der CIO (LLM) anhand von Title+Description, welche Component
(Pipeline, Frontend, NotebookLM, etc.) zustaendig ist.

Strategie:
  1. Heuristik-First (schnell, kostenlos): Schlusselwoerter in Title/Description
     -> pipeline/frontend/notebooklm/infra/database
  2. Falls unklar: LLM-Aufruf (CIO) zur Entscheidung
  3. Fallback: null (Task bleibt ohne Component, manuelle Zuordnung)
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


# Schlusselwort-Mapping (Heuristik)
KEYWORD_MAP = {
    "pipeline": [
        r"\bpipeline\b", r"\brender\b", r"\bcontent[ _-]?generation\b",
        r"\bsmproducer\b", r"\bjob[ _-]?(queue|worker)\b", r"\bffmpeg\b",
        r"\bvideo[ _-]?produ", r"\bproduction[ _-]?pipeline\b",
    ],
    "frontend": [
        r"\bfrontend\b", r"\breact\b", r"\bvite\b", r"\bui\b",
        r"\bdashboard\b", r"\bdark[ _-]?theme\b", r"\bcomponent\b",
        r"\bpage\b", r"\bmodal\b", r"\bbrowser\b", r"\bclient[ _-]?side\b",
    ],
    "notebooklm": [
        r"\bnotebooklm\b", r"\bnotebook[ _-]?lm\b", r"\bai[ _-]?source\b",
        r"\bcontent[ _-]?source\b", r"\btopic[ _-]?generation\b",
        r"\bsource[ _-]?data\b",
    ],
    "database": [
        r"\b(database|db|migration|schema|sql|sqlite|postgres)\b",
        r"\btable\b", r"\bcolumn\b", r"\bforeign[ _-]?key\b",
    ],
    "infra": [
        r"\b(infra|docker|kubernetes|k8s|traefik|nginx|authentik)\b",
        r"\bci[ _-]?/?cd\b", r"\bdeploy(ment)?\b",
    ],
}


def _heuristic_route(text_lower: str, components: list[dict]) -> Optional[int]:
    """Versucht anhand von Schluesselwoertern die Component zu erraten."""
    if not text_lower or not components:
        return None
    scores: dict[int, int] = {}
    for comp in components:
        cid = comp["id"]
        slug = comp["slug"].lower()
        comp_type = (comp.get("type") or "").lower()
        score = 0
        # 1) Slug-Match
        if slug in text_lower:
            score += 10
        # 2) Type-Match
        if comp_type in text_lower:
            score += 5
        # 3) Keyword-Match
        for pattern in KEYWORD_MAP.get(slug, []):
            if re.search(pattern, text_lower, re.IGNORECASE):
                score += 3
        if score > 0:
            scores[cid] = score
    if not scores:
        return None
    # Best Score gewinnt
    best = max(scores.items(), key=lambda x: x[1])
    # Confidence-Check: Wenn 2 Components sehr nah beieinander sind, ist unklar
    sorted_scores = sorted(scores.values(), reverse=True)
    if len(sorted_scores) > 1 and sorted_scores[0] - sorted_scores[1] < 2:
        return None  # Zu unklar, LLM muss entscheiden
    return best[0]


async def route_task_to_component(
    db: Session,
    project_id: str,
    task_text: str,
) -> Optional[int]:
    """Entscheidet, welche Component fuer einen Task zustaendig ist.

    Reihenfolge:
      1. Heuristik (schnell)
      2. LLM-CIO (langsamer, genauer)
      3. None (manuell zuordnen)
    """
    # Lade Components des Projekts
    comp_rows = db.execute(text("""
        SELECT id, slug, name, component_type, description
        FROM project_components WHERE project_id = :pid
        ORDER BY sort_order
    """), {"pid": project_id}).fetchall()
    components = [
        {"id": r[0], "slug": r[1], "name": r[2], "type": r[3], "description": r[4]}
        for r in comp_rows
    ]
    if not components:
        return None  # Kein Component-System vorhanden

    # 1) Heuristik
    text_lower = task_text.lower()
    result = _heuristic_route(text_lower, components)
    if result is not None:
        return result

    # 2) LLM-CIO
    try:
        from ..services.llm_service import chat_completion
        from ..utils.json_repair import safe_json_loads

        comp_list = "\n".join(
            f"  - id={c['id']}, slug={c['slug']}, name={c['name']}, type={c['type'] or '-'}"
            for c in components
        )
        prompt = f"""Du bist der CIO (Chief Intelligence Officer) eines Projekts.
Du musst entscheiden, welche architektonische Component fuer diesen Task zustaendig ist.

**Verfuegbare Components:**
{comp_list}

**Task (Title + Description):**
{task_text[:500]}

Antworte NUR mit JSON: {{"component_id": <int>, "confidence": <0-100>, "reason": "<kurz>"}}
Wenn keine Component passt: {{"component_id": null, "confidence": 0, "reason": "..."}}"""

        result_obj = await chat_completion(
            messages=[
                {"role": "system", "content": "Du bist ein praeziser CIO-Router. Antworte nur mit JSON."},
                {"role": "user", "content": prompt},
            ],
            model="minimax-m3",
            provider="minimax-direct",
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        parsed = safe_json_loads(result_obj.get("content", "{}"))
        cid = parsed.get("component_id")
        if cid is not None and isinstance(cid, int):
            # Validierung: Component muss zum Projekt gehoeren
            if any(c["id"] == cid for c in components):
                return cid
    except Exception:
        pass

    # 3) Fallback
    return None
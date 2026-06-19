"""Benennt 'ToDo' / 'To Do' / 'TODO' in Tasks und SOPs zu 'GO' um.

Strategie:
- DB-Status 'todo' bleibt 'todo' (technisch, wuerde sonst Code brechen)
- Task-Texte (title, description, success_criteria, tags): 'ToDo' -> 'GO'
- SOP-Step-Texte (description, ai_instructions_md, name): 'ToDo' / 'TODO' -> 'GO'
- SubProcess-Namen in BPMN: 'To Do' -> 'GO'

Wichtig: Wir machen KEINE Ersetzungen in:
- IDs (koennten breaking sein)
- Code (Python, TypeScript)
- Status-Keys in DB ('todo' bleibt technisch)
- URLs/Endpoints
"""
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy.orm.attributes import flag_modified
from app.db.base import SessionLocal
from app.models.task import Task
from app.models.sop import SOP, SOPStep, SOPStepRule


def replace_todo(text: str) -> str:
    """Ersetzt ToDo / To Do / TODO durch GO.

    Reihenfolge wichtig: Zuerst mehrdeutige Varianten, dann generisches TODO.
    """
    if not text:
        return text
    # 1. "To Do" / "to do" -> "GO" (Spalten-Label, Beschreibungen)
    text = re.sub(r"\bTo Do\b", "GO", text)
    text = re.sub(r"\bto do\b", "go", text, flags=re.IGNORECASE)
    # 2. "ToDo" / "todo" als Word -> "GO" / "go"
    text = re.sub(r"\bToDo\b", "GO", text)
    text = re.sub(r"\btodo\b", "go", text)  # lowercase
    # 3. "TODO" uppercase -> "GO" (Platzhalter-Marker in Code-Kommentaren etc.)
    text = re.sub(r"\bTODO\b", "GO", text)
    return text


def main():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("RENAME: ToDo / To Do / TODO -> GO")
        print("=" * 70)
        print()

        # === 1) Tasks: title, description, success_criteria, tags ===
        tasks = db.query(Task).all()
        print(f"[Tasks] Pruefe {len(tasks)} Tasks...")
        task_changes = 0
        for t in tasks:
            changed = False
            new_title = replace_todo(t.title or "")
            new_desc = replace_todo(t.description or "")
            new_sc = None
            if t.success_criteria:
                # success_criteria ist JSON-Liste
                import json
                sc = t.success_criteria
                if isinstance(sc, str):
                    try:
                        sc = json.loads(sc)
                    except Exception:
                        sc = []
                new_sc = [replace_todo(s) if isinstance(s, str) else replace_todo(s.get("text", "")) for s in sc] if isinstance(sc, list) else sc
                if new_sc != sc:
                    changed = True

            new_tags = None
            if t.tags:
                import json
                tags = t.tags
                if isinstance(tags, str):
                    try:
                        tags = json.loads(tags)
                    except Exception:
                        tags = []
                new_tags = [replace_todo(tag) for tag in tags] if isinstance(tags, list) else tags
                if new_tags != tags:
                    changed = True

            if new_title != t.title or new_desc != t.description or new_tags is not None or new_sc is not None:
                if new_title != t.title:
                    t.title = new_title
                    changed = True
                if new_desc != t.description:
                    t.description = new_desc
                    changed = True
                if new_sc is not None:
                    t.success_criteria = json.dumps(new_sc) if new_sc else t.success_criteria
                    changed = True
                if new_tags is not None:
                    t.tags = json.dumps(new_tags) if new_tags else t.tags
                    changed = True
                task_changes += 1
        db.commit()
        print(f"  -> {task_changes} Tasks aktualisiert")

        # === 2) SOPs: name, description ===
        sops = db.query(SOP).all()
        print(f"\n[SOPs] Pruefe {len(sops)} SOPs...")
        sop_changes = 0
        for s in sops:
            new_name = replace_todo(s.name or "")
            new_desc = replace_todo(s.description or "")
            if new_name != s.name or new_desc != s.description:
                s.name = new_name
                s.description = new_desc
                sop_changes += 1
        db.commit()
        print(f"  -> {sop_changes} SOPs aktualisiert")

        # === 3) SOPSteps: name, description, ai_instructions_md ===
        steps = db.query(SOPStep).all()
        print(f"\n[Steps] Pruefe {len(steps)} Steps...")
        step_changes = 0
        for s in steps:
            new_name = replace_todo(s.name or "")
            new_desc = replace_todo(s.description or "")
            new_exp = replace_todo(s.expected_result or "")
            ap = s.action_params or {}
            new_ai = replace_todo(ap.get("ai_instructions_md", "")) if ap.get("ai_instructions_md") else ap.get("ai_instructions_md", "")
            new_ap = dict(ap)
            if new_ai != ap.get("ai_instructions_md", ""):
                new_ap["ai_instructions_md"] = new_ai

            if (new_name != s.name or new_desc != s.description or
                new_exp != s.expected_result or new_ap != ap):
                s.name = new_name
                s.description = new_desc
                s.expected_result = new_exp
                s.action_params = new_ap
                flag_modified(s, "action_params")
                step_changes += 1
        db.commit()
        print(f"  -> {step_changes} Steps aktualisiert")

        # === 4) Rules: description ===
        rules = db.query(SOPStepRule).all()
        print(f"\n[Rules] Pruefe {len(rules)} Rules...")
        rule_changes = 0
        for r in rules:
            new_desc = replace_todo(r.description or "")
            if new_desc != r.description:
                r.description = new_desc
                rule_changes += 1
        db.commit()
        print(f"  -> {rule_changes} Rules aktualisiert")

        # === 5) BPMN-XML: SubProcess-Namen (falls vorhanden) ===
        print(f"\n[BPMN] Pruefe gespeicherte BPMN-XMLs in SOPs...")
        bpmn_changes = 0
        for s in sops:
            if s.bpmn_xml and "To Do" in s.bpmn_xml:
                new_xml = s.bpmn_xml.replace("To Do", "GO")
                s.bpmn_xml = new_xml
                bpmn_changes += 1
        db.commit()
        print(f"  -> {bpmn_changes} BPMN-XMLs aktualisiert")

        print()
        print("=" * 70)
        print("FERTIG")
        print("=" * 70)
        print(f"Zusammenfassung:")
        print(f"  Tasks:  {task_changes} veraendert")
        print(f"  SOPs:   {sop_changes} veraendert")
        print(f"  Steps:  {step_changes} veraendert")
        print(f"  Rules:  {rule_changes} veraendert")
        print(f"  BPMN:   {bpmn_changes} veraendert")
        print()
        print("HINWEIS: DB-Status 'todo' bleibt 'todo' (technisch, wuerde Code brechen).")
        print("Nur die ANZEIGE im Frontend wurde auf 'GO' geaendert.")

    finally:
        db.close()


if __name__ == "__main__":
    main()

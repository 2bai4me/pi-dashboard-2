"""Erstellt verstaendliche AgentQuestions fuer alle rueckfrage-Tasks."""
import sys
import os
import json
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.base import SessionLocal
from app.models.agent_question import AgentQuestion
from app.models.task import Task


def make_question(t, category, cio_q):
    """Erstellt eine verstaendliche AgentQuestion fuer den Task."""
    titles = {
        "todo_keyword": f'Erfolgskriterien fuer "{t.title[:50]}" ergaenzen',
        "description_short": f'Beschreibung fuer "{t.title[:50]}" erweitern',
        "architecture_conflict": f'Architektur-Konflikt bei "{t.title[:50]}" klaeren',
        "general": f'Klaerung zu "{t.title[:50]}" benoetigt',
    }
    questions = {
        "todo_keyword": (
            f'Im Task-Titel oder in der Description kommt das Wort "TODO" oder eine aehnliche '
            f'Platzhalter-Markierung vor. Das deutet darauf hin, dass der Task noch nicht '
            f'vollstaendig definiert ist.\n\n'
            f'**Konkret brauche ich von dir:**\n'
            f'- Welche konkreten, messbaren Ergebnisse soll "{t.title}" liefern?\n'
            f'- Woran erkenne ich, dass der Task erfolgreich abgeschlossen ist?\n'
            f'- Welche Akzeptanzkriterien (GIVEN-WHEN-THEN) gelten?'
        ),
        "description_short": (
            f'Die Description des Tasks ist zu kurz oder fehlt. Der Worker braucht mehr '
            f'Kontext, um die Aufgabe sinnvoll umzusetzen.\n\n'
            f'**Konkret brauche ich von dir:**\n'
            f'- Was genau soll "{t.title}" machen?\n'
            f'- Welche Akzeptanzkriterien gelten (mind. 3 Stueck)?\n'
            f'- Welche Edge-Cases sind zu beachten?\n'
            f'- Welche Constraints (Zeit, Performance, Security) gelten?'
        ),
        "architecture_conflict": (
            f'Der CIO hat einen Konflikt zwischen deiner Anforderung und unseren '
            f'Architektur-Vorgaben erkannt.\n\n'
            f'**Konkret brauche ich von dir:**\n'
            f'- Verstehe und akzeptierst du die Architektur-Vorgabe?\n'
            f'- Oder gibt es einen triftigen Grund, davon abzuweichen?\n'
            f'- Falls Abweichung noetig: warum und wie?'
        ),
        "general": (
            f'Beim Triage des Tasks sind dem CIO einige Punkte aufgefallen, die vor der '
            f'Implementierung geklaert werden sollten.\n\n'
            f'**Bitte schau dir die folgenden Punkte an und beantworte sie:**\n\n'
            f'{cio_q}'
        ),
    }
    descriptions = {
        "todo_keyword": (
            '## Warum diese Rueckfrage?\n\n'
            'Das Wort "TODO" in der Description signalisiert, dass die Anforderung noch '
            'unvollstaendig ist. Ohne klare Erfolgskriterien weiss der Worker nicht, '
            'wann der Task "fertig" ist.\n\n'
            '## Vorgehen (Empfehlung)\n\n'
            '1. Lies den aktuellen Task-Titel und die Description\n'
            '2. Ersetze jedes "TODO" durch konkrete Information\n'
            '3. Formuliere 3-5 messbare Akzeptanzkriterien\n\n'
            '## Beispiel-Format\n\n'
            '```\n'
            '- [ ] GIVEN [Ausgangszustand] WHEN [Aktion] THEN [Erwartetes Ergebnis]\n'
            '- [ ] Feature X funktioniert mit Input Y und produziert Output Z\n'
            '- [ ] Bestehende Tests in test_xy.py laufen gruen\n'
            '```\n\n'
            '## Was passiert ohne Antwort?\n\n'
            'Ohne Erfolgskriterien bleibt der Task in rueckfrage und kann nicht in TODO. '
            'Der Worker kann nicht sinnvoll starten.'
        ),
        "description_short": (
            '## Warum diese Rueckfrage?\n\n'
            'Die aktuelle Description enthaelt zu wenig Information, damit ein Worker die '
            'Aufgabe eigenstaendig umsetzen kann. Eine gute Description ist 200+ Worte '
            'und enthaelt Use Cases, Akzeptanzkriterien und Constraints.\n\n'
            '## Vorgehen (Empfehlung)\n\n'
            '1. **Ziel**: Was soll erreicht werden? (1-2 Saetze)\n'
            '2. **Use Cases**: Wer nutzt das Feature und wie? (3-5 Stueck)\n'
            '3. **Akzeptanzkriterien**: Woran merke ich, dass es funktioniert? (3-5 Stueck)\n'
            '4. **Edge-Cases**: Was sind ungewoehnliche Eingaben/Situationen?\n'
            '5. **Constraints**: Performance, Security, Browser, Devices\n\n'
            '## Beispiel-Struktur\n\n'
            '```\n'
            '## Was\nBeschreibung der Funktion in 2-3 Saetzen.\n\n'
            '## Akzeptanzkriterien\n- [ ] Kriterium 1\n- [ ] Kriterium 2\n\n'
            '## Edge-Cases\n- Eingabe X fuehrt zu Verhalten Y\n- ...\n'
            '```'
        ),
        "architecture_conflict": (
            '## Warum diese Rueckfrage?\n\n'
            'Unsere OpenBrain-Architektur-Vorgaben definieren Standards, die Konsistenz '
            'und Wartbarkeit ueber Projekte hinweg sicherstellen. Wenn du explizit von '
            'diesen Standards abweichen willst, brauche ich eine Begruendung.\n\n'
            '## Vorgehen (Empfehlung)\n\n'
            '1. Lies die betroffene Architektur-Vorgabe in OpenBrain\n'
            '2. Pruefe, ob deine Anforderung wirklich im Konflikt steht\n'
            '3. Optionen:\n'
            '   - **Akzeptieren**: Anforderung an Vorgabe anpassen\n'
            '   - **Abweichung begruenden**: Warum ist die Abweichung noetig?\n\n'
            '## Was passiert ohne Antwort?\n\n'
            'Ohne Klarstellung kann der Task nicht in TODO gehen, weil unklar ist, '
            'nach welcher Architektur implementiert werden soll.'
        ),
        "general": (
            f'## Details\n\n'
            f'Beim Triage-Prozess wurde der Task "{t.title}" geprueft. '
            f'Folgende Aspekte sind noch unklar und sollten vor der Bearbeitung '
            f'geklaert werden.'
        ),
    }
    recommendations = {
        "todo_keyword": (
            'Nimm dir 2 Minuten und ergaenze 3-5 konkrete Akzeptanzkriterien. '
            'Falls etwas wirklich unklar ist, schreibe "unbekannt" dazu.'
        ),
        "description_short": (
            'Verwende die Struktur "Was / Use Cases / Akzeptanzkriterien / Edge-Cases / '
            'Constraints". Mindestens 200 Worte, ideal 500+. '
            'Konkrete Beispiele helfen dem Worker, die Aufgabe richtig zu verstehen.'
        ),
        "architecture_conflict": (
            'Pruefe zuerst, ob die Architektur-Vorgabe wirklich im Konflikt steht. '
            'In 80% der Faelle ist die Anforderung mit der Vorgabe vereinbar, wenn man '
            'sie richtig interpretiert. Falls Abweichung noetig: schreibe eine klare '
            'Begruendung (was, warum, welche Alternativen du geprueft hast).'
        ),
        "general": (
            'Beantworte die offenen Punkte direkt in der Task-Description oder hier. '
            'Danach kann der Worker den Task in TODO uebernehmen.'
        ),
    }
    return {
        "title": titles[category],
        "question": questions[category],
        "description": descriptions[category],
        "recommendation": recommendations[category],
    }


def main():
    db = SessionLocal()
    try:
        rueckfrage_tasks = db.query(Task).filter(Task.status == "rueckfrage").all()
        print(f"Erstelle verstaendliche AgentQuestions fuer {len(rueckfrage_tasks)} Tasks...")
        print()

        created = 0
        skipped = 0
        for t in rueckfrage_tasks:
            # Pruefe, ob schon eine pending AgentQuestion existiert
            all_pending = db.query(AgentQuestion).filter(AgentQuestion.status == "pending").all()
            has_question = False
            for q in all_pending:
                ctx = q.context
                if isinstance(ctx, str):
                    try:
                        ctx = json.loads(ctx)
                    except Exception:
                        ctx = {}
                if isinstance(ctx, dict) and ctx.get("task_id") == t.id:
                    has_question = True
                    break
            if has_question:
                skipped += 1
                continue

            # Parse die alte cio_question
            cio_q = (t.meta or {}).get("cio_question", "") if t.meta else ""
            cio_q_lower = cio_q.lower()

            # Kategorisiere
            if "todo" in cio_q_lower or "konflikt-keyword" in cio_q_lower:
                category = "todo_keyword"
            elif "description" in cio_q_lower or "erfolgskriterien" in cio_q_lower or "fehlt oder zu kurz" in cio_q_lower:
                category = "description_short"
            elif "architektur" in cio_q_lower or "soa" in cio_q_lower or "fastapi" in cio_q_lower:
                category = "architecture_conflict"
            else:
                category = "general"

            tmpl = make_question(t, category, cio_q)

            aq = AgentQuestion(
                id=f"q-{uuid.uuid4().hex[:12]}",
                agent_id="cio-auto",
                agent_level="C-Level",
                agent_label="CIO (Triage-Heuristik)",
                question_type="text",
                title=tmpl["title"],
                question=tmpl["question"],
                description=tmpl["description"],
                recommendation=tmpl["recommendation"],
                options=[],
                options_config=None,
                context={
                    "task_id": t.id,
                    "task_title": t.title,
                    "task_priority": t.priority,
                    "auto_triage": True,
                    "category": category,
                    "old_cio_question": cio_q,
                },
                priority="high" if t.priority >= 80 else ("medium" if t.priority >= 50 else "low"),
                status="pending",
            )
            db.add(aq)
            created += 1
            print(f"  [OK] {t.id[:12]} | {category:25} | {t.title[:50]}")

        db.commit()
        print()
        print(f"Zusammenfassung:")
        print(f"  Erstellt:           {created} neue AgentQuestions")
        print(f"  Uebersprungen:      {skipped} (hatten schon eine)")

        # Verbleibende pruefen
        all_q = db.query(AgentQuestion).filter(AgentQuestion.status == "pending").all()
        print(f"  Total pending:      {len(all_q)}")

    finally:
        db.close()


if __name__ == "__main__":
    main()

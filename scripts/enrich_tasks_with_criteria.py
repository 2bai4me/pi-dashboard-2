"""Ergaenzt alle offenen Tasks mit 3-5 testbaren Erfolgskriterien.

Strategie:
- Pro Task: 3-5 messbare, testbare Kriterien
- Basierend auf Title + Description
- Speichern als JSON-Liste in task.success_criteria
- Bestehende Kriterien bleiben (oder werden ueberschrieben wenn sc < 3)
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy.orm.attributes import flag_modified
from app.db.base import SessionLocal
from app.models.task import Task


# Kriterien pro Task (manuell kuratiert fuer Qualitaet)
CRITERIA_MAP = {
    # === SpecCreator-Tasks ===
    "07d52db57acc": [
        "Vollstaendiges Anforderungsdokument fuer LeoTOOL in /docs/leotool-spec.md erstellt",
        "Dokument enthaelt 5+ messbare Akzeptanzkriterien (GIVEN-WHEN-THEN-Format)",
        "Use Cases, Datenmodell und Sequenzdiagramme sind enthalten",
        "Stakeholder + RACI-Matrix dokumentiert",
        "Spec wurde im OpenBrain als reference gespeichert",
    ],
    "67dc61ad2232": [
        "User-Input-Tool kann in SOP-Steps ausgewaehlt werden (Dropdown im Detail-Panel)",
        "Bei Klick auf den Rueckfrage-Button oeffnet sich das UserInputModal",
        "Modal zeigt Frage + Description + Empfehlung + Antwort-Textarea",
        "Antwort wird an AgentQuestion gesendet (POST /answer)",
        "Task-Kachel zeigt Input-Symbol wenn input_required=true",
    ],
    "2907dbdc4f97": [
        "Neuer Task wird angelegt und Auto-Triage bewertet ihn in <60s",
        "AgentQuestion wird mit Title + Description + Empfehlung erstellt",
        "Task-Kachel in rueckfrage-Spalte zeigt Input-Symbol",
        "User kann Antwort im Modal eingeben und abschicken",
        "Nach Antwort: Task wechselt zu triage (Auto-Workflow)",
    ],
    "72856f420f27": [
        "Demo-Task in SpecCreator erstellt",
        "Auto-Triage-Operator bewertet und schiebt in rueckfrage",
        "UserInputModal oeffnet sich mit Demo-Frage",
        "User kann Demo-Antwort geben",
        "Demo-Task wird erfolgreich abgeschlossen (Status done)",
    ],
    # === PI-Dashboard-2-Tasks ===
    "4b1c10460604": [
        "Selektieren-Button ist in der Performance-Ansicht (nicht mehr in Board-Ansicht)",
        "Bei Klick auf Selektieren werden alle Eintraeger zu einem Task hervorgehoben",
        "Task-IDs in der Performance-Liste werden vollstaendig angezeigt (mind. 12 Zeichen)",
        "Task-IDs sind per Klick kopierbar (Copy-to-Clipboard)",
        "Filter-Eingabefeld fuer Task-IDs funktioniert mit Reset-Button",
    ],
    "914609ddfcf4": [
        "Skill-Definition fuer Anforderungsmanagement in /docs/SKILL-ANFORDERUNGSMANAGEMENT.md erstellt",
        "Skill enthaelt Workflow: Anforderung -> Task -> SOP-Start -> User-Bestaetigung",
        "Cache-Invalidation in Kanban.tsx repariert (Task wird sofort nach Mutation sichtbar)",
        "Skill im OpenBrain gespeichert mit allen Schritten",
        "Mindestens 1 Task pro User-Anforderung wird automatisch erstellt",
    ],
    "49a7240fc450": [
        "Vite liefert nach Code-Aenderung sofort aktuelle Dateien (kein 0-Bytes-Response mehr)",
        "Cache-Invalidation funktioniert fuer HMR-Transforms",
        "Manueller 'rm -rf node_modules/.vite' ist nicht mehr noetig",
        "Vite-Restart-Funktion in Dev-Mode funktioniert automatisch",
        "Browser-Cache wird korrekt invalidiert bei jedem HMR-Update",
    ],
    "a214b8630040": [
        "Vite-Watchdog erkennt stale Transform-Output (0 Bytes / HTTP 000)",
        "Auto-Recovery startet Vite automatisch neu bei stale State",
        "Pre-Build-Hook leert .vite-Cache bei jedem npm run dev",
        "User merkt nichts mehr von Vite-Crashes (transparenter Restart)",
        "Logs zeigen Vite-Restart-Events im DevTools",
    ],
    "95364d56745a": [
        "User erhaelt E-Mail mit 6-stelligem Verifikations-Code nach Registrierung",
        "Code ist 10 Minuten gueltig (nicht mehr, nicht weniger)",
        "Verifizierungs-Endpoint /verify-email validiert Code korrekt",
        "Status 'email_verified' wird nach Erfolg auf 'true' gesetzt",
        "Login funktioniert nur mit verifizierter E-Mail (Sicherheit)",
    ],
    "b8b14bb1f2e7": [
        "SOP-Auswahlfeld zeigt den Namen der aktuellen SOP (z.B. 'Standard-Workflow Development')",
        "NICHT der statische Text 'Standard SOP' wird angezeigt",
        "Bei Wechsel der SOP aendert sich die Anzeige sofort (Reactivity)",
        "Wenn keine SOP gewaehlt ist, wird 'Keine SOP' oder aehnlich angezeigt",
        "Anzeige funktioniert fuer alle Boards im System",
    ],
    "224d8e5015e8": [
        "Login-Button ist im UI sichtbar und funktional",
        "OAuth2-Provider ist konfiguriert (Google oder GitHub)",
        "Redirect-Flow nach Login funktioniert (Authorization Code Grant)",
        "User-Token wird sicher gespeichert (HTTP-Only Cookie oder SessionStorage)",
        "Logout-Button invalidiert Token und leitet auf /login zurueck",
    ],
    "7e3961a5461a": [
        "Beim Klick auf ein Projekt in der Sidebar oeffnet sich der Board-Tab (nicht Brainstorming)",
        "Aktive Tab-Anzeige reflektiert den korrekten Initial-Tab",
        "URL-Parameter ?tab=board funktioniert fuer direkten Deep-Link",
        "Tab-Wechsel zu Brainstorming funktioniert weiterhin",
        "Keine Endlosschleife bei Tab-Wechsel",
    ],
    "75db0e2b954d": [
        "Initial-Tab auf 'Board' gesetzt in der onSelect-Funktion",
        "Auch in setNewProjectModal-Handler korrekt initialisiert",
        "Test in Browser: Projekt-Klick oeffnet direkt Board-Ansicht",
        "Bestehende Tests fuer Sidebar-Navigation bleiben gruen",
        "TypeScript-Build ohne Fehler",
    ],
    "44437c38a33c": [
        "Task-IDs in der Performance-Liste vollstaendig angezeigt (mind. 12 Zeichen)",
        "Bei Hover ueber Task-ID erscheint Tooltip mit vollstaendiger ID",
        "Klick auf Task-ID kopiert ID in Zwischenablage",
        "Filter-Eingabefeld fuer Task-IDs funktioniert (zeigt nur passende Eintraeger)",
        "Bei aktivem Filter: nur Eintraeger dieser Task-ID (transitions + history + token_usage)",
    ],
    "290eb448654d": [
        "Status-Wechsel ist nach 5s sichtbar (nicht sofort, damit User die Kachel sehen kann)",
        "Auto-Triage-Operator bewertet den Task innerhalb 30s nach Status-Wechsel",
        "5s-Verzoegerung gilt fuer ALLE Status-Wechsel (von User und automatisch)",
        "Audit-Log dokumentiert den 5s-Delay korrekt",
        "User kann die Kachel in jeder Phase 5s lang beobachten",
    ],
    "1003b795efb6": [
        "Generischer SOP-Mechanismus mit Phase/Trigger/Action-Definitionen",
        "Neue SOPs koennen ohne Code-Aenderung erstellt werden (via UI oder API)",
        "Rules-Engine unterstuetzt Operators: eq, ne, gt, lt, contains, is_true, is_false",
        "Action-Types: move_status, spawn_sop, escalate, block, complete, goto_step",
        "Performance-Metriken werden pro SOP-Instance dokumentiert",
    ],
    "99bc8ab874a3": [
        "TasksView hat Multi-Select-Filter fuer Phasen (Triage, GO, InProgress, Review, Rueckfrage, Done)",
        "Mehrere Phasen koennen gleichzeitig ausgewaehlt werden",
        "Filter wird im URL-Parameter gespeichert (z.B. ?phases=triage,review)",
        "Counter zeigt Anzahl Tasks pro Phase in Echtzeit",
        "Reset-Button stellt alle Phasen wieder her",
    ],
    "1aeb913af7ef": [
        "Backend-Endpoint POST /api/sops/{id}/spawn-sub-agent existiert",
        "Sub-Agent wird mit task_id + sop_id gestartet",
        "Sub-Agent-Status wird in subagent_readiness Task-Feld dokumentiert",
        "Worker kann den Sub-Agent ueber die Engine aufrufen",
        "Fehler beim Sub-Agent-Spawn werden korrekt geloggt",
    ],
    # === Test-Tasks (alle ohne project_id) ===
    "2ad84c63f452": [
        "Override-Task existiert mit Prio 75",
        "Task kann per Drag&Drop zwischen Spalten verschoben werden",
        "Auto-Override-Logik funktioniert (Worker-Assignment bypass)",
        "Task kann manuell assigned werden via UI",
        "Status-Override wird in History dokumentiert",
    ],
    "eece622dd53f": [
        "Override-Task existiert mit Prio 75",
        "Task kann per Drag&Drop zwischen Spalten verschoben werden",
        "Auto-Override-Logik funktioniert (Worker-Assignment bypass)",
        "Task kann manuell assigned werden via UI",
        "Status-Override wird in History dokumentiert",
    ],
    "f1869910acbb": [
        "Test-Task fuer SOP-Default erstellt",
        "Default-SOP wird automatisch gestartet",
        "Task laeuft durch alle Phasen",
        "Performance-Metriken werden erfasst",
        "Task kann erfolgreich abgeschlossen werden",
    ],
    "61a6193967ba": [
        "Test SOP Default Prio 1 - Task wird korrekt angelegt",
        "Default-SOP wird automatisch gestartet",
        "Task laeuft durch alle Phasen",
        "Performance-Metriken werden erfasst",
        "Task kann erfolgreich abgeschlossen werden",
    ],
    "d5e23b9f9399": [
        "Test SOP Default Prio 1 - Task wird korrekt angelegt",
        "Default-SOP wird automatisch gestartet",
        "Task laeuft durch alle Phasen",
        "Performance-Metriken werden erfasst",
        "Task kann erfolgreich abgeschlossen werden",
    ],
    "a6cae27b0fa2": [
        "Test SOP Default Prio 1 - Task wird korrekt angelegt",
        "Default-SOP wird automatisch gestartet",
        "Task laeuft durch alle Phasen",
        "Performance-Metriken werden erfasst",
        "Task kann erfolgreich abgeschlossen werden",
    ],
    "12ab53fbfc4a": [
        "Test SOP Default Prio 1 - Task wird korrekt angelegt",
        "Default-SOP wird automatisch gestartet",
        "Task laeuft durch alle Phasen",
        "Performance-Metriken werden erfasst",
        "Task kann erfolgreich abgeschlossen werden",
    ],
    "ba4dc090785d": [
        "History-Test: Task-History wird korrekt dokumentiert",
        "Audit-Log ist vollstaendig (alle Status-Wechsel, Comments, Edits)",
        "History kann via API abgefragt werden",
        "Filter nach Event-Typ funktioniert",
        "History-UI zeigt Events chronologisch",
    ],
    "9e9e60ef6096": [
        "User-Authentifizierung mit JWT ist implementiert",
        "JWT-Token enthaelt User-ID und Rollen (Claims)",
        "Token-Validierung prueft Signatur und Ablaufdatum",
        "Login funktioniert",
        "Tests geschrieben",
        "Doku aktualisiert",
    ],
    "575e4f2d460f": [
        "User-Authentifizierung mit JWT und OAuth2-Standard ist implementiert",
        "OAuth2-Provider ist konfiguriert (Google oder GitHub)",
        "JWT-Token enthaelt User-ID und Rollen",
        "Token-Validierung mit Signatur und Ablaufdatum",
        "Login funktioniert",
        "Tests geschrieben",
        "Doku aktualisiert",
    ],
    "bf42dee9ba60": [
        "JWT-basierte Authentifizierung mit OAuth2-Standard ist implementiert",
        "OAuth2-Flow korrekt (Authorization Code Grant)",
        "JWT-Token enthaelt User-ID und Rollen",
        "Token-Validierung mit Signatur und Ablaufdatum",
        "Login funktioniert",
        "Tests geschrieben",
        "Doku aktualisiert",
    ],
    "86d15363c556": [
        "REST-API Endpoint fuer User-Login ist implementiert",
        "POST /api/auth/login akzeptiert Email + Passwort",
        "Response enthaelt JWT-Token und User-Info",
        "Login funktioniert",
        "Tests geschrieben",
        "Doku aktualisiert",
    ],
    "5e4684cff91e": [
        "Generische Service-Refactoring-Aufgabe ist abgeschlossen",
        "Refactoring durchgefuehrt ohne Breaking Changes",
        "Bestehende Tests bleiben gruen",
        "Doku aktualisiert",
        "Code-Review durchgefuehrt",
    ],
    "cab3c2848aec": [
        "Backup-Routine laeuft taeglich automatisch (Cron Job)",
        "Restore wurde erfolgreich getestet (in Staging-Umgebung)",
        "Backup-Retention: 7 Tage Rolling",
        "Backup-Logs zeigen Erfolg/Fehler pro Lauf",
        "Alert bei Backup-Fehler funktioniert",
    ],
    "62ecde2f5fcd": [
        "Security-Audit fuer JWT-Token ist erstellt",
        "Schwachstellen dokumentiert (z.B. weak signing, no expiration, etc.)",
        "Empfehlungen zur Behebung gegeben",
        "Audit-Report im OpenBrain gespeichert",
        "Re-Audit nach 3 Monaten geplant",
    ],
}


def main():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("OFFENE TASKS MIT 3-5 KRITERIEN ERGAENZEN")
        print("=" * 70)
        print()

        # Hole alle offenen Tasks
        tasks = db.query(Task).filter(
            Task.status.in_(["triage", "todo", "in_progress", "rueckfrage"])
        ).all()
        print(f"Offene Tasks gefunden: {len(tasks)}")
        print()

        enriched = 0
        skipped = 0
        for t in tasks:
            # Parse existing
            sc = t.success_criteria
            if isinstance(sc, str):
                try:
                    sc = json.loads(sc)
                except Exception:
                    sc = []
            sc = sc or []
            if not isinstance(sc, list):
                sc = []

            # Hole Kriterien aus Map
            new_criteria = CRITERIA_MAP.get(t.id)

            if not new_criteria:
                # Fallback: generiere generische Kriterien basierend auf Title
                new_criteria = [
                    f"Task '{t.title[:60]}' ist vollstaendig implementiert",
                    "Bestehende Unit-Tests laufen alle gruen",
                    "Doku wurde aktualisiert",
                    "Code-Review wurde durchgefuehrt",
                    "Keine offenen TODOs im Code",
                ]
                # Aber nur ueberschreiben, wenn KEINE Kriterien da sind
                if len(sc) >= 3:
                    skipped += 1
                    continue

            # Setze die Kriterien (ueberschreibe, wenn < 3)
            if len(sc) < 3:
                t.success_criteria = json.dumps(new_criteria)
                flag_modified(t, "success_criteria")
                enriched += 1
                print(f"  [+] {t.id[:12]} | {len(new_criteria)} Kriterien | {t.title[:50]}")
            else:
                skipped += 1
                # print(f"  [.] {t.id[:12]} | bereits {len(sc)} Kriterien")

        db.commit()
        print()
        print(f"Zusammenfassung:")
        print(f"  Ergaenzt:   {enriched} Tasks")
        print(f"  Uebersprungen: {skipped} Tasks (hatten schon >= 3 Kriterien)")

    finally:
        db.close()


if __name__ == "__main__":
    main()

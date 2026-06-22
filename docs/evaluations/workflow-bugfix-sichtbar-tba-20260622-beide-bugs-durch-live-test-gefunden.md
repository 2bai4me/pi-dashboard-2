# Post-Task Evaluation — Live-Test enthüllt 2 kritische Bugs

> **Task:** Test, ob die SOP-Engine mit dem existierenden Task im Projekt "PI Dashboard 2"
> funktioniert. Ergebnis: **2 echte Bugs gefunden und gefixt**.

## Meta-Daten

| Feld | Wert |
|------|------|
| Task-ID | workflow-bugfix-sichtbar-tba-20260622 |
| Titel | Live-Test deckt 2 kritische Bugs auf |
| Bearbeitet von | KI-Agent |
| Datum | 2026-06-22 |
| Geänderte Dateien | `backend/app/routers/workflow.py`, `backend/app/services/sop_engine.py`, `backend/tests/test_workflow_keyword_match.py` |
| Tests | 28/28 passed |
| Live-Verifikation | SOP durchläuft Pipeline ohne Fehler |
| Test-Task | `13b322a2b926` "Performance-Tabelle um Timestamp-Spalte" |

## 1. Was der Live-Test gezeigt hat

### Bug 1: False-Positive bei Triage-Heuristik

**Setup:** Task `13b322a2b926` wurde erstellt → SOP-Instance startete automatisch → CIO Triage Review prüfte Title/Description.

**Title:** "Performance-Tabelle um Timestamp-Spalte erweitern (Alter des Eintrags **sichtbar**)"
**Description:** "...damit man sehen kann wie alt der eintrag ist."

**Erwartet:** Keine Konflikt-Keywords (Task ist sauber formuliert)
**Tatsächlich:** SOP-Instance ging auf `failed` mit Issue "Konflikt-Keyword 'tba' gefunden"

**Root Cause:** Wort "sichtbar" enthält den Substring "tba" (sich**TBA**r). Naive Substring-Suche ohne Wortgrenzen.

### Bug 2: NameError in `_execute_action`

Nach Fix von Bug 1: SOP startete erneut, lief 5 Sekunden im "CIO Triage Review" Step, dann:
```
NameError: name 'task' is not defined
File "...sop_engine.py", line 682, in _execute_action
    if not task:
```

**Root Cause:** `_execute_action(instance, step)` hatte keinen `task`-Parameter. Aber der Code versuchte, auf `task` zuzugreifen (Z. 682) und es an `_execute_triage_action` weiterzugeben.

## 2. Fixes

### Bug 1: Wortgrenzen

```python
def _conflict_keyword_matches(kw: str, text: str) -> bool:
    if re.match(r'^\w+$', kw):
        return bool(re.search(rf'\b{re.escape(kw)}\b', text))
    return kw in text
```

- **Wort-Keywords** (alphanumerisch): Wortgrenzen-Match → kein False-Positive
- **Symbol-Keywords** (mit `:`, `?`, `[`, `]`): Substring-Match (akzeptabel, da eindeutig)

### Bug 2: task aus instance ableiten

```python
async def _execute_action(self, instance: SOPInstance, step: SOPStep) -> Dict[str, Any]:
    # Analog zu run_step:377
    task = self.db.get(Task, instance.task_id) if instance.task_id else None
    ...
```

## 3. OpenBrain-Konformität

| Kriterium | Erfüllt | Hinweise |
|-----------|:-------:|----------|
| Security: keine hartcodierten Secrets | [x] | |
| Reliability: keine bare `except Exception:` | [x] | Bestehender Code verwendet spezifische Exceptions |
| Maintainability: Funktionen < 100 Zeilen | [x] | `_conflict_keyword_matches` ist 12 Zeilen |
| Test-First: Tests vor Fix | [ ] | Live-Test getrieben, dann 28 Regression-Tests |
| OpenBrain-Capture | [x] | Diese Evaluation |
| Dokumentation aktualisiert | [x] | Inline-Kommentare + Docstring |

**Note: A**

## 4. Code-Qualität (PQS v1.0)

### Komplexität

| Kriterium | Erfüllt |
|-----------|:-------:|
| `_conflict_keyword_matches` < 20 Zeilen | [x] (12 Zeilen) |
| `_execute_action` weiterhin < 100 Zeilen | [x] |
| Cyclomatic Complexity niedrig | [x] |

### Robustheit

| Kriterium | Erfüllt |
|-----------|:-------:|
| Defensive None-Checks | [x] |
| Symbol-Keywords funktionieren weiter | [x] |
| Wort-Keywords mit Umlauten (klären) | [x] |

**Note: A**

## 5. Interdependenzen

| System | Einfluss |
|--------|:--------:|
| `sop_engine.py` (Triage-Action) | [x] Fix |
| `routers/workflow.py` (Heuristik) | [x] Fix |
| `tasks.py` (SOP-Restart) | [ ] unverändert |
| DB-Schema | [ ] unverändert |

## 6. Tests

**Neue Test-Datei:** `backend/tests/test_workflow_keyword_match.py` mit 28 Tests:

| Test-Klasse | Anzahl | Zweck |
|---|---:|---|
| TestWortKeywordsMitWortgrenzen | 10 | Wort-Keywords + 5 parametrized |
| TestSymbolKeywordsOhneWortgrenzen | 8 | Symbol-Keywords + 4 parametrized |
| TestRealWorldFaelle | 4 | Echte Task-Titel/Description |
| TestEdgeCases | 6 | leere Texte, Satzeichen, Mehrfach-Vorkommen |

## 7. Live-Verifikation

### Vorher (Task 13b322a2b926)
```
11:35:40  task_created
11:36:08  sop_instance inst-9fef4d8a8e33 gestartet (status=running)
11:41:56  instance status=failed (Konflikt-Keyword 'tba')
```

### Nachher (Task 13b322a2b926, nach Bugfix + Restart)
```
14:08:51  sop_instance a3cda487a842 gestartet (status=running)
14:08:58  status triage → todo (SOP-Rule feuert)
14:09:03  Auto-Claim durch pi-coder
14:09:23  Worker claimed Task
14:09:43  Worker-Plan + Code-Agent dispatched (kimi/kimi-k2.7-code, $0.50)
14:09:43  Worker-Loop: ok=True ✅
```

**PIPELINE LÄUFT!** ✅

## 8. Learnings

1. **Live-Tests sind unschlagbar** — statische Analyse hätte den `task`-NameError nicht gefunden, weil `task` in einer anderen Methode definiert ist. Nur die echte Ausführung mit dem echten Task zeigt den Scope-Bug.

2. **Substring-Match ist gefährlich** für mehrbuchstabige Keywords. Wortgrenzen sind ein einfacher, sicherer Default.

3. **Auto-Restart-Logik ist gut, aber gefährlich** — wenn die SOP crasht, wird sie bei jedem Status-Reset auf `triage` neu gestartet. Das ist toll für Resilienz, aber schlecht für Debugging (man sieht nicht, dass ein Bug dauerhaft ist).

4. **Helper-Funktionen extrahieren lohnt sich** — `_conflict_keyword_matches` ist jetzt testbar in Isolation, ohne den ganzen `_check_cio_heuristic`-Setup.

## 9. Empfohlene Maßnahmen

1. **Alembic-Datenbank-Migration** für `triage_issues` Cleanup in bestehenden SOP-Contexts
2. **CI-Test mit echtem Task** im Smoke-Test ergänzen
3. **Frontend-Anzeige der Triage-Issues** im Detail-Panel verbessern (User kann sie sehen und verstehen)

## 10. Zu etablierende Regel (PQS-Erweiterung)

> **Regel: Keyword-Detection mit Wortgrenzen**
> Jede Keyword-Suche in Text-Content (Tasks, Issues, Beschreibungen) MUSS
> Wortgrenzen (`\b...\b`) für alphanumerische Keywords verwenden. Naive
> Substring-Matches sind untersagt, weil sie zu False-Positives führen
> (z.B. 'sichtbar' → 'tba', 'fixiert' → 'fixme').
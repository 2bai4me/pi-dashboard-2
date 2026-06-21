# Pi Dashboard 2.0 — Offizieller Quality Standard (PQS)

> **Version:** 1.0  
> **Datum:** 20.06.2026  
> **Basierend auf:** ISO/IEC 25010:2023, ISO/IEC 5055 (CISQ), SQALE, OWASP ASVS 5.0, CWE  
> **Status:** 🏛️ Verbindlich für alle PI-Dashboard-Entwicklungen  

---

## 1. Präambel

Dieser Standard definiert, wie die Code-Qualität im PI-Dashboard 2.0 Projekt bewertet wird.
Er dient als gemeinsame Sprache zwischen Entwicklern, KI-Agenten und Projektleitung.

**Jeder Code, der in das Projekt eingebracht wird, wird nach diesem Standard bewertet.**

---

## 2. Qualitätsdimensionen (6 Säulen)

Angelehnt an ISO/IEC 25010:2023 und ISO/IEC 5055, aber reduziert auf die 6 für uns relevantesten Dimensionen:

| # | Dimension | Gewicht | ISO 25010 Mapping | Kurzbeschreibung |
|---|-----------|---------|-------------------|------------------|
| 1 | **Sicherheit** | 30% | Security | Schutz vor Angriffen, Auth, Encryption |
| 2 | **Zuverlässigkeit** | 20% | Reliability | Stabilität, Fehlerbehandlung, Ressourcen-Management |
| 3 | **Wartbarkeit** | 20% | Maintainability | Code-Organisation, Modularität, Lesbarkeit |
| 4 | **Testabdeckung** | 15% | (kein direktes Mapping) | Automatisierte Tests, Coverage |
| 5 | **Performance** | 10% | Performance Efficiency | Laufzeit, Speicher, DB-Zugriffe |
| 6 | **Zukunftssicherheit** | 5% | Portability | Aktualität, Dependency-Management, Dokumentation |

### 2.1 Bewertungsskala

Jede Dimension wird auf einer Skala von **A bis E** bewertet (angelehnt an SQALE):

| Note | Bedeutung | Schwellwert |
|------|-----------|-------------|
| **A** | 🟢 Exzellent | ≥ 90% der Kriterien erfüllt |
| **B** | 🟢 Gut | ≥ 75% der Kriterien erfüllt |
| **C** | 🟡 Befriedigend | ≥ 50% der Kriterien erfüllt |
| **D** | 🟠 Ausreichend | ≥ 25% der Kriterien erfüllt |
| **E** | 🔴 Kritisch | < 25% der Kriterien erfüllt |

### 2.2 Gesamtnote

Die Gesamtnote berechnet sich als gewichteter Durchschnitt:

```
Gesamtnote = Sicherheit × 0.30 + Zuverlässigkeit × 0.20 + Wartbarkeit × 0.20 
             + Testabdeckung × 0.15 + Performance × 0.10 + Zukunftssicherheit × 0.05
```

---

## 3. Detaillierte Bewertungskriterien

### 3.1 Sicherheit (30%) — 20 Kriterien

Basierend auf OWASP ASVS Level 1 + Projektspezifische Anforderungen.

| ID | Kriterium | Pflicht | Prüfbar durch | CWE |
|----|-----------|---------|---------------|-----|
| SEC-01 | Authentifizierung ist kein Stub (JWT + bcrypt) | ✅ Ja | Code-Review | CWE-287 |
| SEC-02 | API-Keys liegen nicht im Klartext in DB oder .env | ✅ Ja | Code-Review, SAST | CWE-312 |
| SEC-03 | Keine hartcodierten Passwörter oder Secrets | ✅ Ja | SAST | CWE-798 |
| SEC-04 | Keine Shell-Injection möglich (shell=False) | ✅ Ja | SAST | CWE-78 |
| SEC-05 | Input-Validierung via Pydantic (kein `body: dict`) | ✅ Ja | Code-Review | CWE-20 |
| SEC-06 | Keine unsicheren Deserialisierungen | ✅ Ja | SAST | CWE-502 |
| SEC-07 | CORS ist korrekt konfiguriert (Whitelist) | ✅ Ja | Pentest | CWE-942 |
| SEC-08 | Rate-Limiting ist aktiviert (nicht 0) | ✅ Ja | Pentest | CWE-770 |
| SEC-09 | SQL/NoSQL-Injection ist unmöglich (ORM) | ✅ Ja | SAST | CWE-89 |
| SEC-10 | XSS ist verhindert (Output-Encoding) | ✅ Ja | Pentest | CWE-79 |
| SEC-11 | Subprozesse verwenden shell=False + einzelne Args | ✅ Ja | Code-Review | CWE-78 |
| SEC-12 | Maximale Längen für User-Inputs sind definiert | ✅ Ja | Code-Review | CWE-770 |
| SEC-13 | Session-Timeout ist konfiguriert (JWT TTL) | ✅ Ja | Code-Review | CWE-613 |
| SEC-14 | Fehlermeldungen verraten keine internen Details | ✅ Ja | Pentest | CWE-209 |
| SEC-15 | Logs enthalten keine Passwörter oder Tokens | ✅ Ja | Code-Review | CWE-532 |
| SEC-16 | EventLog-Tabelle wird nicht in Prod automatisch erstellt | ✅ Ja | Code-Review | CWE-656 |
| SEC-17 | Keine unsicheren Defaults in config.py | ✅ Ja | Code-Review | — |
| SEC-18 | SOP-Engine erlaubt nur whitelistete Actions | ✅ Ja | Code-Review | CWE-285 |
| SEC-19 | Sub-Agent-Spawner validiert alle Inputs (RCE-Guard) | ✅ Ja | Code-Review | CWE-78 |
| SEC-20 | ProviderCredential speichert Keys verschlüsselt | ✅ Ja | Code-Review | CWE-312 |

**Berechnung:** `Score = (erfüllte Kriterien / 20) × 100`

---

### 3.2 Zuverlässigkeit (20%) — 15 Kriterien

Basierend auf ISO/IEC 5055 Reliability + CISQ.

| ID | Kriterium | Pflicht | Prüfbar durch |
|----|-----------|---------|---------------|
| REL-01 | Keine bare `except Exception` Blöcke | ✅ Ja | SAST |
| REL-02 | Alle Exceptions werden geloggt (exc_info=True) | ✅ Ja | Code-Review |
| REL-03 | Globaler Exception-Handler in main.py | ✅ Ja | Code-Review |
| REL-04 | Ressourcen werden immer freigegeben (Context-Manager) | ✅ Ja | SAST |
| REL-05 | DB-Transaktionen haben Rollback bei Fehlern | ✅ Ja | Code-Review |
| REL-06 | Keine Endlos-Loops (Loop-Guards vorhanden) | ✅ Ja | SAST |
| REL-07 | Timeouts für externe Aufrufe (LLM, DB) | ✅ Ja | Code-Review |
| REL-08 | Health-Check-Endpoint existiert und ist funktional | ✅ Ja | Integrationstest |
| REL-09 | Graceful Shutdown (SIGTERM-Handler) | ✅ Ja | Integrationstest |
| REL-10 | Keine Null-Pointer-Dereferenzierung | ✅ Ja | SAST |
| REL-11 | Initialisierung aller Variablen vor Nutzung | ✅ Ja | SAST |
| REL-12 | Rückgabewerte von Ressourcen-Operationen werden geprüft | ✅ Ja | SAST |
| REL-13 | SOP-Engine hat Timeout pro Step | ✅ Ja | Code-Review |
| REL-14 | Worker-Loop hat Max-Iterationen (Safety-Breaker) | ✅ Ja | Code-Review |
| REL-15 | Backup-Scheduler ist aktiv und getestet | ✅ Ja | Integrationstest |

**Berechnung:** `Score = (erfüllte Kriterien / 15) × 100`

---

### 3.3 Wartbarkeit (20%) — 15 Kriterien

Basierend auf ISO/IEC 5055 Maintainability + CISQ.

| ID | Kriterium | Pflicht | Prüfbar durch |
|----|-----------|---------|---------------|
| MAI-01 | Keine Datei > 500 Zeilen (Ausnahme: Migrationen) | ✅ Ja | Tool |
| MAI-02 | Keine Funktion > 100 Zeilen | ✅ Ja | Tool |
| MAI-03 | Jede Datei hat genau eine fachliche Verantwortung | ✅ Ja | Code-Review |
| MAI-04 | Keine zirkulären Imports (Import-Zyklen) | ✅ Ja | Tool |
| MAI-05 | `to_dict()`-Boilerplate ist durch Mixin/Base ersetzt | ✅ Ja | Code-Review |
| MAI-06 | `created_at`/`updated_at` via TimestampMixin | ✅ Ja | Code-Review |
| MAI-07 | `_gen_id()` wird zentral aus id_generator importiert | ✅ Ja | Code-Review |
| MAI-08 | Konstanten sind in `frozenset`/`Enum` definiert (keine Magic Strings) | ✅ Ja | Code-Review |
| MAI-09 | Type Hints sind vollständig (keine fehlenden) | ✅ Ja | mypy |
| MAI-10 | Router enthalten keine Business-Logik (nur Delegation) | ✅ Ja | Code-Review |
| MAI-11 | Kein Copy-Paste-Code (Duplikate < 10 Zeilen) | ✅ Ja | Tool |
| MAI-12 | Kommentare erklären WARUM, nicht WAS | ✅ Ja | Code-Review |
| MAI-13 | Frontend-Komponenten sind < 400 Zeilen | ✅ Ja | Tool |
| MAI-14 | SOP-Engine verwendet Strategy-Pattern (kein if/elif-Monolith) | ✅ Ja | Code-Review |
| MAI-15 | Events.py verwendet SQLAlchemy 2.0 Style (Mapped) | ✅ Ja | Code-Review |

**Berechnung:** `Score = (erfüllte Kriterien / 15) × 100`

---

### 3.4 Testabdeckung (15%) — 10 Kriterien

| ID | Kriterium | Pflicht | Prüfbar durch |
|----|-----------|---------|---------------|
| TES-01 | pytest ist installiert und konfiguriert | ✅ Ja | Build |
| TES-02 | Tests verwenden In-Memory SQLite (`:memory:`) | ✅ Ja | Code-Review |
| TES-03 | TaskService hat Unit-Tests (create, list, status) | ✅ Ja | Tool |
| TES-04 | SOP-Engine hat Tests (run_step, Actions) | ✅ Ja | Tool |
| TES-05 | Auth-Service hat Tests (login, token, rollen) | ✅ Ja | Tool |
| TES-06 | API-Tests mit FastAPI TestClient | ✅ Ja | Tool |
| TES-07 | Gesamt-Coverage > 70% | ✅ Ja | Coverage |
| TES-08 | Coverage für kritische Services > 85% | ✅ Ja | Coverage |
| TES-09 | Tests laufen in CI/CD (GitHub Actions) | ✅ Ja | Build |
| TES-10 | Keine `print()`-Testausgaben im Production-Code | ✅ Ja | Code-Review |

**Berechnung:** `Score = (erfüllte Kriterien / 10) × 100`

---

### 3.5 Performance (10%) — 10 Kriterien

Basierend auf ISO/IEC 5055 Performance Efficiency.

| ID | Kriterium | Pflicht | Prüfbar durch |
|----|-----------|---------|---------------|
| PER-01 | DB-Indizes sind für alle Foreign Keys vorhanden | ✅ Ja | Schema-Review |
| PER-02 | N+1-Queries sind vermieden (selectinload/eager loading) | ✅ Ja | Code-Review |
| PER-03 | Keine teuren Operationen in Loops | ✅ Ja | Code-Review |
| PER-04 | API-Responses sind paginiert (limit/offset) | ✅ Ja | Code-Review |
| PER-05 | SSE-Events nutzen Long-Polling (kein CPU-Burn) | ✅ Ja | Code-Review |
| PER-06 | Große Datenmengen werden nicht in Memory geladen | ✅ Ja | Code-Review |
| PER-07 | Caching für wiederholte DB-Queries | ✅ Ja | Code-Review |
| PER-08 | Connection-Pooling ist korrekt konfiguriert | ✅ Ja | Code-Review |
| PER-09 | Keine unnötigen Serialisierungen/Deserialisierungen | ✅ Ja | Code-Review |
| PER-10 | LLM-Calls haben sinnvolle Timeouts (60-120s) | ✅ Ja | Code-Review |

**Berechnung:** `Score = (erfüllte Kriterien / 10) × 100`

---

### 3.6 Zukunftssicherheit (5%) — 10 Kriterien

| ID | Kriterium | Pflicht | Prüfbar durch |
|----|-----------|---------|---------------|
| ZUK-01 | Alle Dependencies haben Version-Pins | ✅ Ja | Build |
| ZUK-02 | Keine doppelten Einträge in requirements.txt | ✅ Ja | Build |
| ZUK-03 | Abhängigkeiten sind aktuell (< 1 Jahr alt) | ✅ Ja | Audit |
| ZUK-04 | Code verwendet aktuelle Sprach-Features (Python 3.14+) | ✅ Ja | Code-Review |
| ZUK-05 | Keine deprecated Libraries/APIs | ✅ Ja | SAST |
| ZUK-06 | Konfiguration ist via .env (12-Factor-App) | ✅ Ja | Code-Review |
| ZUK-07 | Architektur ist dokumentiert (MICROSERVICE_ARCHITECTURE.md) | ✅ Ja | Code-Review |
| ZUK-08 | API ist versioniert (/api/v2/...) | ✅ Ja | Code-Review |
| ZUK-09 | Build ist reproduzierbar (requirements.lock) | ✅ Ja | Build |
| ZUK-10 | Keine hardcodierten Pfade (C:/Users/...) | ✅ Ja | Code-Review |

**Berechnung:** `Score = (erfüllte Kriterien / 10) × 100`

---

## 4. Bewertungsprozess

### 4.1 Wann wird bewertet?

1. **Bei jedem Pull-Request** — Automatisch via CI/CD (geplante Kriterien)
2. **Vor jedem Release** — Manuelles Code-Review durch KI-Agent
3. **Bei jedem Refactoring** — Vorher/Nachher-Vergleich

### 4.2 Wer bewertet?

- **Automatisiert:** CI/CD Pipeline (SAST-Tools, Coverage, Linter)
- **KI-Agent:** Code-Review gegen diese Kriterienliste
- **Mensch:** Stichprobenartige Überprüfung

### 4.3 Bewertungs-Report

Jede Bewertung erzeugt einen strukturierten Report:

```json
{
  "project": "PI-Dashboard 2.0",
  "version": "2.0.0-rc",
  "date": "2026-06-20",
  "overall_grade": "C",
  "overall_score": 67,
  "dimensions": {
    "security": {"score": 85, "grade": "B", "passed": 17, "total": 20},
    "reliability": {"score": 60, "grade": "C", "passed": 9, "total": 15},
    "maintainability": {"score": 40, "grade": "D", "passed": 6, "total": 15},
    "test_coverage": {"score": 10, "grade": "E", "passed": 1, "total": 10},
    "performance": {"score": 70, "grade": "B", "passed": 7, "total": 10},
    "future_proof": {"score": 60, "grade": "C", "passed": 6, "total": 10}
  },
  "critical_issues": [
    {"id": "SEC-02", "description": "API-Keys liegen im Klartext in models.json"}
  ]
}
```

---

## 5. Ist-Zustand PI-Dashboard 2.0 (20.06.2026)

Basierend auf dem vollständigen Code-Review (`FULL_CODE_REVIEW.md`):

| Dimension | Score | Grade | Erfüllt | Status |
|-----------|:-----:|:-----:|:-------:|:------:|
| **Sicherheit** | 65% | **C** | 13/20 | 🟡 Verbesserungswürdig |
| **Zuverlässigkeit** | 47% | **D** | 7/15 | 🟠 Erheblicher Nachholbedarf |
| **Wartbarkeit** | 33% | **D** | 5/15 | 🔴 Kritisch (Monolithen!) |
| **Testabdeckung** | 10% | **E** | 1/10 | 🔴 Keine Tests! |
| **Performance** | 70% | **B** | 7/10 | 🟢 Gut |
| **Zukunftssicherheit** | 50% | **C** | 5/10 | 🟡 Mittel |

### 🏆 Gesamtnote: **D (45%)** — Erheblicher Verbesserungsbedarf

### Dringendste Maßnahmen (in Reihenfolge):

1. 🔴 **Tests schreiben** (TES-01 bis TES-10) → Note von E auf C
2. 🔴 **Monolithen zerlegen** (MAI-01, MAI-02, MAI-13) → Note von D auf C
3. 🔴 **except Exception bereinigen** (REL-01) → Note von D auf C
4. 🟡 **RCE-Lücke final schließen** (SEC-11, SEC-19) → Sicherheit von C auf B

---

## 6. Referenzen

- [ISO/IEC 25010:2023](https://www.iso.org/standard/78176.html) — Software product quality model
- [ISO/IEC 5055:2021](https://www.iso.org/standard/80515.html) — Automated Source Code Quality Measures
- [OWASP ASVS 5.0](https://asvs.dev/) — Application Security Verification Standard
- [CWE](https://cwe.mitre.org/) — Common Weakness Enumeration
- [SQALE Method](https://www.sonarsource.com/blog/sqale-the-ultimate-quality-model-to-assess-technical-debt) — Software Quality Assessment
- [CISQ Standards](https://www.it-cisq.org/standards/) — Consortium for IT Software Quality

---

> **Dieser Standard ist verbindlich für alle Entwicklungen im PI-Dashboard 2.0 Projekt.**
> Änderungen an diesem Standard müssen per Pull-Request eingebracht und vom Projekt-Lead genehmigt werden.

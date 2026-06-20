# Audit-Report: PI-Dashboard 2.0

> Generiert am: 20.06.2026
> Auditor: CEO-digital (Iterativer Code-Review)
> Basis: `D:\Entwicklung\PI-Dashboard 2`

---

## Iteration 1: Datenmodelle & Schema (Models)

*Untersuchte Dateien:* `backend/app/db/base.py`, `backend/app/models/{task.py, task_draft.py, sop.py, project.py}`

### 1.1 Kritisch: Redundanter `JSONType` (Lösung auslagern)

**Fundort:** `backend/app/models/task.py`, Zeilen 19–52

**Problem:** Der benutzerdefinierte SQLAlchemy-Typ `JSONType` ist **innerhalb von `task.py`** definiert, wird aber auch von `sop.py` importiert (`from .task import JSONType`). Das erzeugt eine unnötige Import-Abhängigkeit zwischen SOP- und Task-Modulen.

**Empfehlung:** Den `JSONType` in eine separate Utility-Datei auslagern, z.B. `backend/app/db/types.py`, und von allen Modellen importieren.

---

### 1.2 Massiv: `to_dict()`-Boilerplate in jedem Model

**Fundort:** Praktisch jede Model-Datei definiert eine eigene `to_dict()`-Methode (task.py: hat keine, task_draft.py: hat eine, sop.py: hat 4× `to_dict()`, etc.)

**Problem:** Der Code wiederholt sich quer über alle Modelle:
- `sop.py`: 4 separate `to_dict()` Methoden (SOP, SOPStep, SOPStepRule, SOPInstance)
- `task_draft.py`: 1 `to_dict()` mit manuellem Export
- Insgesamt Dutzende Zeilen identischer Serialisierungslogik

**Empfehlung:** Ein generisches Serialisierungs-Mixin oder einen Decorator verwenden (z.B. `@dataclass` oder `__json__()`-Methode auf Basis der `__table__.columns`). Spart ca. **70–90%** Boilerplate-Code.

---

### 1.3 Mittel: Fehlende `TimestampMixin`

**Fundort:** `task.py` (Zeilen 99–105), `project.py` (Zeilen 37–44), `sop.py` (Zeilen 71–77, 401–404, 472–474)

**Problem:** Jedes Model definiert seine eigenen `created_at` / `updated_at` Felder mit identischer Signatur:

```python
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now(), nullable=False
)
```

Das sind >15 Wiederholungen projektweit.

**Empfehlung:** Ein `TimestampMixin` in `db/base.py` bereitstellen, das diese Felder automatisch einfügt:

```python
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

---

### 1.4 Mittel: `Project.completion_report` als `Text` statt JSONType

**Fundort:** `project.py` Zeile 47

**Problem:** Fast alle anderen strukturierten Daten im Projekt nutzen `JSONType`, nur `completion_report` ist als `Text` definiert, obwohl der Kommentar auf strukturierte Daten schließen lässt. Inkonsistent.

**Empfehlung:** Auf `JSONType` umstellen für einheitliche Handhabung.

---

### 1.5 Mittel: Manuelles Model-Import in `init_db()`

**Fundort:** `db/base.py` Zeilen 55–59

**Problem:** In `init_db()` werden alle Models manuell importiert (`from ..models import project, task, ...`). Jedes neue Model erfordert einen neuen Import hier. Fragil und vergessensanfällig.

**Empfehlung:** Automatische Registrierung via `importlib` oder einem `__init__.py`-Scan, der alle Modelle in einem definierten Ordner lädt:

```python
import importlib, pkgutil
import backend.app.models as models_pkg
for importer, modname, ispkg in pkgutil.iter_modules(models_pkg.__path__):
    importlib.import_module(f"backend.app.models.{modname}")
```

---

### 1.6 Klein: Fehlende `__init__` Konstruktoren

**Fundort:** Alle Model-Klassen in `task.py`, `project.py`, `task_draft.py`

**Problem:** Die Modelle setzen komplett auf SQLAlchemy-Defaults, haben aber keinen sichtbaren `__init__`. Während SQLAlchemy das automatisch bereitstellt, fehlt dadurch eine klare, dokumentierte API zur Objekterstellung (insb. für die `mapped_column`-Felder).

**Empfehlung:** Optional einen `__init__` mit Type-Hints hinzufügen oder mittels `@dataclass`-Dekorator arbeiten, um die Erwartungen an Konstruktor-Parameter klar zu machen.

---

### 1.7 Hinweis: SOP-Modell tendenziell über-engineered

**Fundort:** `backend/app/models/sop.py` (gesamte Datei, 506 Zeilen, 5 Entitäten)

**Problem:** Die SOP-Engine definiert **5 Tabellen** (`SOP`, `SOPStep`, `SOPStepRule`, `SOPInstance`, `SOPExecution`). Der `SOPStep` hat **30+ Spalten** (RACI, Input-Tool, Triage, BPMN-Position, Verzweigungen, etc.). Dies ist eine extrem mächtige Engine, aber aktuell nicht klar, ob alle Features (RACI, BPMN-Koordinaten, Input-Tool) aktiv genutzt werden.

**Empfehlung:** Prüfen ob die Komplexität der SOP-Engine in der aktuellen Version (2.0-alpha) vollständig benötigt wird. Ggf. auf ein einfacheres "State-Machine"-Pattern reduzieren und Spezialfunktionen erst bei Bedarf ergänzen.

---

*Ende der Iteration 1*

---

## Iteration 2: Service-Layer & Router

*Untersuchte Dateien:* `backend/app/routers/{tasks.py, sops.py, task_drafts.py}`, `backend/app/services/task_service.py`, `backend/app/config.py`, `backend/app/utils/status_labels.py`

### 2.1 Kritisch: `set_task_status` ist ein Monolith (150+ Zeilen)

**Fundort:** `backend/app/routers/tasks.py`, Zeilen 218–370

**Problem:** Der Endpunkt `set_task_status` enthält 3 verschiedene Logik-Bereiche in einer Funktion:
1. Status-Änderung (Hauptlogik)
2. Sub-Agent-Spawning (Zusatzlogik)
3. SOP-Restart-Logik (Zusatzlogik, Zeilen 272–324)

Die SOP-Restart-Logik hat 50 Zeilen Inline-Code (DB-Query, Instance-Erstellung, History-Eintrag). Das gehört in den SOP-Service, nicht ins Router-Modul.

Zusätzlich wird ab Zeile 327 ein eigenes Response-Dict manuell gebaut (20+ Felder, Zeilen 341–366), statt das bestehende Pydantic-Schema `TaskRead` zu verwenden.

**Empfehlung:**
- SOP-Restart-Logik in `SOPEngine.start_instance_for_task()` auslagern
- Sub-Agent-Spawning in einen Callback/Hook auslagern
- `TaskRead.model_validate()` konsistent verwenden statt manuellem Dict-Bau

---

### 2.2 Massiv: Doppelte manuelle Dict-Serialisierung in `tasks.py`

**Fundort:**
- `list_tasks` (Zeilen 50–69): Eigenes Dict mit 20 Feldern
- `set_task_status` (Zeilen 341–366): Eigenes Dict mit 24 Feldern

**Problem:** Zwei verschiedene Endpunkte bauen fast identische Dicts für die gleiche Entität (`Task`). Das ist eine Redundanz, die bei jeder Schema-Änderung an **zwei Stellen** gewartet werden muss.

**Empfehlung:** `TaskRead` Schema einheitlich nutzen (so wie `create_task`, `update_task` und andere Endpunkte es tun). Nur wenn zwingend nötig, ein `to_response_dict()`-Helper im Service bereitstellen.

---

### 2.3 Mittel: `sops.py` ist zu groß (1478 Zeilen)

**Fundort:** `backend/app/routers/sops.py`, gesamte Datei

**Problem:** Mit 1478 Zeilen ist der SOP-Router der mit Abstand größte File im Projekt. Der `update_step` Endpoint hat 20+ individuelle `if req.X is not None` Blöcke (Zeilen 344–407), die sich nur durch den Feldnamen unterscheiden.

**Empfehlung:**
- Pattern durch eine generische `apply_updates()`-Methode ersetzen
- Große BPMN/UML/AI-Evaluate Endpunkte in separate Module auslagern (`routers/sops/` Unterordner)

---

### 2.4 Mittel: Unerreichbarer Code (Dead Code) in `tasks.py`

**Fundort:** `backend/app/routers/tasks.py`, Zeilen 213–215

```python
    if not t:
        raise HTTPException(404, "Task not found")
    return TaskRead.model_validate(t)
```

**Problem:** Diese Zeilen stehen **nach einem `return`** (Zeile 212). Sie sind unerreichbar. Entweder ein Merge-Konflikt-Überbleibsel oder versehentlich kopiert.

**Empfehlung:** Löschen.

---

### 2.5 Klein: Doppelter Import in `sops.py`

**Fundort:** Zeile 34 und Zeile 336, 461

**Problem:** `SOPStep` wird auf Modulebene importiert (Zeile 34: `from ..models.sop import SOP, SOPStep, ...`) und dann innerhalb von Funktionen erneut importiert (Zeile 336: `from ..models.sop import SOPStep`, Zeile 461: `from ..models.sop import SOPStep, SOP as _SOP`).

**Empfehlung:** Konsistent den Modul-Level Import verwenden.

---

### 2.6 Klein: Redundanz in `status_labels.py`

**Fundort:** `backend/app/utils/status_labels.py`

**Problem:** Das Label-Mapping wird doppelt definiert:
- `DB_TO_DISPLAY` (Zeilen 29–43): 12 Einträge
- `EMOJI_MAP` (Zeilen 74–88): 13 Einträge (davon 12 mit gleichem Key)

Jeder neue Status muss in **zwei Maps** eingetragen werden. Zudem hat `waiting` als Alternative zu `warten` einen eigenen Eintrag, was zu Inkonsistenzen führen kann.

**Empfehlung:**
- Eine einzige Datenstruktur: `{ "todo": {"display": "GO", "emoji": "✅"}, ... }`
- `display_status()` und `display_status_with_emoji()` daraus ableiten

---

*Ende der Iteration 2*

---

## Iteration 3: Dokumentation & Kommentare

*Untersuchte Dateien:* `README.md`, `docs/ARCHITECTURE.md`, `docs/SOP-ARCHITECTURE.md`, `docs/SKILL-ANFORDERUNGSMANAGEMENT.md`, Code-Kommentare

### 3.1 Mittel: `README.md` verweist auf nicht-existierende Dokumente

**Fundort:** `README.md`, Zeilen 77–79 (Verzeichnisstruktur)

**Problem:** Die README listet folgende Dateien im `docs/`-Verzeichnis:
- `docs/ARCHITECTURE.md` ✅ existiert
- `docs/MIGRATION_PLAN.md` ❌ **existiert nicht**
- `docs/CHANGELOG.md` ❌ **existiert nicht**

Der Leser sucht vergebens nach diesen Dateien.

**Empfehlung:** Entweder die Dateien anlegen oder die Referenzen aus der README entfernen.

---

### 3.2 Mittel: `README.md` verweist auf falschen Dateipfad

**Fundort:** `README.md`, Zeilen 48–49

**Problem:** Die Verzeichnisstruktur zeigt `db/init_db.py` als "DB-Initialization". Diese Datei existiert nicht. Die `init_db()`-Funktion befindet sich in `db/base.py`.

**Empfehlung:** README-Struktur korrigieren: `init_db()` in `base.py` dokumentieren, nicht als separate Datei.

---

### 3.3 Klein: Kein `CHANGELOG.md` vorhanden

**Fundort:** Keine Datei `CHANGELOG.md` im Projekt.

**Problem:** Bei über 15 Migrations-Revisionen und zahlreichen User-Direktiven (15.06.–19.06.2026) gibt es kein strukturiertes Änderungslog.

**Empfehlung:** `CHANGELOG.md` anlegen (Datum, Änderung, betroffene Dateien).

---

### 3.4 Hinweis: `ARCHITECTURE.md` nicht vollständig aktuell

**Fundort:** `docs/ARCHITECTURE.md`, Tabellen-Beschreibungen

**Problem:**
- `tasks`-Tabelle zeigt keine CIO-Triage-Felder (`task_type`, `implementation_plan`, `standards_check`, `subagent_readiness`), die im Code existieren
- `metadata` wird als Spalte gezeigt, heißt im Code aber `meta`
- SOP-Tabellen (`sops`, `sop_steps`, `sop_step_rules`, `sop_instances`, `sop_executions`) fehlen komplett

**Empfehlung:** ARCHITECTURE.md mit tatsächlichem Code abgleichen und SOP-Tabellen ergänzen.

---

### 3.5 Hinweis: Inline-Kommentare gut, aber Begründungen lückenhaft

**Fundort:** Router-Dateien und Model-Kommentare

**Problem:**
- **Positiv:** `status_labels.py` hat hervorragende Docstrings mit Doctests und Beispielen (Vorbildcharakter)
- Router-Endpunkte beschreiben **was** sie tun, erklären aber selten **warum** bestimmte Architekturentscheidungen getroffen wurden
- CIO-Triage-Felder in `task.py` (Zeilen 117–132) sagen nur *was* gespeichert wird, nicht *wann* und in welchem Prozess-Schritt

**Empfehlung:** "Rationale"-Kommentare bei komplexen Business-Entscheidungen ergänzen.

---

*Ende der Iteration 3*

---

## Iteration 4: Openbrain-Konformität

*Untersuchte Dateien:* `docs/SKILL-ANFORDERUNGSMANAGEMENT.md`, `backend/app/config.py`, `backend/app/models/architecture_rule.py`, `backend/app/routers/tasks.py`, `backend/app/routers/workflow.py`

### 4.1 Mittel: Openbrain-URL ist leer (keine Live-Anbindung)

**Fundort:** `backend/app/config.py`, Zeilen 68–69

```python
OPENBRAIN_URL: str = ""
OPENBRAIN_ACCESS_KEY: str = ""
```

**Problem:** Die Konfiguration für die Openbrain-Anbindung ist vorhanden (Settings-Klasse), aber beide Werte sind leer. Eine tatsächliche Live-Synchronisation der Architekturregeln aus dem Openbrain findet nicht statt. Die `architecture_rules`-Tabelle wird stattdessen via Migrations-Script mit hartcodierten Werten befüllt (10 default-Regeln).

**Empfehlung:**
- Entweder den Openbrain-API-Endpunkt konfigurieren und einen Sync-Service implementieren
- Oder die leeren Konfigurationswerte als "nicht verwendet" dokumentieren, damit es keine Verwirrung gibt

---

### 4.2 Mittel: Architekturregeln via Migration hartcodiert (nicht synced)

**Fundort:** `backend/app/migrations/versions/d4e5f6a7b8c9_add_cio_triage_fields.py`, Zeilen 90–132

**Problem:** 10 Architekturregeln werden in einer Datenbank-Migration als `INSERT INTO architecture_rules` angelegt. Das macht die Regeln schwer wartbar – jede Änderung erfordert eine neue Migration. Der Docstring in `architecture_rule.py` sagt "Defaults werden aus dem OpenBrain übernommen", aber das passiert nicht.

**Empfehlung:** Entweder:
- Einen Seed-/Sync-Layer für Openbrain implementieren (empfohlen, da die Architektur darauf ausgelegt ist)
- Oder die Regeln in einer YAML/JSON-Datei definieren und beim App-Start laden (wenn kein Openbrain verfügbar)

---

### 4.3 Klein: `standards_check` auf Task vorhanden, aber keine Prüf-Logik

**Fundort:** `backend/app/models/task.py`, Zeilen 126–128 (+ `routers/tasks.py`, Zeilen 175–192)

**Problem:** Das Task-Model hat ein `standards_check` JSON-Feld und einen PUT-Endpunkt zum Setzen. Es gibt aber **keine automatisierte Prüf-Logik**, die die Standards aus `architecture_rules` gegen den Task validiert. Der Wert wird nur manuell vom CIO via API gesetzt.

**Empfehlung:** Eine Service-Methode `run_standards_check(task_id)` implementieren, die:
1. Alle aktiven `architecture_rules` lädt
2. Task-Daten (Kategorie, Typ, etc.) gegen jede Regel prüft
3. Ergebnis als `standards_check` am Task persistiert

---

### 4.4 Hinweis: Openbrain-Skill vorhanden – aber nicht im Code referenziert

**Fundort:** `docs/SKILL-ANFORDERUNGSMANAGEMENT.md` (OpenBrain-ID `b112ab54...`)

**Problem:** Der Openbrain-Skill "Anforderungsmanagement" ist hervorragend dokumentiert (138 Zeilen, 6 Pflicht-Regeln), aber die ID `b112ab54-488e-461f-8c92-17062bf06aa0` wird nirgendwo im Code referenziert. Es gibt keinen Mechanismus, der prüft, ob die Umsetzung den Skill-Vorgaben entspricht.

**Empfehlung:**
- Skill-ID in die `architecture_rules`-Tabelle als `source_ref` aufnehmen
- Oder eine `skill_checks`-Tabelle einführen, die jeden Task gegen relevante Skills prüft

---

### 4.5 Hinweis: Config-Werte für "minimax-m3" inkonsistent

**Fundort:** `backend/app/routers/tasks.py`, Zeilen 25–31 (Default-Modell) vs. `docs/SKILL-ANFORDERUNGSMANAGEMENT.md`, Zeile 27

**Problem:**
- Der Skill sagt: `minimax-direct/minimax-m3` (Cloud)
- Der Code-Default (Zeilen 25–31) setzt `CODE_AGENT_MODEL=minimax-m3` (ohne Provider-Präfix)

Wenn der Code `f\"{provider}/{model}\"` kombiniert, kann ein inkonsistenter Modell-String entstehen, wenn Provider und Model aus unterschiedlichen Quellen stammen.

**Empfehlung:** Einen einheitlichen `DEFAULT_MODEL`-String in den Settings definieren (statt aus zwei Env-Variablen zusammenzusetzen).

---

*Ende der Iteration 4*

---

## Synopse: Übergreifende Verbesserungsvorschläge

Die 20 Einzelfunde aus den 4 Iterationen lassen sich auf **4 grundlegende Querschnittsthemen** reduzieren:

---

### S1 🔴 KRITISCH: Serialisierungs-Boilerplate beseitigen (~40% aller Funde)

**Betrifft:** 1.1 (JSONType), 1.2 (to_dict), 1.3 (Timestamp), 2.2 (Dict-Dopplung), 2.6 (Label-Map)

**Ursache:** Fehlende Basis-Abstraktionen. Jedes Model definiert Serialisierung und Timestamps eigenhändig.

**Empfehlung "Big Bang Refactoring" (1 Nachmittag):**

```python
# db/mixins.py — einmal schreiben, überall nutzen
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(...)
    updated_at: Mapped[datetime] = mapped_column(...)

class SerializeMixin:
    def to_dict(self, exclude=None):
        exclude = exclude or set()
        return {c.name: getattr(self, c.name) for c in self.__table__.columns
                if c.name not in exclude}
```

Damit entfallen: 1.1 ✓, 1.2 ✓, 1.3 ✓, 2.2 ✓ (>50% Refactor bei tasks.py), 2.6 ✓

**Aufwandsabschätzung:** ~2–3h (Mixin erstellen + Modelle umstellen + tasks.py-Router vereinheitlichen + Router-Response vereinheitlichen)

---

### S2 🟠 HOCH: Monolithen aufbrechen (Service-Refactoring)

**Betrifft:** 2.1 (set_task_status), 2.3 (sops.py), 1.7 (SOP-Over-Engineering)

**Ursache:** Business-Logik wächst in Routern/Models, statt in Services ausgelagert zu werden.

**Empfehlung:**
1. `set_task_status()` aufteilen in: `TaskService.set_status()`, `SOPEngine.restart_for_task()`, `SubAgentService.spawn()`
2. `sops.py` aufteilen in: `sops_crud.py`, `sops_engine.py`, `sops_bpmn.py`, `sops_ai.py`
3. SOP-Modell auf State-Machine-Pattern reduzieren (RACI, BPMN-Koordinaten, Input-Tool bei Bedarf als Plugin laden)

**Bonus-Effekt:** Der unerreichbare Code (2.4) und die Doppelimporte (2.5) verschwinden beim Refactoring von selbst.

**Aufwandsabschätzung:** ~4–6h (Service-Aufteilung + Router-Refactoring + Monolith-Entflechtung)

---

### S3 🟡 MITTEL: Dokumentation mit dem Code synchronisieren

**Betrifft:** 3.1 (fehlende Docs), 3.2 (falscher Pfad), 3.4 (veraltete ARCHITECTURE.md), 4.5 (Config-String inkonsistent)

**Ursache:** README und ARCHITECTURE.md werden bei Code-Änderungen nicht aktualisiert.

**Empfehlung:**
1. `CHANGELOG.md` anlegen und bei jeder User-Direktive einen Eintrag hinzufügen
2. ARCHITECTURE.md mit tatsächlichen Modell-Feldern abgleichen + SOP-Tabellen ergänzen
3. README-Verzeichnisstruktur korrigieren (init_db.py → base.py)
4. Einen konsistenten `DEFAULT_MODEL`-String in `config.py` definieren

**Aufwandsabschätzung:** ~1–2h (Dokumentation abgleichen + CHANGELOG anlegen + Config vereinheitlichen)

---

### S4 🟢 NIEDRIG: Openbrain-Live-Integration vervollständigen

**Betrifft:** 4.1 (leere URL), 4.2 (hartcodierte Regeln), 4.3 (fehlende Prüflogik), 4.4 (Skill nicht referenziert)

**Ursache:** Die Infrastruktur für Openbrain-Integration ist da (architecture_rules-Tabelle, standards_check-Feld, config.py), aber die Live-Anbindung fehlt.

**Empfehlung:** Entscheidung treffen:
- **Option A** (Openbrain-Live): `OPENBRAIN_URL` konfigurieren + Sync-Service schreiben + `run_standards_check()` implementieren
- **Option B** (Kein Openbrain): Leere Config-Werte dokumentieren + Regeln aus Migration in YAML-Datei auslagern

**Aufwandsabschätzung:** Option A: ~4h (Sync-Service + Prüflogik), Option B: ~30min (Doku + YAML)

---

### 🔍 Quick-Wins (sofort umsetzbar, <15 Minuten)

| Fund | Problem | Fix |
|------|---------|-----|
| 2.4 | Dead Code nach return | 2 Zeilen löschen |
| 2.5 | Doppelter Import | überflüssige `from ..models.sop import SOPStep` entfernen |
| 3.1 | README verweist auf nicht-existierende Dateien | Einträge entfernen oder leere Dateien anlegen |
| 3.3 | Kein CHANGELOG.md | Leere Datei mit erster Zeile anlegen |

---

**Ende des Audit-Reports — 20 Funde, 4 Querschnittsthemen, 4 Quick-Wins**
|
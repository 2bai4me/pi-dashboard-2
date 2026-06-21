# PI Dashboard 2.0 — Multi-Provider-Fähigkeit

> **Task-ID:** 826ae31a0743  
> **Projekt:** PI Dashboard 2 (d5976e76247c)  
> **Status:** In Umsetzung

---

## Ziel

Das PI Dashboard 2.0 soll **multi-provider-fähig** werden. Der User kann in den Einstellungen beliebig viele **Provider-Profile** anlegen. In jedem Profil kann er für jede Rolle (z. B. `pi-coder`, `pi-tester`, `CIO`) einen Provider und ein Modell festlegen. Das aktive Profil steuert, welcher Provider/Modell für LLM-Calls verwendet wird.

---

## Datenbank-Schema

### Tabelle: `provider_profiles`

| Feld | Typ | Beschreibung |
|---|---|---|
| `id` | str (PK) | Eindeutige Profil-ID |
| `name` | str | Anzeigename des Profils |
| `is_active` | bool | Nur ein Profil kann aktiv sein |
| `created_at` | datetime | Erstellungszeitpunkt |
| `updated_at` | datetime | Letzte Änderung |

### Tabelle: `provider_profile_role_mappings`

| Feld | Typ | Beschreibung |
|---|---|---|
| `id` | str (PK) | Eindeutige Mapping-ID |
| `profile_id` | str (FK) | Referenz zum Profil |
| `role_name` | str | Rollen-Name (z. B. `pi-coder`) |
| `provider` | str | Provider-Name (z. B. `minimax-direct`, `openrouter`) |
| `model` | str | Modell-ID (z. B. `minimax-m3`) |
| `api_key` | str | Optionaler API-Key für dieses Mapping |
| `base_url` | str | Optionale Base-URL für dieses Mapping |

---

## Backend-Endpunkte

| Methode | Endpoint | Beschreibung |
|---|---|---|
| GET | `/api/provider-profiles` | Liste aller Profile |
| GET | `/api/provider-profiles/{id}` | Detail eines Profils inkl. Mappings |
| POST | `/api/provider-profiles` | Neues Profil anlegen |
| PUT | `/api/provider-profiles/{id}` | Profil aktualisieren |
| DELETE | `/api/provider-profiles/{id}` | Profil löschen |
| POST | `/api/provider-profiles/{id}/activate` | Profil aktivieren (andere werden deaktiviert) |
| GET | `/api/provider-profiles/active` | Aktives Profil abrufen |

---

## Integration mit LLM-Service

- Neue Funktion `get_model_config_for_role(role: str) -> dict`
- Liest das aktive Provider-Profil
- Gibt Provider, Modell, API-Key und Base-URL für die Rolle zurück
- Fallback-Reihenfolge:
  1. Aktives Profil + Mapping für Rolle
  2. ENV-Variablen (`MINIMAX_API_KEY`, etc.)
  3. Fehler, wenn nichts konfiguriert

---

## Frontend-UI

- Neue Seite oder Erweiterung der Config-Page
- Übersicht aller Provider-Profile
- Formular: Name, Mappings (Rolle → Provider → Modell → API-Key → Base-URL)
- Button „Aktivieren" pro Profil
- Anzeige des aktiven Profils

---

## Akzeptanzkriterien

- [ ] Tabellen `provider_profiles` und `provider_profile_role_mappings` existieren
- [ ] Alembic-Migration ist vorhanden
- [ ] CRUD-Endpunkte funktionieren
- [ ] `llm_service.py` verwendet das aktive Profil pro Rolle
- [ ] Frontend erlaubt das Anlegen/Bearbeiten/Löschen von Profilen
- [ ] Tests für Backend-Logik vorhanden
- [ ] Dokumentation aktualisiert

---

## Phasen

1. **Phase 1:** DB-Schema + Modelle + Backend-CRUD
2. **Phase 2:** `llm_service.py` Integration
3. **Phase 3:** Frontend-UI
4. **Phase 4:** Tests + Dokumentation

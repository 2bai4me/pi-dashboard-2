"""RoleService — Verwaltet Sub-Agent- und Org-Rollen."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.role import Role

logger = logging.getLogger("pi-dashboard-2")


def _gen_id() -> str:
    return secrets.token_hex(6)


# Default-Rollen (initialisiert beim Startup)
# IDs sind deterministisch, damit Idempotenz gewaehrleistet ist (Re-Init aendert nichts).
DEFAULT_ROLES = [
    # === Sub-Agents (swarm-spawner) ===
    {
        "id": "role-pi-coder", "name": "pi-coder", "role_type": "sub_agent", "emoji": "💻",
        "description": "Code schreiben, editieren, implementieren",
        "provider": "minimax-direct", "model": "minimax-m3",
        "tool_whitelist": ["read", "write", "edit", "bash", "grep", "find", "ls"],
        "timeout_sec": 900, "fresh_context": True,
        "estimated_savings_usd": Decimal("0"),
    },
    {
        "id": "role-pi-tester", "name": "pi-tester", "role_type": "sub_agent", "emoji": "🧪",
        "description": "Tests ausfuehren, validieren",
        "provider": "minimax-direct", "model": "minimax-m3",
        "tool_whitelist": ["bash", "read"],
        "timeout_sec": 600, "fresh_context": True,
        "estimated_savings_usd": Decimal("0"),
    },
    {
        "id": "role-pi-reviewer", "name": "pi-reviewer", "role_type": "sub_agent", "emoji": "👁️",
        "description": "Code-Review mit frischen Augen",
        "provider": "minimax-direct", "model": "minimax-m3",
        "tool_whitelist": ["read", "grep", "bash", "find"],
        "timeout_sec": 600, "fresh_context": True,
        "estimated_savings_usd": Decimal("0"),
    },
    {
        "id": "role-pi-fixer", "name": "pi-fixer", "role_type": "sub_agent", "emoji": "🔧",
        "description": "Bug-Fixes, Test-Reparatur",
        "provider": "minimax-direct", "model": "minimax-m3",
        "tool_whitelist": ["read", "write", "edit", "bash"],
        "timeout_sec": 900, "fresh_context": True,
        "estimated_savings_usd": Decimal("0"),
    },
    # === Organisationale Rollen (strategische Perspektiven) ===
    {
        "id": "role-ceo-digital", "name": "CEO-digital", "role_type": "org", "emoji": "👑",
        "description": "Chief Executive Officer — strategische Entscheidungen, Vision, Budget-Steuerung",
        "provider": "minimax-direct", "model": "minimax-m3",
        "system_prompt": (
            "You are CEO-digital — the strategic decision-maker and owner of the PI Agent system.\n"
            "- Define vision, priorities, and high-level strategy\n"
            "- Review and approve architectural decisions\n"
            "- Allocate token budgets and model resources\n"
            "- Ultimate authority on all PI Agent operations\n"
            "- Focus: business value, cost efficiency, strategic direction"
        ),
        "tool_whitelist": ["read", "bash", "grep"],
        "timeout_sec": 600, "fresh_context": True,
        "estimated_savings_usd": Decimal("0"),
    },
    {
        "id": "role-cio", "name": "CIO", "role_type": "org", "emoji": "🏗️",
        "description": "Chief Information Officer — technische Infrastruktur, Security, Architektur, GitHub-Backup",
        "provider": "ollama", "model": "gemma4:12b",
        "system_prompt": (
            "You are CIO — responsible for technical infrastructure, security, architecture, and GitHub backup.\n"
            "- Evaluate technical feasibility and risks\n"
            "- Define architecture standards and best practices\n"
            "- Oversee security, compliance, and data governance\n"
            "- Manage technology stack decisions\n"
            "- **GitHub-Backup-Verantwortlichkeit (User-Direktive 15.06.2026):**\n"
            "  - Regelmäßige Sicherung des Codes auf GitHub (https://github.com/2bai4me/pi-dashboard)\n"
            "  - Entscheidet, wann ein 'signifikanter Entwicklungsschritt' erreicht ist\n"
            "  - Bereitet Commits mit aussagekräftigen Messages vor\n"
            "  - Führt Pushes durch, NACHDEM der User die Commit-Message bestätigt hat\n"
            "  - NIEMALS automatisch pushen — immer User-Approval erforderlich\n"
            "  - NIEMALS bei kleinen Änderungen — nur bei Major-Features, Done-Tasks-Meilensteinen, etc.\n"
            "  - Empfohlenes Intervall: alle 8h ODER bei signifikantem Schritt\n"
            "  - Tools: /cio:backup (Status), /cio:backup --message='...' --yes (Commit + Push)\n"
            "- Focus: system integrity, scalability, maintainability, code preservation"
        ),
        "tool_whitelist": ["read", "write", "bash", "grep", "find", "ls"],
        "timeout_sec": 600, "fresh_context": True,
        "estimated_savings_usd": Decimal("0"),
    },
    {
        "id": "role-cmo", "name": "CMO", "role_type": "org", "emoji": "📢",
        "description": "Chief Marketing Officer — Marketing, Branding, Kommunikation",
        "provider": "ollama", "model": "gemma4:12b",
        "system_prompt": (
            "You are CMO — responsible for marketing, communication, and brand strategy.\n"
            "- Craft compelling messaging and positioning\n"
            "- Analyze market trends and competitive landscape\n"
            "- Generate content strategy and copy\n"
            "- Evaluate brand impact and audience engagement\n"
            "- Focus: clarity, persuasion, brand consistency"
        ),
        "tool_whitelist": ["read", "write", "bash", "grep"],
        "timeout_sec": 600, "fresh_context": True,
        "estimated_savings_usd": Decimal("0"),
    },
    {
        "id": "role-cfo", "name": "CFO", "role_type": "org", "emoji": "💰",
        "description": "Chief Financial Officer — Kosten, Budget, ROI, Resource Optimization",
        "provider": "ollama", "model": "gemma4:12b",
        "system_prompt": (
            "You are CFO — responsible for financial planning, cost analysis, and resource optimization.\n"
            "- Track and analyze token costs across providers\n"
            "- Optimize resource allocation and model selection\n"
            "- Calculate ROI of agent operations\n"
            "- Forecast budget needs and cost trends\n"
            "- Focus: cost efficiency, value optimization, financial transparency"
        ),
        "tool_whitelist": ["read", "bash", "grep"],
        "timeout_sec": 600, "fresh_context": True,
        "estimated_savings_usd": Decimal("0"),
    },
]


class RoleService:
    @staticmethod
    def list_roles(db: Session) -> List[Role]:
        """Alle Rollen sortiert nach role_type, name."""
        return list(db.execute(select(Role).order_by(Role.role_type, Role.name)).scalars())

    @staticmethod
    def list_sub_agents(db: Session) -> List[Role]:
        """Nur Sub-Agents (pi-coder, pi-tester, pi-reviewer, pi-fixer)."""
        return list(db.execute(
            select(Role).where(Role.role_type == "sub_agent").order_by(Role.name)
        ).scalars())

    @staticmethod
    def list_org_roles(db: Session) -> List[Role]:
        """Nur Org-Rollen (CEO-digital, CIO, CMO, CFO)."""
        return list(db.execute(
            select(Role).where(Role.role_type == "org").order_by(Role.name)
        ).scalars())

    @staticmethod
    def get_role(db: Session, role_id: str) -> Optional[Role]:
        return db.get(Role, role_id)

    @staticmethod
    def seed_defaults(db: Session) -> int:
        """Initialisiert die Default-Rollen, falls noch nicht vorhanden.

        Idempotent: Existierende Rollen werden in-place aktualisiert
        (emoji, system_prompt, tool_whitelist, timeout_sec, fresh_context).
        Nur description/provider/model werden nicht ueberschrieben, falls
        der User sie manuell geaendert hat (kein Override-Schutz in v2.0-rc,
        wird in v2.1 mit audit-trail nachgeruestet).
        """
        added = 0
        updated = 0
        for rd in DEFAULT_ROLES:
            existing = db.execute(
                select(Role).where(Role.name == rd["name"])
            ).scalar_one_or_none()
            if existing is None:
                r = Role(**rd)
                db.add(r)
                added += 1
            else:
                # Update Felder, die als Default gepflegt werden.
                # provider/model werden mit aktualisiert, damit
                # Provider-Migrationen (z.B. CIO: minimax → ollama) sicher greifen.
                changed = False
                for key in ("emoji", "system_prompt", "tool_whitelist",
                            "timeout_sec", "fresh_context", "role_type",
                            "provider", "model"):
                    new_val = rd.get(key)
                    if new_val is not None and getattr(existing, key) != new_val:
                        setattr(existing, key, new_val)
                        changed = True
                if changed:
                    existing.updated_at = datetime.utcnow()
                    updated += 1
        if added or updated:
            db.commit()
        if added:
            logger.info(f"Seeded {added} new default roles.")
        if updated:
            logger.info(f"Updated {updated} default roles (emoji/system_prompt/etc.).")
        return added

    @staticmethod
    def create_role(db: Session, name: str, **fields) -> Role:
        r = Role(id=_gen_id(), name=name, **{k: v for k, v in fields.items() if hasattr(Role, k)})
        db.add(r)
        db.commit()
        db.refresh(r)
        return r

    @staticmethod
    def update_role(db: Session, role_id: str, **fields) -> Optional[Role]:
        r = db.get(Role, role_id)
        if not r:
            return None
        for k, v in fields.items():
            if v is not None and hasattr(r, k):
                setattr(r, k, v)
        r.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(r)
        return r

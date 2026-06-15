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
DEFAULT_ROLES = [
    # Sub-Agents (swarm-spawner)
    {
        "id": "role-pi-coder", "name": "pi-coder", "role_type": "sub_agent",
        "description": "Code schreiben, editieren, implementieren",
        "provider": "minimax-direct", "model": "minimax-m3",
        "tool_whitelist": ["read", "write", "edit", "bash", "grep"],
        "timeout_sec": 600, "fresh_context": True,
    },
    {
        "id": "role-pi-tester", "name": "pi-tester", "role_type": "sub_agent",
        "description": "Tests ausfuehren, validieren",
        "provider": "minimax-direct", "model": "minimax-m3",
        "tool_whitelist": ["bash", "read"],
        "timeout_sec": 600, "fresh_context": True,
    },
    {
        "id": "role-pi-reviewer", "name": "pi-reviewer", "role_type": "sub_agent",
        "description": "Code-Review mit frischen Augen",
        "provider": "minimax-direct", "model": "minimax-m3",
        "tool_whitelist": ["read", "grep", "bash", "find"],
        "timeout_sec": 600, "fresh_context": True,
    },
    {
        "id": "role-pi-fixer", "name": "pi-fixer", "role_type": "sub_agent",
        "description": "Bug-Fixes, Test-Reparatur",
        "provider": "minimax-direct", "model": "minimax-m3",
        "tool_whitelist": ["read", "write", "edit", "bash"],
        "timeout_sec": 600, "fresh_context": True,
    },
    # Org-Rollen
    {
        "id": "role-cio", "name": "CIO", "role_type": "org",
        "description": "Chief Information Officer — technische Infrastruktur, Security, Architektur, GitHub-Backup",
        "provider": "minimax-direct", "model": "minimax-m3",
        "system_prompt": "You are CIO — responsible for technical infrastructure, security, architecture, and GitHub backup.\n"
                         "- Evaluate technical feasibility and risks\n"
                         "- Define architecture standards and best practices\n"
                         "- Oversee security, compliance, and data governance\n"
                         "- Manage technology stack decisions\n"
                         "- **GitHub-Backup:** Regelmäßige Sicherung des Codes auf GitHub, "
                         "entscheidet wann signifikante Entwicklungsschritte erreicht wurden\n"
                         "- Focus: system integrity, scalability, maintainability, code preservation",
        "tool_whitelist": ["read", "write", "bash", "grep", "find", "ls"],
        "timeout_sec": 600, "fresh_context": True,
    },
    {
        "id": "role-ceo-digital", "name": "CEO-digital", "role_type": "org",
        "description": "Chief Executive Officer — strategische Entscheidungen, Vision, Budget-Steuerung",
        "provider": "minimax-direct", "model": "minimax-m3",
        "system_prompt": "You are CEO-digital — strategic decision-maker and owner of the PI Agent system.",
        "tool_whitelist": ["read", "bash", "grep"],
        "timeout_sec": 600, "fresh_context": True,
    },
]


class RoleService:
    @staticmethod
    def list_roles(db: Session) -> List[Role]:
        return list(db.execute(select(Role).order_by(Role.role_type, Role.name)).scalars())

    @staticmethod
    def get_role(db: Session, role_id: str) -> Optional[Role]:
        return db.get(Role, role_id)

    @staticmethod
    def seed_defaults(db: Session) -> int:
        """Initialisiert die Default-Rollen, falls noch nicht vorhanden."""
        added = 0
        for rd in DEFAULT_ROLES:
            existing = db.execute(
                select(Role).where(Role.name == rd["name"])
            ).scalar_one_or_none()
            if existing is None:
                r = Role(**rd)
                db.add(r)
                added += 1
        if added:
            db.commit()
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

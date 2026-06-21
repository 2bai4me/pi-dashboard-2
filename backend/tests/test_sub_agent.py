"""Unit-Tests fuer den Sub-Agent-Spawner (RCE-Haertung)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Sicherstellen, dass backend/ im Python-Path liegt, falls pytest aus dem Projektroot laeuft.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest

from app.services.sub_agent import (
    ALLOWED_ROLES,
    _validate_spawn_inputs,
    _contains_shell_metacharacters,
)


class TestValidateSpawnInputs:
    """Tests fuer die Eingabevalidierung des Sub-Agent-Spawners."""

    def test_valid_inputs_accepted(self):
        """Erlaubte Werte fuer task_id, title, description und role werden akzeptiert."""
        is_valid, reason = _validate_spawn_inputs(
            task_id="abc123-def_456",
            title="Gültiger Task-Titel",
            description="Beschreibung mit Umlauten: äöü und Zahlen 123.",
            role="pi-coder",
        )
        assert is_valid is True
        assert reason == ""

    @pytest.mark.parametrize("injection_title", [
        "; rm -rf /",
        "$(whoami)",
        "`cat /etc/passwd`",
        'title" && echo injected',
        "normal | cat /etc/shadow",
        "title & malicious_command",
    ])
    def test_shell_injection_in_title_rejected(self, injection_title: str):
        """Shell-Metazeichen im Titel werden abgelehnt."""
        is_valid, reason = _validate_spawn_inputs(
            task_id="task-123",
            title=injection_title,
            description="Saubere Beschreibung",
            role="pi-coder",
        )
        assert is_valid is False
        assert "Shell-Metazeichen" in reason or "unerlaubte Zeichen" in reason

    def test_shell_injection_in_description_rejected(self):
        """Shell-Metazeichen in der Description werden abgelehnt."""
        is_valid, reason = _validate_spawn_inputs(
            task_id="task-123",
            title="Sauberer Titel",
            description="Beschreibung; rm -rf /",
            role="pi-coder",
        )
        assert is_valid is False
        assert "Shell-Metazeichen" in reason or "unerlaubte Zeichen" in reason

    @pytest.mark.parametrize("bad_role", [
        "hacker",
        "root",
        "pi-admin",
        "CEO",
        "",
    ])
    def test_disallowed_role_rejected(self, bad_role: str):
        """Rollen ausserhalb der Whitelist werden abgelehnt."""
        is_valid, reason = _validate_spawn_inputs(
            task_id="task-123",
            title="Sauberer Titel",
            description="Saubere Beschreibung",
            role=bad_role,
        )
        assert is_valid is False
        assert "Whitelist" in reason or "nicht in der Whitelist" in reason or "role fehlt" in reason

    @pytest.mark.parametrize("allowed_role", list(ALLOWED_ROLES))
    def test_allowed_roles_accepted(self, allowed_role: str):
        """Alle Whitelist-Rollen werden akzeptiert."""
        is_valid, reason = _validate_spawn_inputs(
            task_id="task-123",
            title="Sauberer Titel",
            description="Saubere Beschreibung",
            role=allowed_role,
        )
        assert is_valid is True, f"Rolle {allowed_role} sollte erlaubt sein"

    def test_invalid_task_id_rejected(self):
        """Task-IDs mit unerlaubten Zeichen werden abgelehnt."""
        is_valid, reason = _validate_spawn_inputs(
            task_id="task/123;drop",
            title="Sauberer Titel",
            description="Saubere Beschreibung",
            role="pi-coder",
        )
        assert is_valid is False
        assert "task_id" in reason.lower()


class TestShellMetacharacterDetection:
    """Direkte Tests fuer die Shell-Metazeichen-Erkennung."""

    @pytest.mark.parametrize("unsafe", [
        ";",
        "|",
        "&",
        "$",
        "`",
        "<",
        ">",
        "!",
        "#",
        "*",
        "?",
        "{",
        "}",
        "[",
        "]",
        "(",
        ")",
        "\\",
        "\"",
    ])
    def test_detects_shell_metacharacters(self, unsafe: str):
        """Jedes bekannte Shell-Metazeichen wird erkannt."""
        assert _contains_shell_metacharacters(f"foo{unsafe}bar") is True

    def test_safe_strings_pass(self):
        """Normale Texte enthalten keine Shell-Metazeichen."""
        assert _contains_shell_metacharacters("Normaler Text 123") is False
        assert _contains_shell_metacharacters("äöü ÄÖÜ ß") is False

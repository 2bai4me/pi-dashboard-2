"""Hilfs-Skript: Erzeugt einen bcrypt-Hash fuer ADMIN_PASSWORD.

Usage:
    .venv/Scripts/python scripts/hash_admin_pw.py
    .venv/Scripts/python scripts/hash_admin_pw.py "mein-sicheres-passwort"
"""
from __future__ import annotations

import sys

import bcrypt


def main() -> int:
    password = sys.argv[1] if len(sys.argv) > 1 else input("Admin-Passwort: ")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    print(hashed.decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Credential-Service — Verschlüsselte Verwaltung von Provider-API-Keys.

Statt API-Keys im Klartext in der DB zu speichern (altes ProviderCredential-Modell),
werden Keys mit AES-256-GCM verschlüsselt abgelegt.

Architektur:
  - Beim ersten Start wird ein zufälliger Encryption-Key generiert
    und in ENCRYPTION_KEY (Environment) erwartet
  - Jeder API-Key wird vor dem Speichern verschlüsselt (AES-256-GCM)
  - Beim Lesen wird entschlüsselt (nur in Memory)
  - Der Encryption-Key selbst liegt NIEMALS in der DB

Sicherheit:
  - AES-256-GCM (authenticated encryption)
  - Jeder Key hat einen eindeutigen Nonce (12 Byte)
  - Auth-Tag (16 Byte) verhindert Manipulation
  - Encryption-Key muss via ENV gesetzt werden (32 Byte, base64-kodiert)

Environment-Variablen:
  ENCRYPTION_KEY=<32-Byte-base64>  # Pflicht für verschlüsselte Keys

Migration von Klartext- zu verschlüsselten Keys:
  1. ENCRYPTION_KEY in .env setzen
  2. migrate_credentials_to_encrypted() ausführen
  3. Alte Klartext-Spalte `api_key` leeren

Verwendung:
  from ..services.micro.credential_service import encrypt_key, decrypt_key
  
  # Key speichern
  encrypted = encrypt_key("sk-...", credential_id)
  db.execute(update(ProviderCredential).where(...).values(api_key=encrypted))
  
  # Key lesen
  encrypted = db.get(ProviderCredential, id).api_key
  plaintext = decrypt_key(encrypted, id)
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Optional, Tuple

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import settings
from ..utils.exceptions import ServiceError

logger = logging.getLogger("pi-dashboard-2.credential")


def _get_encryption_key() -> bytes:
    """Holt den AES-256-Encryption-Key aus der Environment.
    
    Der Key muss als base64-kodierter 32-Byte-String in ENCRYPTION_KEY gesetzt sein.
    
    Returns:
        32-Byte-Key für AES-256
    
    Raises:
        RuntimeError: Wenn ENCRYPTION_KEY nicht gesetzt ist
    """
    key_b64 = os.getenv("ENCRYPTION_KEY") or getattr(settings, "ENCRYPTION_KEY", None)
    if not key_b64:
        raise RuntimeError(
            "ENCRYPTION_KEY nicht gesetzt! "
            "Setze ENCRYPTION_KEY auf einen base64-kodierten 32-Byte-String.\n"
            "Beispiel (PowerShell):\n"
            "  $key = [byte[]]::new(32); [Security.Cryptography.RNGCryptoServiceProvider]::new().GetBytes($key)\n"
            "  $env:ENCRYPTION_KEY = [Convert]::ToBase64String($key)\n"
            "  [Environment]::SetEnvironmentVariable('ENCRYPTION_KEY', $env:ENCRYPTION_KEY, 'User')"
        )
    
    try:
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            raise ValueError(f"Key must be 32 bytes, got {len(key)}")
        return key
    except Exception as e:
        raise RuntimeError(f"Ungültiger ENCRYPTION_KEY: {e}")


def encrypt_key(plaintext: str, context: str = "") -> str:
    """Verschlüsselt einen API-Key mit AES-256-GCM.
    
    Args:
        plaintext: Der API-Key im Klartext
        context: Optionaler Kontext (z.B. Credential-ID) für zusätzliche Sicherheit
    
    Returns:
        Verschlüsselter String im Format: base64(nonce + ciphertext + tag)
    
    Raises:
        ServiceError: Bei Verschlüsselungsfehlern
    """
    if not plaintext:
        return ""
    
    try:
        key = _get_encryption_key()
        aesgcm = AESGCM(key)
        
        # 12 Byte zufälliger Nonce (Standard für GCM)
        nonce = os.urandom(12)
        
        # Zusätzlicher Authenticated Data (AAD) für Kontext-Bindung
        aad = context.encode() if context else None
        
        # Verschlüsseln
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), aad)
        
        # Format: nonce (12) + ciphertext (variabel) zusammen
        # AESGCM.encrypt gibt nonce + ciphertext + tag zurück (alles zusammen)
        result = base64.b64encode(ciphertext).decode()
        
        logger.debug(f"API-Key verschlüsselt (context={context or 'none'})")
        return result
    except Exception as e:
        raise ServiceError(f"Fehler bei Key-Verschlüsselung: {e}")


def decrypt_key(encrypted: str, context: str = "") -> str:
    """Entschlüsselt einen API-Key.
    
    Args:
        encrypted: Der verschlüsselte Key (base64-kodiert)
        context: Gleicher Kontext wie bei Verschlüsselung
    
    Returns:
        Entschlüsselter API-Key im Klartext
    
    Raises:
        ServiceError: Bei Entschlüsselungsfehlern (falscher Key oder manipulierte Daten)
    """
    if not encrypted:
        return ""
    
    try:
        key = _get_encryption_key()
        aesgcm = AESGCM(key)
        
        # Dekodieren
        ciphertext = base64.b64decode(encrypted)
        
        # AAD (muss identisch mit Verschlüsselung sein)
        aad = context.encode() if context else None
        
        # Entschlüsseln
        plaintext = aesgcm.decrypt(key, ciphertext, aad)
        
        logger.debug(f"API-Key entschlüsselt (context={context or 'none'})")
        return plaintext.decode()
    except Exception as e:
        raise ServiceError(f"Fehler bei Key-Entschlüsselung (falscher Key oder manipulierte Daten): {e}")


def verify_encryption_key() -> bool:
    """Prüft, ob der Encryption-Key gesetzt und gültig ist.
    
    Returns:
        True wenn Key gültig, False sonst
    """
    try:
        key = _get_encryption_key()
        return len(key) == 32
    except Exception:
        return False


# === Migration von Klartext-Keys ===

def migrate_credential_to_encrypted(
    db_session,
    credential_id: str,
    plaintext_key: str,
) -> bool:
    """Migriert einen einzelnen Klartext-Key zu verschlüsselter Speicherung.
    
    Args:
        db_session: SQLAlchemy-Session
        credential_id: ID des ProviderCredential
        plaintext_key: Der aktuelle Klartext-Key
    
    Returns:
        True bei Erfolg, False bei Fehler
    
    Verwendung:
        from ..models.provider_credential import ProviderCredential
        from sqlalchemy import update
        
        encrypted = encrypt_key(old_key, cred.id)
        db.execute(
            update(ProviderCredential)
            .where(ProviderCredential.id == cred.id)
            .values(api_key=encrypted)
        )
    """
    try:
        from sqlalchemy import update
        from ..models.provider_credential import ProviderCredential
        
        encrypted = encrypt_key(plaintext_key, credential_id)
        db_session.execute(
            update(ProviderCredential)
            .where(ProviderCredential.id == credential_id)
            .values(api_key=encrypted)
        )
        db_session.commit()
        logger.info(f"Credential {credential_id[:8]} erfolgreich migriert (verschlüsselt)")
        return True
    except Exception as e:
        logger.error(f"Migration fehlgeschlagen für {credential_id[:8]}: {e}")
        return False


def migrate_all_credentials(db_session) -> Tuple[int, int]:
    """Migriert ALLE Klartext-Keys in der DB zu verschlüsselter Speicherung.
    
    Args:
        db_session: SQLAlchemy-Session
    
    Returns:
        Tuple (migriert, fehlgeschlagen)
    """
    from sqlalchemy import select
    from ..models.provider_credential import ProviderCredential
    
    credentials = db_session.execute(
        select(ProviderCredential)
    ).scalars().all()
    
    migrated = 0
    failed = 0
    
    for cred in credentials:
        if not cred.api_key:
            continue
        
        # Prüfen ob bereits verschlüsselt (base64-kodiert und mit AESGCM-Länge)
        try:
            decoded = base64.b64decode(cred.api_key)
            if len(decoded) > 28:  # nonce(12) + min_data(1) + tag(16) = 29
                # Bereits verschlüsselt?
                logger.debug(f"Credential {cred.id[:8]} scheint bereits verschlüsselt, überspringe")
                continue
        except Exception:
            pass
        
        # Klartext → verschlüsselt
        success = migrate_credential_to_encrypted(db_session, cred.id, cred.api_key)
        if success:
            migrated += 1
        else:
            failed += 1
    
    return migrated, failed

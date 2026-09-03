"""At-rest encryption for per-user provider keys.

The master key lives in the ``SECRETS_ENCRYPTION_KEY`` env var. If unset on
import we generate a fresh Fernet key, save it to the path in
``SECRETS_KEY_FILE`` (default: ``.secrets_key`` next to the project root)
with ``chmod 600``, log a one-time warning telling the operator to back it
up, and use it for this process.

``SECRETS_KEY_FILE`` exists because the default location is only durable
when the project root is. In a container it is not: the app lives in
``/app``, which is an image layer, so a generated key dies with the
container and every ``provider_keys`` row encrypted under it becomes
permanently undecryptable on the next redeploy. The compose file points
this at a named volume so the fallback survives a restart.

This is a service-local secret, not a deployment-wide one — every process
that needs to decrypt a row must see the same key. In production the
operator sets ``SECRETS_ENCRYPTION_KEY`` directly (e.g. via systemd
``EnvironmentFile=``, a Kubernetes Secret, or the docker-compose env file).
The on-disk fallback is for first-run convenience in a homelab deployment
where there is no env-var-injection machinery handy.

Rotation (``scripts/rotate-secrets.sh``) reads the new key, re-encrypts
every ``provider_keys`` row, and atomically swaps the file. A restart of
the API is required to pick up the new key; the in-process Fernet object
is built once at import time and cached.
"""

import base64
import binascii
import hashlib
import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger(__name__)

# Project root: two levels up from surgite/secrets.py. AGENTS.md lives there.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Override the fallback key's location for deployments where the project root
# is not durable storage — see the module docstring.
_SECRETS_FILE = Path(os.environ.get("SECRETS_KEY_FILE") or _PROJECT_ROOT / ".secrets_key")


def _derive_fernet_key(material: str) -> bytes:
    """Fernet wants a 32-byte url-safe base64 key. Accept either:
      - a 44-char urlsafe-b64 string (raw Fernet key, the usual case for
        a value the operator pastes from a secret manager), or
      - an arbitrary passphrase (we SHA-256 it and base64-encode).
    The derived form is also stable across processes, so a passphrase set
    via SECRETS_ENCRYPTION_KEY in dev works the same way on every restart.
    """
    material = material.strip()
    try:
        decoded = base64.urlsafe_b64decode(material)
        if len(decoded) == 32:
            return material.encode("ascii")
    except ValueError, binascii.Error:
        pass
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _load_or_create_master_key() -> bytes:
    """Read SECRETS_ENCRYPTION_KEY, or generate a new one and persist it."""
    env_key = os.environ.get("SECRETS_ENCRYPTION_KEY", "").strip()
    if env_key:
        return _derive_fernet_key(env_key)
    if _SECRETS_FILE.is_file():
        return _derive_fernet_key(_SECRETS_FILE.read_text().strip())
    key = Fernet.generate_key()
    _SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SECRETS_FILE.write_text(key.decode("ascii"))
    os.chmod(_SECRETS_FILE, 0o600)
    log.warning(
        "Generated a new SECRETS_ENCRYPTION_KEY at %s (chmod 600). "
        "Back this file up — provider keys at rest are unrecoverable without it. "
        "To rotate, see scripts/rotate-secrets.sh.",
        _SECRETS_FILE,
    )
    return key


# Cached for the life of the process. Rotations require a restart.
_fernet: Fernet = Fernet(_load_or_create_master_key())


def encrypt(plaintext: str) -> str:
    """Encrypt a provider key. Returns a urlsafe-b64 Fernet token (str)."""
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a Fernet token. Raises InvalidToken if the master key has
    changed (rotation that wasn't completed) or the row is corrupt."""
    try:
        return _fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("Failed to decrypt provider key (rotated master key?)") from e


def rotate_to(new_material: str) -> None:
    """Swap the in-process Fernet to a new master key. Caller is responsible
    for re-encrypting all stored rows with the new key first (see
    scripts/rotate-secrets.sh). Writes the new key to the on-disk file so
    a subsequent restart doesn't fall back to the old one."""
    global _fernet
    _fernet = Fernet(_derive_fernet_key(new_material))
    _SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SECRETS_FILE.write_text(new_material.strip())
    os.chmod(_SECRETS_FILE, 0o600)


def key_file_path() -> Path:
    return _SECRETS_FILE

"""Read and decrypt Preply session cookies from a local Chrome profile.

This module handles the one-time, present-user extraction of a live Preply
session so it can be handed to the credential store. It never persists a cookie
value to disk and never prints one; callers receive values in memory only.

macOS Chrome stores cookies as ``v10`` blobs encrypted with a key derived from
the "Chrome Safe Storage" login-keychain password (PBKDF2-HMAC-SHA1, salt
``saltysalt``, 1003 iterations, AES-128-CBC, IV of 16 spaces). Recent Chrome
builds prepend a 32-byte SHA256(host_key) integrity hash to the plaintext.

Reading the keychain password may trigger one macOS authorization prompt the
first time a new binary asks for it. That is the authorized extraction moment
and is expected to happen only while the user is present.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

def _cipher_primitives():
    """Import `cryptography` at the point of use, not at import time.

    This module is imported by ``main()`` purely for ``ChromeCookieError``, so a
    module-scope import made a missing `cryptography` fatal for *every* command
    -- including ``tutor-reviews``, which needs no login at all -- and it
    surfaced as a raw traceback because that import ran outside main()'s
    ``try``. Only AES decryption actually needs the library, so only AES
    decryption pays for it, and the failure arrives as a normal CLI error.
    """
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:
        raise ChromeCookieError(
            "Reading Chrome's cookie store requires the 'cryptography' package. "
            "Install it with: python3 -m pip install cryptography"
        ) from exc
    return Cipher, algorithms, modes


class ChromeCookieError(RuntimeError):
    """Chrome cookies could not be located or decrypted."""


CHROME_USER_DATA = Path.home() / "Library/Application Support/Google/Chrome"
_SAFE_STORAGE_SERVICE = "Chrome Safe Storage"
_SALT = b"saltysalt"
_ITERATIONS = 1003
_KEY_LENGTH = 16
_IV = b" " * 16
# Auth-relevant Preply cookies. sessionid alone authenticates; csrftoken is
# required for mutations (the x-csrftoken header must match it).
SESSION_COOKIE_NAMES = ("sessionid", "csrftoken")


@dataclass(frozen=True)
class ProfileCookies:
    """Decrypted Preply cookies from one Chrome profile (values in memory)."""

    profile: str
    sessionid: str | None = field(repr=False)
    csrftoken: str | None = field(repr=False)
    sessionid_expiry_webkit: int | None
    # Non-secret reason a present cookie could not be decrypted (diagnostic).
    decrypt_error: str | None = None

    @property
    def has_session(self) -> bool:
        return bool(self.sessionid)


def _safe_storage_key() -> bytes:
    """Derive the AES key from the 'Chrome Safe Storage' keychain password."""
    if sys.platform != "darwin":
        raise ChromeCookieError(
            "Chrome cookie decryption is implemented for macOS only."
        )
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", _SAFE_STORAGE_SERVICE],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise ChromeCookieError("macOS 'security' tool not found.") from exc
    except subprocess.CalledProcessError as exc:
        raise ChromeCookieError(
            "Could not read 'Chrome Safe Storage' from the login keychain. "
            "Approve the keychain prompt, or ensure Chrome has run on this Mac."
        ) from exc
    raw_pw = result.stdout.strip().encode("utf-8")
    if not raw_pw:
        raise ChromeCookieError("Empty 'Chrome Safe Storage' keychain password.")
    return hashlib.pbkdf2_hmac("sha1", raw_pw, _SALT, _ITERATIONS, dklen=_KEY_LENGTH)


def _decrypt_v10(blob: bytes, key: bytes, host_key: str) -> str:
    if not blob.startswith(b"v10"):
        raise ChromeCookieError(f"unexpected cookie encryption scheme: {blob[:3]!r}")
    ciphertext = blob[3:]
    Cipher, algorithms, modes = _cipher_primitives()
    decryptor = Cipher(algorithms.AES(key), modes.CBC(_IV)).decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    if plaintext:
        pad = plaintext[-1]
        if 1 <= pad <= 16:
            plaintext = plaintext[:-pad]
    # Newer Chrome prepends a 32-byte SHA256(host_key) integrity hash.
    if plaintext[:32] == hashlib.sha256(host_key.encode()).digest():
        plaintext = plaintext[32:]
    else:
        try:
            plaintext.decode("utf-8")
        except UnicodeDecodeError:
            plaintext = plaintext[32:]
    return plaintext.decode("utf-8", "replace")


def _profile_dirs() -> list[Path]:
    if not CHROME_USER_DATA.is_dir():
        return []
    dirs = []
    for child in sorted(CHROME_USER_DATA.iterdir()):
        if child.is_dir() and (child / "Cookies").exists():
            dirs.append(child)
    return dirs


def _read_profile(profile_dir: Path, key: bytes) -> ProfileCookies:
    cookies_db = profile_dir / "Cookies"
    with tempfile.TemporaryDirectory() as tmp:
        # Copy first: Chrome holds a write lock on the live database.
        db_copy = Path(tmp) / "Cookies"
        shutil.copy2(cookies_db, db_copy)
        conn = sqlite3.connect(f"file:{db_copy}?mode=ro", uri=True)
        try:
            # Match only the real Preply domain, not any host containing the
            # substring "preply" (sessionid/csrftoken are generic Django names).
            rows = conn.execute(
                "SELECT name, host_key, encrypted_value, expires_utc FROM cookies "
                "WHERE name IN (?, ?) "
                "AND (host_key = 'preply.com' OR host_key LIKE '%.preply.com') "
                "ORDER BY expires_utc DESC",
                SESSION_COOKIE_NAMES,
            ).fetchall()
        finally:
            conn.close()
    values: dict[str, str] = {}
    expiry: dict[str, int] = {}
    decrypt_error: str | None = None
    for name, host_key, blob, expires in rows:
        if name in values:
            continue  # keep the longest-lived variant (ORDER BY expiry DESC)
        try:
            values[name] = _decrypt_v10(bytes(blob), key, host_key)
            expiry[name] = int(expires)
        except (ChromeCookieError, ValueError) as exc:
            # A present-but-undecryptable cookie is a real signal (e.g. a future
            # app-bound v20 scheme). Record the non-secret reason so capture can
            # distinguish "not logged in" from "could not decrypt".
            if decrypt_error is None:
                decrypt_error = f"{name}: {exc}"
            continue
    return ProfileCookies(
        profile=profile_dir.name,
        sessionid=values.get("sessionid"),
        csrftoken=values.get("csrftoken"),
        sessionid_expiry_webkit=expiry.get("sessionid"),
        decrypt_error=decrypt_error if not values.get("sessionid") else None,
    )


def read_profile_cookies(profile: str) -> ProfileCookies:
    """Decrypt Preply session cookies for one named Chrome profile."""
    profile_dir = CHROME_USER_DATA / profile
    if not (profile_dir / "Cookies").exists():
        raise ChromeCookieError(f"No Chrome cookie database for profile {profile!r}.")
    return _read_profile(profile_dir, _safe_storage_key())


def read_all_profiles() -> list[ProfileCookies]:
    """Decrypt Preply session cookies for every Chrome profile that has any.

    Profiles with no Preply sessionid are still returned (has_session False) so
    callers can report them.
    """
    profiles = _profile_dirs()
    if not profiles:
        raise ChromeCookieError(f"No Chrome profiles found under {CHROME_USER_DATA}.")
    key = _safe_storage_key()
    out: list[ProfileCookies] = []
    for profile_dir in profiles:
        try:
            cookies = _read_profile(profile_dir, key)
        except ChromeCookieError:
            continue
        if cookies.sessionid or cookies.csrftoken or cookies.decrypt_error:
            out.append(cookies)
    return out


def webkit_to_iso(value: int | None) -> str | None:
    """Convert a Chrome/WebKit microsecond timestamp to an ISO-8601 string."""
    if not value:
        return None
    import datetime as dt

    epoch = dt.datetime(1601, 1, 1, tzinfo=dt.timezone.utc)
    try:
        return (epoch + dt.timedelta(microseconds=int(value))).isoformat()
    except (OverflowError, ValueError):
        return None

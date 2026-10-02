"""Offline licence validation for the Tanzim Pedagogique desktop app.

Licences are JSON payloads signed with Ed25519.  The application contains only
the public key; the private key stays with the person issuing licences.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import platform
import subprocess
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

APP_ID = "tanzim-pedagogique"
LICENCE_FORMAT = 1
EMBEDDED_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA3h4RT3DzjXB95PBP80rHuOwt5ZEL4Rmb+byG0YB9lyY=
-----END PUBLIC KEY-----
"""


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def licence_code(document: dict) -> str:
    """Portable activation code: safe to copy through chat, email, or SMS."""
    raw = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "TP1-" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def document_from_code(code: str) -> dict:
    normalized = "".join(code.strip().split())
    if not normalized.startswith("TP1-"):
        raise ValueError("كود التفعيل يجب أن يبدأ بـ TP1-.")
    encoded = normalized[4:]
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        document = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
        raise ValueError("كود التفعيل غير صالح.") from exc
    if not isinstance(document, dict):
        raise ValueError("كود التفعيل غير صالح.")
    return document


def device_id() -> str:
    """Stable, privacy-preserving identifier used only for device-bound licences."""
    components = [platform.system(), platform.node(), os.environ.get("COMPUTERNAME", "")]
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                0, winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
            ) as key:
                components.append(str(winreg.QueryValueEx(key, "MachineGuid")[0]))
        except (OSError, ImportError):
            pass
        try:
            bios_uuid = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
                text=True, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=4,
            ).strip()
            if bios_uuid and bios_uuid != "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF":
                components.append(bios_uuid)
        except (OSError, subprocess.SubprocessError):
            pass
    raw = "|".join(part.strip().upper() for part in components if part)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()[:24]


@dataclass(frozen=True)
class LicenceStatus:
    valid: bool
    message: str
    payload: dict | None = None


class LicenceManager:
    def __init__(self, data_dir: Path, public_key_path: Path | None = None):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "licence.json"
        self.public_key_path = Path(public_key_path) if public_key_path else None

    def validate(self) -> LicenceStatus:
        if not self.path.exists():
            return LicenceStatus(False, "لم يتم تفعيل التطبيق بعد.")
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            payload = document["payload"]
            signature = base64.b64decode(document["signature"], validate=True)
            if payload.get("format") != LICENCE_FORMAT or payload.get("app_id") != APP_ID:
                return LicenceStatus(False, "ملف الرخصة لا يخص هذا التطبيق.")
            public_key = serialization.load_pem_public_key(EMBEDDED_PUBLIC_KEY_PEM)
            if not isinstance(public_key, Ed25519PublicKey):
                return LicenceStatus(False, "مفتاح التحقق غير صالح.")
            public_key.verify(signature, _canonical(payload))
            bound_device = payload.get("device_id")
            if bound_device and bound_device != device_id():
                return LicenceStatus(False, "هذه الرخصة مفعّلة لجهاز آخر.")
            issued = date.fromisoformat(payload["issued_on"])
            if issued > date.today():
                return LicenceStatus(False, "تاريخ إصدار الرخصة غير صالح.")
            expires = payload.get("expires_on")
            if expires and date.fromisoformat(expires) < date.today():
                return LicenceStatus(False, "انتهت صلاحية الرخصة.")
            return LicenceStatus(True, "الرخصة صالحة.", payload)
        except (OSError, ValueError, KeyError, TypeError, binascii.Error, InvalidSignature) as exc:
            return LicenceStatus(False, f"ملف الرخصة غير صالح: {exc}")

    def install(self, source: str | Path) -> LicenceStatus:
        source = Path(source)
        try:
            content = source.read_text(encoding="utf-8")
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return LicenceStatus(False, f"تعذر حفظ الرخصة: {exc}")
        status = self.validate()
        if not status.valid:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
        return status

    def install_code(self, code: str) -> LicenceStatus:
        try:
            content = json.dumps(document_from_code(code), ensure_ascii=False, indent=2)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.path.write_text(content, encoding="utf-8")
        except (OSError, ValueError) as exc:
            return LicenceStatus(False, f"تعذر حفظ كود التفعيل: {exc}")
        status = self.validate()
        if not status.valid:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
        return status


def create_key_pair(private_path: Path, public_path: Path) -> None:
    private_path = Path(private_path)
    public_path = Path(public_path)
    if private_path.exists() or public_path.exists():
        raise FileExistsError("مفاتيح الرخصة موجودة بالفعل؛ لن يتم استبدالها.")
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.generate()
    private_path.write_bytes(private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ))
    public_path.write_bytes(private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ))


def issue_licence(private_key_path: Path, customer: str, device: str, expires_on: str | None = None) -> dict:
    private_key = serialization.load_pem_private_key(Path(private_key_path).read_bytes(), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("مفتاح التوقيع يجب أن يكون Ed25519.")
    if expires_on:
        date.fromisoformat(expires_on)  # Validate before creating the licence.
    payload = {
        "format": LICENCE_FORMAT,
        "app_id": APP_ID,
        "customer": customer.strip(),
        "device_id": device.strip().upper(),
        "issued_on": date.today().isoformat(),
        "expires_on": expires_on or None,
        "licence_id": str(uuid.uuid4()),
    }
    return {"payload": payload, "signature": base64.b64encode(private_key.sign(_canonical(payload))).decode("ascii")}

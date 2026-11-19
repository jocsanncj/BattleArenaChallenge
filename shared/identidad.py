"""Nombres de jugador para las identidades verificadas por Google."""

import hashlib


def nombre_jugador_google(uid: str, correo: str, nombre: str | None) -> str:
    # Escritorio y móvil usan el mismo sufijo para distinguir dos cuentas de
    # Google con el mismo nombre visible. El perfil se guarda con el UID completo.
    base = nombre if isinstance(nombre, str) and nombre else correo.partition("@")[0]
    base = base.replace("@", "").strip()[:27] or "Jugador"
    sufijo = hashlib.sha256(uid.encode("utf-8")).hexdigest()[:12]
    return f"{base}-{sufijo}"

"""Nombres de jugador para las identidades verificadas por Google."""

import hashlib


def nombre_jugador_google(uid: str, correo: str, nombre: str | None) -> str:
    # Para un perfil nuevo se usa el nombre visible de Google o la parte del correo anterior a @.
    # Los dos clientes usan la misma regla de longitud y el mismo sufijo derivado del UID. Así, dos
    # personas con el mismo nombre visible pueden jugar con nombres distintos sin mostrar su UID completo.
    base = nombre if isinstance(nombre, str) and nombre else correo.partition("@")[0]
    base = base.replace("@", "").strip()[:27] or "Jugador"
    sufijo = hashlib.sha256(uid.encode("utf-8")).hexdigest()[:12]
    return f"{base}-{sufijo}"

"""Capa de casos de uso del cliente: registro, login, verificación y recuperación.

Capas:  Escenas (UI)  ->  ServicioAuth (este archivo)  ->  ClientesHttp (Firebase y servidor)
"""

import re
from dataclasses import dataclass
from typing import Protocol

from ClientesHttp import (AuthError, ClienteServidor, CorreoPendiente,CredencialesInvalidas, FirebaseAuth)

# ------------------------------------------- abstracciones (Inversión de dependencias)
class ProveedorIdentidad(Protocol):
    def registrar(self, correo: str, password: str) -> dict: ...
    def iniciar_sesion(self, correo: str, password: str) -> dict: ...
    def renovar(self, refresh_token: str) -> dict: ...
    def datos_cuenta(self, id_token: str) -> dict: ...
    def poner_nombre(self, id_token: str, nombre: str) -> None: ...
    def enviar_verificacion(self, id_token: str) -> None: ...
    def enviar_recuperacion(self, correo: str) -> None: ...


class ApiPerfiles(Protocol):
    def nombre_disponible(self, nombre: str) -> bool: ...
    def correo_de(self, nombre: str) -> str | None: ...
    def guardar_perfil(self, token: str, nombre: str) -> dict: ...
    def obtener_perfil(self, token: str) -> dict: ...


# ------------------------------------------------------ dominio y servicio
@dataclass
class Sesion:
    id_token: str
    refresh_token: str
    email: str
    nombre: str | None = None


def validar_registro(nombre: str, correo: str, password: str, confirmacion: str) -> None:
    """Reglas mínimas del registro (CA-01.4)."""
    if not nombre or len(nombre) > 40:
        raise ValueError("El nombre debe tener entre 1 y 40 caracteres.")
    if "@" in nombre:
        raise ValueError("El nombre de usuario no puede contener '@'.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
        raise ValueError("El formato del correo no es válido.")
    if len(password) < 8 or not any(c.isalpha() for c in password) \
            or not any(c.isdigit() for c in password):
        raise ValueError("La contraseña debe tener al menos 8 caracteres, con letras y números.")
    if password != confirmacion:
        raise ValueError("Las contraseñas no coinciden.")


class ServicioAuth:
    """Casos de uso de cuenta. Recibe sus dependencias, así se puede probar sin red."""

    def __init__(self, identidad: ProveedorIdentidad, servidor: ApiPerfiles):
        self._identidad = identidad
        self._servidor = servidor
        self._sesion: Sesion | None = None

    # -- sesión
    def _abrir_sesion(self, respuesta: dict) -> None:
        try:
            self._sesion = Sesion(respuesta["idToken"], respuesta["refreshToken"], respuesta["email"])
        except KeyError as error:
            raise AuthError("Firebase no devolvió una sesión completa.") from error

    def _token(self, renovar: bool = False) -> str:
        if self._sesion is None:
            raise AuthError("Inicia sesión para continuar.")
        if renovar:
            nuevo = self._identidad.renovar(self._sesion.refresh_token)
            self._sesion.id_token, self._sesion.refresh_token = nuevo["idToken"], nuevo["refreshToken"]
        return self._sesion.id_token

    def _resolver_correo(self, identificador: str) -> str | None:
        """Acepta usuario o correo y devuelve el correo (None si el usuario no existe)."""
        identificador = identificador.strip()
        return identificador if "@" in identificador else self._servidor.correo_de(identificador)

    # -- casos de uso
    def registrar(self, nombre, password, confirmacion, correo) -> dict:
        nombre, correo = nombre.strip(), correo.strip()
        validar_registro(nombre, correo, password, confirmacion)
        if not self._servidor.nombre_disponible(nombre):
            raise ValueError("Ese nombre de usuario ya está en uso.")
        self._abrir_sesion(self._identidad.registrar(correo, password))
        self._identidad.poner_nombre(self._token(), nombre)
        self._identidad.enviar_verificacion(self._token())
        self._servidor.guardar_perfil(self._token(), nombre)
        return {"verification_required": True, "verification_sent": True}

    def autenticar(self, identificador, password) -> dict | None:
        correo = self._resolver_correo(identificador)
        if correo is None:
            return None
        try:
            self._abrir_sesion(self._identidad.iniciar_sesion(correo, password))
        except CredencialesInvalidas:
            return None
        cuenta = self._identidad.datos_cuenta(self._token())
        if cuenta.get("emailVerified") is not True:
            raise CorreoPendiente("Tu correo todavía no está verificado. Revisa tu bandeja de entrada.")
        nombre = (cuenta.get("displayName") or "").strip() or correo.partition("@")[0]
        perfil = self._servidor.guardar_perfil(self._token(), nombre)
        self._sesion.nombre = perfil.get("name", nombre)
        return perfil

    def obtener_perfil(self) -> dict:
        return self._servidor.obtener_perfil(self._token(renovar=True))

    def reenviar_verificacion(self, identificador) -> None:
        if self._sesion is None:
            raise AuthError("Inicia sesión con esa cuenta para reenviar la verificación.")
        if (self._resolver_correo(identificador) or "").casefold() != self._sesion.email.casefold():
            raise ValueError("El correo no coincide con la cuenta activa.")
        self._identidad.enviar_verificacion(self._token(renovar=True))

    def recuperar_contrasena(self, identificador) -> None:
        if not identificador.strip():
            raise ValueError("Escribe tu usuario o correo electrónico.")
        correo = self._resolver_correo(identificador)
        if correo:
            try:
                self._identidad.enviar_recuperacion(correo)
            except CredencialesInvalidas:
                pass  # respuesta genérica: no revela si la cuenta existe

    def cerrar_sesion(self) -> None:
        self._sesion = None

    def usuario_actual(self) -> str | None:
        return self._sesion.nombre if self._sesion else None


# Instancia por defecto con los nombres que ya importa Escenas.py.
_servicio = ServicioAuth(FirebaseAuth(), ClienteServidor())
registrar_usuario = _servicio.registrar
autenticar_usuario = _servicio.autenticar
obtener_usuario = _servicio.obtener_perfil
reenviar_verificacion = _servicio.reenviar_verificacion
solicitar_recuperacion = _servicio.recuperar_contrasena
cerrar_sesion = _servicio.cerrar_sesion
usuario_actual = _servicio.usuario_actual

# CAMBIO ONLINE: puente de infraestructura para los repositorios del juego.
_ultimo_refresh_juego = 0.0

def token_para_juego() -> str:
    """Devuelve un token de sesión; lo renueva como máximo cada 45 minutos para no saturar Firebase."""
    import time
    global _ultimo_refresh_juego
    ahora = time.monotonic()
    renovar = ahora - _ultimo_refresh_juego >= 45 * 60
    token = _servicio._token(renovar=renovar)
    if renovar:
        _ultimo_refresh_juego = ahora
    return token

def cliente_juego() -> ClienteServidor:
    """Devuelve el adaptador HTTP compartido con el que se consulta el servidor Docker."""
    return _servicio._servidor

def id_usuario_actual() -> int:
    """Genera un identificador entero estable a partir del UID de Firebase para el modelo legado."""
    import hashlib
    token = token_para_juego()
    cuenta = _servicio._identidad.datos_cuenta(token)
    uid = str(cuenta.get("localId", ""))
    if not uid:
        raise AuthError("No se pudo identificar la cuenta para jugar online.")
    return int.from_bytes(hashlib.sha256(uid.encode("utf-8")).digest()[:4], "big") & 0x7fffffff

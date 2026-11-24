"""Capa de casos de uso del cliente: registro, login, verificación y recuperación.

Capas:  Escenas (UI)  ->  ServicioAuth (este archivo)  ->  ClientesHttp (Firebase y servidor)
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Protocol

from shared.identidad import nombre_jugador_google

from .http_client import (
    AuthError,
    ClienteServidor,
    CorreoPendiente,
    CredencialesInvalidas,
    FirebaseAuth,
    PerfilNoEncontrado,
)

# ------------------------------------------- abstracciones (Inversión de dependencias)
class ProveedorIdentidad(Protocol):
    def registrar(self, correo: str, password: str) -> dict: ...
    def iniciar_sesion(self, correo: str, password: str) -> dict: ...
    # El adaptador recibe el access token de Google. El servicio espera en la respuesta el UID, el correo y los tokens de Firebase.
    def iniciar_sesion_google(self, credencial: str) -> dict: ...
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
    id_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    email: str
    nombre: str | None = None


## @brief US-01–US-02: valida nombre, correo, contraseña y confirmación de registro.
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
    ## @brief US-01–US-05 y US-29: configura las dependencias y el estado de sesión.
    def __init__(self, identidad: ProveedorIdentidad, servidor: ApiPerfiles):
        self._identidad = identidad
        self._servidor = servidor
        self._sesion: Sesion | None = None
    # -- sesión
    ## @brief US-01–US-05 y US-29: guarda los tokens entregados por Firebase.
    def _abrir_sesion(self, respuesta: dict) -> None:
        try:
            self._sesion = Sesion(respuesta["idToken"], respuesta["refreshToken"], respuesta["email"])
        except KeyError as error:
            raise AuthError("Firebase no devolvió una sesión completa.") from error
    ## @brief US-01–US-05 y US-29: obtiene el token vigente y lo renueva si se solicita.
    def _token(self, renovar: bool = False) -> str:
        if self._sesion is None:
            raise AuthError("Inicia sesión para continuar.")
        if renovar:
            nuevo = self._identidad.renovar(self._sesion.refresh_token)
            self._sesion.id_token, self._sesion.refresh_token = nuevo["idToken"], nuevo["refreshToken"]
        return self._sesion.id_token
    ## @brief US-03 y US-05: resuelve un nombre de usuario a su correo.
    def _resolver_correo(self, identificador: str) -> str | None:
        """Acepta usuario o correo y devuelve el correo (None si el usuario no existe)."""
        identificador = identificador.strip()
        return identificador if "@" in identificador else self._servidor.correo_de(identificador)
    # -- casos de uso
    ## @brief US-01–US-02: registra la cuenta, crea el perfil y envía verificación.
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
    ## @brief US-03–US-04: autentica con correo o nombre y devuelve el perfil.
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
    ## @brief US-29: valida Google y prepara un perfil sin activar aún la sesión de juego.
    def preparar_acceso_google(self, credencial: str) -> tuple[Sesion, dict]:
        """Verifica el acceso y carga el perfil antes de activar la sesión del juego."""
        # El servidor local de la pestaña llama aquí con accessToken. El idToken obtenido autoriza la consulta a /api/profile;
        # refreshToken permite renovar esa sesión más adelante. El menú todavía puede cancelar este intento.
        respuesta = self._identidad.iniciar_sesion_google(credencial)
        # Firebase pide confirmación cuando el correo ya está asociado a otra credencial.
        # El jugador debe volver a entrar con el método original para conservar su cuenta.
        if respuesta.get("needConfirmation"):
            raise AuthError("Este correo ya tiene una cuenta. Usa su método de acceso original.")
        if respuesta.get("providerId") != "google.com" or respuesta.get("emailVerified") is not True:
            raise AuthError("Firebase no confirmó un correo verificado de Google.")
        uid = respuesta.get("localId")
        correo = respuesta.get("email")
        token = respuesta.get("idToken")
        refresh = respuesta.get("refreshToken")
        if not all(isinstance(valor, str) and valor for valor in (uid, correo, token, refresh)):
            raise AuthError("Firebase no devolvió una sesión completa.")
        try:
            perfil = self._servidor.obtener_perfil(token)
        except PerfilNoEncontrado:
            # Solo un 404 entra en esta rama. El UID distingue a dos jugadores con el mismo nombre visible;
            # un error de conexión llega al menú para que se pueda reintentar sin crear un perfil por error.
            nombre = nombre_jugador_google(uid, correo, respuesta.get("displayName"))
            perfil = self._servidor.guardar_perfil(token, nombre)
        nombre_perfil = perfil.get("name")
        if not isinstance(nombre_perfil, str) or not nombre_perfil.strip():
            raise AuthError("El servidor no devolvió un nombre de jugador válido.")
        # El menú activa esta sesión al recoger el resultado del intento que sigue abierto en Pygame.
        return Sesion(token, refresh, correo, nombre_perfil), perfil
    # La pantalla llama aquí tras comprobar que sigue esperando ese intento. Desde ese momento, el perfil y la sala
    # pueden usar los tokens de la misma sesión que usarían con el acceso por correo.
    ## @brief US-29: activa en el cliente la sesión de Google que ya fue validada.
    def activar_acceso_google(self, sesion: Sesion) -> None:
        self._sesion = sesion
    ## @brief US-04: consulta el perfil de la cuenta autenticada.
    def obtener_perfil(self) -> dict:
        return self._servidor.obtener_perfil(self._token(renovar=True))
    ## @brief US-02: reenvía verificación solo a la cuenta que tiene sesión activa.
    def reenviar_verificacion(self, identificador) -> None:
        if self._sesion is None:
            raise AuthError("Inicia sesión con esa cuenta para reenviar la verificación.")
        if (self._resolver_correo(identificador) or "").casefold() != self._sesion.email.casefold():
            raise ValueError("El correo no coincide con la cuenta activa.")
        self._identidad.enviar_verificacion(self._token(renovar=True))
    ## @brief US-05: solicita a Firebase un enlace de recuperación de contraseña.
    def recuperar_contrasena(self, identificador) -> None:
        if not identificador.strip():
            raise ValueError("Escribe tu usuario o correo electrónico.")
        correo = self._resolver_correo(identificador)
        if correo:
            try:
                self._identidad.enviar_recuperacion(correo)
            except CredencialesInvalidas:
                pass  # respuesta genérica: no revela si la cuenta existe
    ## @brief US-04: elimina la sesión activa de la aplicación.
    def cerrar_sesion(self) -> None:
        self._sesion = None
    ## @brief US-04: devuelve el nombre de la sesión activa, si existe.
    def usuario_actual(self) -> str | None:
        return self._sesion.nombre if self._sesion else None


# Instancia por defecto compartida por las pantallas de cuenta.
_servicio = ServicioAuth(FirebaseAuth(), ClienteServidor())
registrar_usuario = _servicio.registrar
autenticar_usuario = _servicio.autenticar
preparar_acceso_google = _servicio.preparar_acceso_google
activar_acceso_google = _servicio.activar_acceso_google
obtener_usuario = _servicio.obtener_perfil
reenviar_verificacion = _servicio.reenviar_verificacion
solicitar_recuperacion = _servicio.recuperar_contrasena
cerrar_sesion = _servicio.cerrar_sesion
usuario_actual = _servicio.usuario_actual

# CAMBIO ONLINE: puente de infraestructura para los repositorios del juego.
_ultimo_refresh_juego = 0.0

## @brief US-06–US-31: proporciona un token renovado para las peticiones del juego.
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

## @brief US-06–US-31: obtiene el adaptador HTTP compartido del juego.
def cliente_juego() -> ClienteServidor:
    """Devuelve el adaptador HTTP compartido con el que se consulta el servidor Docker."""
    return _servicio._servidor

## @brief US-06–US-10: convierte el UID de Firebase al ID entero usado por el juego.
def id_usuario_actual() -> int:
    """Genera un identificador entero estable a partir del UID de Firebase para el modelo legado."""
    token = token_para_juego()
    cuenta = _servicio._identidad.datos_cuenta(token)
    uid = str(cuenta.get("localId", ""))
    if not uid:
        raise AuthError("No se pudo identificar la cuenta para jugar online.")
    return int.from_bytes(hashlib.sha256(uid.encode("utf-8")).digest()[:4], "big") & 0x7fffffff
## @brief US-27: consulta el ranking mediante el adaptador del servidor.
def obtener_ranking():
    return cliente_juego().obtener_ranking()

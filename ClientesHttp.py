"""Capa de infraestructura del cliente: habla con Firebase Auth y con el servidor del juego."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------- errores
class AuthError(RuntimeError):
    """Error base de autenticación; su mensaje se puede mostrar al usuario."""


class CredencialesInvalidas(AuthError):
    """Usuario, correo o contraseña incorrectos."""


class CorreoPendiente(AuthError):
    """La cuenta existe pero su correo aún no está verificado."""


MENSAJES_FIREBASE = {
    "EMAIL_EXISTS": "Ese correo ya tiene una cuenta.",
    "INVALID_EMAIL": "La dirección de correo no es válida.",
    "WEAK_PASSWORD": "La contraseña es demasiado débil.",
    "USER_DISABLED": "Esta cuenta fue deshabilitada.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Demasiados intentos. Espera un momento.",
    "OPERATION_NOT_ALLOWED": "Activa Correo/contraseña en Firebase Authentication.",
    "API_KEY_INVALID": "Falta una API key válida en FIREBASE_API_KEY.",
}
CODIGOS_CREDENCIALES = {"INVALID_PASSWORD", "INVALID_LOGIN_CREDENTIALS", "EMAIL_NOT_FOUND"}


# ------------------------------------------------------------- HTTP común
class _ErrorHttp(Exception):
    """Respuesta HTTP de error; guarda el cuerpo JSON para que lo interprete el adaptador."""

    def __init__(self, cuerpo: dict):
        super().__init__("error HTTP")
        self.cuerpo = cuerpo


def _json(datos: bytes) -> dict:
    try:
        resultado = json.loads(datos.decode("utf-8"))
    except ValueError:
        return {}
    return resultado if isinstance(resultado, dict) else {}


def _enviar(request: Request, timeout: int = 15) -> dict:
    """Ejecuta la petición y devuelve el JSON de la respuesta."""
    try:
        with urlopen(request, timeout=timeout) as respuesta:
            datos = respuesta.read()
    except HTTPError as error:
        raise _ErrorHttp(_json(error.read())) from error
    except (URLError, TimeoutError, OSError) as error:
        raise AuthError(f"No se pudo conectar con el servicio: {error}") from error
    return _json(datos)


# ------------------------------------------------------------- adaptadores
class FirebaseAuth:
    """Adaptador de la API REST de Firebase Auth (implementa ProveedorIdentidad)."""

    URL = "https://identitytoolkit.googleapis.com/v1/accounts:"
    URL_TOKEN = "https://securetoken.googleapis.com/v1/token"

    @staticmethod
    def _key() -> str:
        key = os.getenv("FIREBASE_API_KEY", "").strip()
        if not key:
            raise AuthError("Configura FIREBASE_API_KEY en el archivo .env.")
        return key

    def _llamar(self, accion: str, datos: dict) -> dict:
        request = Request(
            f"{self.URL}{accion}?key={self._key()}",
            json.dumps(datos).encode("utf-8"),
            {"Content-Type": "application/json"},
            method="POST",
        )
        try:
            return _enviar(request)
        except _ErrorHttp as error:
            detalle = error.cuerpo.get("error")
            mensaje = detalle.get("message", "") if isinstance(detalle, dict) else ""
            codigo = mensaje.split(" : ")[0] or "ERROR"
            if codigo in CODIGOS_CREDENCIALES:
                raise CredencialesInvalidas("Usuario/correo o contraseña incorrectos.") from error
            raise AuthError(
                MENSAJES_FIREBASE.get(codigo, f"Firebase rechazó la solicitud ({codigo}).")
            ) from error

    def registrar(self, correo, password):
        return self._llamar("signUp", {"email": correo, "password": password,"returnSecureToken": True})

    def iniciar_sesion(self, correo, password):
        return self._llamar("signInWithPassword", {"email": correo, "password": password,"returnSecureToken": True})

    def renovar(self, refresh_token):
        form = urlencode({"grant_type": "refresh_token", "refresh_token": refresh_token})
        request = Request(f"{self.URL_TOKEN}?key={self._key()}", form.encode("utf-8"),{"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            r = _enviar(request)
        except _ErrorHttp as error:
            raise AuthError("No se pudo renovar la sesión. Inicia sesión de nuevo.") from error
        if not r.get("id_token") or not r.get("refresh_token"):
            raise AuthError("Firebase devolvió una sesión inválida.")
        return {"idToken": r["id_token"], "refreshToken": r["refresh_token"]}

    def datos_cuenta(self, id_token):
        usuarios = self._llamar("lookup", {"idToken": id_token}).get("users")
        if not usuarios:
            raise AuthError("Firebase no devolvió los datos de la cuenta.")
        return usuarios[0]

    def poner_nombre(self, id_token, nombre):
        self._llamar("update", {"idToken": id_token, "displayName": nombre})

    def enviar_verificacion(self, id_token):
        self._llamar("sendOobCode", {"requestType": "VERIFY_EMAIL", "idToken": id_token})

    def enviar_recuperacion(self, correo):
        self._llamar("sendOobCode", {"requestType": "PASSWORD_RESET", "email": correo})


class ClienteServidor:
    """Adaptador del servidor del juego (implementa ApiPerfiles)."""

    def __init__(self, url: str | None = None):
        self.url = (url or os.getenv("BATTLE_ARENA_SERVER", "http://127.0.0.1:8000")).rstrip("/")

    def _llamar(self, metodo, ruta, token=None, cuerpo=None, **params) -> dict:
        url = self.url + ruta + (f"?{urlencode(params)}" if params else "")
        cabeceras = {"Accept": "application/json"}
        if token:
            cabeceras["Authorization"] = f"Bearer {token}"
        datos = None
        if cuerpo is not None:
            datos = json.dumps(cuerpo).encode("utf-8")
            cabeceras["Content-Type"] = "application/json"
        try:
            return _enviar(Request(url, datos, cabeceras, method=metodo), timeout=10)
        except _ErrorHttp as error:
            raise AuthError(str(error.cuerpo.get("error", "El servidor rechazó la solicitud."))) from error

    @staticmethod
    def _perfil(respuesta: dict) -> dict:
        perfil = respuesta.get("user")
        if not isinstance(perfil, dict):
            raise AuthError("El servidor devolvió un perfil inválido.")
        return perfil

    def nombre_disponible(self, nombre):
        return bool(self._llamar("GET", "/api/disponible", nombre=nombre).get("disponible"))

    def correo_de(self, nombre):
        return self._llamar("GET", "/api/correo", nombre=nombre).get("correo")
    def guardar_perfil(self, token, nombre):
        return self._perfil(self._llamar("POST", "/api/profile", token, {"name": nombre}))
    def obtener_perfil(self, token):
        return self._perfil(self._llamar("GET", "/api/profile", token))

    # CAMBIO ONLINE: persistencia compartida de avatares y sala en el servidor Docker.
    def obtener_avatar(self, token, id_usuario):
        return self._llamar("GET", "/api/game/avatar", token, id=int(id_usuario)).get("avatar")

    def guardar_avatar(self, token, eleccion):
        return self._llamar("PUT", "/api/game/avatar", token, eleccion)

    def obtener_partida(self, token):
        return self._llamar("GET", "/api/game/state", token)

    def unirse_partida(self, token):
        return self._llamar("POST", "/api/game/join", token)

    def salir_partida(self, token):
        return self._llamar("POST", "/api/game/leave", token)

    def iniciar_partida(self, token):
        return self._llamar("POST", "/api/game/start", token)

    def mover_jugador(self, token, direccion):
        return self._llamar("POST", "/api/game/move", token, {"direction": direccion})

    def guardar_configuracion_partida(self, token, configuracion):
        return self._llamar("PUT", "/api/game/config", token, configuracion)

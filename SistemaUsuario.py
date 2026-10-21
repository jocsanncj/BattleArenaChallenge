"""Conecta la interfaz Pygame con Firebase Auth y el perfil del servidor."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


load_dotenv()

URL_SERVIDOR = os.getenv(
    "BATTLE_ARENA_SERVER", "http://127.0.0.1:8000"
).rstrip("/")
FIREBASE_AUTH_URL = "https://identitytoolkit.googleapis.com/v1"
FIREBASE_TOKEN_URL = "https://securetoken.googleapis.com/v1/token"
_id_token: str | None = None
_refresh_token: str | None = None
_email_actual: str | None = None
_nombre_actual: str | None = None


## @brief Excepción para correo o contraseña rechazados por Firebase.
class CredencialesInvalidas(RuntimeError):
    """Indica que Firebase rechazó el correo o la contraseña."""


## @brief Excepción para una cuenta que todavía no confirmó su correo.
class CorreoPendiente(RuntimeError):
    """Indica que la cuenta debe verificar su dirección de correo."""


## @brief Excepción con el código devuelto por la API REST de Firebase.
class FirebaseAPIError(RuntimeError):
    """Incluye el código de error devuelto por Firebase Auth."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(_mensaje_firebase(code))


## @brief Convierte un código de Firebase Auth en un mensaje para la interfaz.
## @param code Código de error devuelto en la respuesta SQLite.
## @return Mensaje legible en español.
def _mensaje_firebase(code: str) -> str:
    """Traduce códigos comunes de Firebase a mensajes para la interfaz."""
    messages = {
        "EMAIL_EXISTS": "Ese correo ya tiene una cuenta de Firebase.",
        "INVALID_EMAIL": "La dirección de correo no es válida.",
        "WEAK_PASSWORD": "Firebase rechazó la contraseña por ser demasiado débil.",
        "EMAIL_NOT_FOUND": "No existe una cuenta con ese correo.",
        "INVALID_PASSWORD": "El correo o la contraseña son incorrectos.",
        "INVALID_LOGIN_CREDENTIALS": "El correo o la contraseña son incorrectos.",
        "USER_DISABLED": "Esta cuenta fue deshabilitada.",
        "TOO_MANY_ATTEMPTS_TRY_LATER": (
            "Firebase limitó temporalmente los intentos. Espera y vuelve a probar."
        ),
        "OPERATION_NOT_ALLOWED": (
            "Activa el proveedor Correo/contraseña en Firebase Authentication."
        ),
        "API_KEY_INVALID": (
            "Falta una API key web válida de Firebase en FIREBASE_API_KEY."
        ),
    }
    return messages.get(code, f"Firebase Auth rechazó la solicitud ({code}).")


## @brief Lee la API key web requerida para las llamadas de Firebase Auth.
## @return API key pública configurada en el entorno.
## @throws RuntimeError Si falta FIREBASE_API_KEY.
def _api_key() -> str:
    """Obtiene la API key web pública configurada para el proyecto Firebase."""
    key = os.getenv("FIREBASE_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Configura la API key web de Firebase en FIREBASE_API_KEY dentro de .env."
        )
    return key


## @brief Decodifica una respuesta HTTP y comprueba que sea un objeto JSON.
## @param response Respuesta HTTP que contiene el JSON del servicio.
## @return Diccionario con los datos recibidos.
## @throws RuntimeError Si el JSON está dañado o tiene otro tipo superior.
def _decode_response(response) -> dict[str, object]:
    """Decodifica y valida un objeto JSON devuelto por un servicio."""
    try:
        result = json.loads(response.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("El servicio respondió con datos inválidos.") from error
    if not isinstance(result, dict):
        raise RuntimeError("El servicio respondió con un formato inválido.")
    return result


## @brief Envía JSON a un endpoint REST de Firebase Authentication.
## @param endpoint Nombre de la operación REST de Firebase.
## @param payload Datos JSON requeridos por esa operación.
## @return Respuesta JSON de Firebase Auth.
## @throws RuntimeError Si hay un error de red o Firebase rechaza la solicitud.
def _firebase_request(
    endpoint: str, payload: dict[str, object]
) -> dict[str, object]:
    """Envía una solicitud JSON a la API REST oficial de Firebase Auth."""
    request = Request(
        f"{FIREBASE_AUTH_URL}/{endpoint}?key={_api_key()}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            return _decode_response(response)
    except HTTPError as error:
        try:
            body = _decode_response(error)
        except RuntimeError:
            raise RuntimeError(
                f"Firebase Auth respondió con el error HTTP {error.code}."
            ) from error
        detail = body.get("error")
        code = detail.get("message") if isinstance(detail, dict) else None
        if not isinstance(code, str):
            code = f"HTTP_{error.code}"
        if code in ("INVALID_PASSWORD", "INVALID_LOGIN_CREDENTIALS", "EMAIL_NOT_FOUND"):
            raise CredencialesInvalidas(_mensaje_firebase(code)) from error
        raise FirebaseAPIError(code) from error
    except (URLError, TimeoutError, OSError) as error:
        raise RuntimeError(
            f"No se pudo conectar con Firebase Auth: {error}"
        ) from error


## @brief Consulta o actualiza el perfil en el servidor de juego.
## @param method Método HTTP para solicitar el perfil.
## @param payload Datos de perfil que se enviarán, si corresponde.
## @return Objeto JSON devuelto por el servidor.
## @throws RuntimeError Si falta una sesión o falla la solicitud.
def _profile_request(
    method: str, payload: dict[str, object] | None = None
) -> dict[str, object]:
    """Solicita o registra el perfil de juego en el servidor propio."""
    token = _refresh_id_token()
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(
        f"{URL_SERVIDOR}/api/profile",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            return _decode_response(response)
    except HTTPError as error:
        try:
            detail = _decode_response(error)
            message = detail.get("error", f"Error HTTP {error.code}.")
        except RuntimeError:
            message = f"Error HTTP {error.code} al consultar el perfil."
        raise RuntimeError(str(message)) from error
    except (URLError, TimeoutError, OSError) as error:
        raise RuntimeError(
            f"No se pudo conectar con el servidor {URL_SERVIDOR}: {error}"
        ) from error


## @brief Guarda en memoria los tokens temporales recibidos desde Firebase.
## @param response Respuesta de registro, actualización o login.
## @return None.
## @throws RuntimeError Si la respuesta no contiene todos los campos de sesión.
def _guardar_sesion(response: dict[str, object]) -> None:
    """Conserva localmente los tokens temporales y el correo de Firebase."""
    global _id_token, _refresh_token, _email_actual
    id_token = response.get("idToken")
    refresh_token = response.get("refreshToken")
    email = response.get("email")
    if not all(isinstance(value, str) and value for value in (
        id_token,
        refresh_token,
        email,
    )):
        raise RuntimeError("Firebase no devolvió una sesión completa.")
    _id_token = id_token
    _refresh_token = refresh_token
    _email_actual = email


## @brief Renueva el token de Firebase antes de llamar al servidor de perfiles.
## @return ID token vigente para la sesión actual.
## @throws RuntimeError Si la sesión no puede renovarse.
def _refresh_id_token() -> str:
    """Renueva el token de acceso con el refresh token efímero de Firebase."""
    global _id_token, _refresh_token
    if _refresh_token is None:
        raise RuntimeError("Inicia sesión para consultar el perfil.")
    form = urlencode(
        {"grant_type": "refresh_token", "refresh_token": _refresh_token}
    ).encode("utf-8")
    request = Request(
        f"{FIREBASE_TOKEN_URL}?key={_api_key()}",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = _decode_response(response)
    except HTTPError as error:
        raise RuntimeError(
            "Firebase no pudo renovar la sesión. Inicia sesión de nuevo."
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise RuntimeError(f"No se pudo renovar la sesión: {error}") from error

    token = result.get("id_token")
    refresh_token = result.get("refresh_token")
    if not isinstance(token, str) or not isinstance(refresh_token, str):
        raise RuntimeError("Firebase devolvió una respuesta de sesión inválida.")
    _id_token = token
    _refresh_token = refresh_token
    return token


## @brief Consulta correo verificado y nombre público de la cuenta Firebase.
## @param id_token Token temporal que identifica la cuenta.
## @return Datos del usuario devueltos por accounts:lookup.
def _firebase_user(id_token: str) -> dict[str, object]:
    """Obtiene el estado de verificación y el nombre público de Firebase."""
    response = _firebase_request("accounts:lookup", {"idToken": id_token})
    users = response.get("users")
    if not isinstance(users, list) or not users or not isinstance(users[0], dict):
        raise RuntimeError("Firebase no devolvió los datos de la cuenta.")
    return users[0]


## @brief Sincroniza el nombre del usuario con el perfil JSON del juego.
## @param name Nombre público leído de la cuenta Firebase.
## @return Perfil de juego devuelto por el servidor.
def _sync_profile(name: str) -> dict[str, object]:
    """Registra o actualiza los datos de juego usando el token de Firebase."""
    global _nombre_actual
    response = _profile_request("POST", {"name": name})
    user = response.get("user")
    if not isinstance(user, dict):
        raise RuntimeError("El servidor no devolvió un perfil válido.")
    profile_name = user.get("name")
    if not isinstance(profile_name, str):
        raise RuntimeError("El servidor devolvió un nombre de perfil inválido.")
    _nombre_actual = profile_name
    return user


## @brief Registra una cuenta en Firebase y solicita su correo de verificación.
## @param nombre Nombre público del jugador.
## @param password Contraseña elegida para la cuenta Firebase.
## @param confirmacion Repetición de la contraseña.
## @param correo Correo que Firebase verificará.
## @return Estado del registro y del envío del correo.
## @throws ValueError Si el nombre o las contraseñas no son válidos.
def registrar_usuario(
    nombre: str,
    password: str,
    confirmacion: str,
    correo: str,
) -> dict[str, object]:
    """Crea la cuenta en Firebase, envía verificación y crea su perfil de juego."""
    name = nombre.strip()
    email = correo.strip()
    if not name or len(name) > 40:
        raise ValueError("El nombre debe tener entre 1 y 40 caracteres.")
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    if password != confirmacion:
        raise ValueError("Las contraseñas no coinciden.")

    if not _publico("/api/disponible", nombre=name)["disponible"]:
        raise ValueError("Ese nombre de usuario ya está en uso.")

    response = _firebase_request(
        "accounts:signUp",
        {"email": email, "password": password, "returnSecureToken": True},
    )
    _guardar_sesion(response)

    _firebase_request(
        "accounts:update",
        {
            "idToken": _id_token or "",
            "displayName": name,
            "returnSecureToken": True,
        },
    )
    _firebase_request(
        "accounts:sendOobCode",
        {"requestType": "VERIFY_EMAIL", "idToken": _id_token or ""},
    )
    _sync_profile(name)
    return {"verification_required": True, "verification_sent": True}


## @brief Inicia sesión con Firebase y sincroniza el perfil si el correo se verificó.
## @param identificador Correo electrónico de la cuenta.
## @param password Contraseña de Firebase.
## @return Perfil autenticado o None si Firebase rechaza las credenciales.
## @throws CorreoPendiente Si la cuenta aún no confirmó su correo.
def autenticar_usuario(identificador: str, password: str) -> dict[str, object] | None:
    """Inicia sesión por correo y devuelve el perfil si el correo está verificado."""
    global _nombre_actual
    email = _resolver_correo(identificador)
    if email is None:
        return None
    if "@" not in email:
        email = _publico("/api/correo", nombre=email).get("correo")
        if not email:
            return None
    try:
        response = _firebase_request(
            "accounts:signInWithPassword",
            {"email": email, "password": password, "returnSecureToken": True},
        )
    except CredencialesInvalidas:
        return None

    _guardar_sesion(response)
    firebase_user = _firebase_user(_id_token or "")
    if firebase_user.get("emailVerified") is not True:
        raise CorreoPendiente(
            "Tu correo todavía no está verificado. Revisa tu bandeja de entrada."
        )

    display_name = firebase_user.get("displayName")
    name = display_name.strip() if isinstance(display_name, str) else ""
    if not name:
        name = email.partition("@")[0]
    profile = _sync_profile(name)
    _nombre_actual = str(profile["name"])
    return profile


## @brief Obtiene del servidor el perfil JSON vinculado a la sesión Firebase.
## @return Diccionario con nombre, correo, récord y estadísticas.
def obtener_usuario() -> dict[str, object]:
    """Consulta en el servidor el perfil vinculado a la sesión de Firebase."""
    response = _profile_request("GET")
    user = response.get("user")
    if not isinstance(user, dict):
        raise RuntimeError("El servidor devolvió un perfil inválido.")
    return user


## @brief Solicita a Firebase el reenvío del correo de verificación.
## @param identificador Correo de la cuenta activa.
## @return None.
def reenviar_verificacion(identificador: str) -> None:
    """Solicita a Firebase que reenvíe el correo de verificación actual."""
    if _id_token is None or _email_actual is None:
        raise RuntimeError("Inicia sesión con esa cuenta para reenviar la verificación.")
    if identificador.strip().casefold() != _email_actual.casefold():
        raise ValueError("El correo no coincide con la cuenta activa.")
    token = _refresh_id_token()
    _firebase_request(
        "accounts:sendOobCode",
        {"requestType": "VERIFY_EMAIL", "idToken": token},
    )


## @brief Solicita a Firebase un enlace de restablecimiento de contraseña.
## @param identificador Correo que se desea recuperar.
## @return None.
def solicitar_recuperacion(identificador: str) -> None:
    """Solicita a Firebase un correo para restablecer la contraseña."""
    email = _resolver_correo(identificador)
    if not email: 
        return
    if not email:
        raise ValueError("Escribe tu correo electrónico.")
    try:
        _firebase_request(
            "accounts:sendOobCode",
            {"requestType": "PASSWORD_RESET", "email": email},
        )
    except FirebaseAPIError as error:
        if error.code != "EMAIL_NOT_FOUND":
            raise


## @brief Elimina los tokens y datos de usuario de la memoria del cliente.
## @return None.
def cerrar_sesion() -> None:
    """Elimina de memoria los tokens y datos de la sesión actual."""
    global _id_token, _refresh_token, _email_actual, _nombre_actual
    _id_token = None
    _refresh_token = None
    _email_actual = None
    _nombre_actual = None


## @brief Devuelve el nombre de la cuenta actualmente autenticada.
## @return Nombre público o None si no hay perfil sincronizado.
def usuario_actual() -> str | None:
    """Devuelve el nombre asociado a la sesión, si ya se cargó el perfil."""
    return _nombre_actual

def _publico(ruta, **params):
    with urlopen(f"{URL_SERVIDOR}{ruta}?{urlencode(params)}", timeout=10) as r:
        return _decode_response(r)

def _resolver_correo(identificador: str) -> str | None:
    """Acepta usuario o correo y devuelve el correo (None si el usuario no existe)."""
    identificador = identificador.strip()
    if "@" in identificador:
        return identificador
    return _publico("/api/correo", nombre=identificador).get("correo")
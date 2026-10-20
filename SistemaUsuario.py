import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


URL_SERVIDOR = os.getenv(
    "BATTLE_ARENA_SERVER", "http://127.0.0.1:8000"
).rstrip("/")
_token: str | None = None
_usuario_actual: str | None = None


class CredencialesInvalidas(RuntimeError):
    pass


class CorreoPendiente(RuntimeError):
    pass


def _solicitud(
    ruta: str,
    contenido: dict[str, object] | None = None,
    requiere_sesion: bool = False,
) -> dict[str, object]:
    datos = None
    headers = {"Accept": "application/json"}
    if contenido is not None:
        datos = json.dumps(contenido).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if requiere_sesion:
        if _token is None:
            raise RuntimeError("Inicia sesión para consultar esta información.")
        headers["Authorization"] = f"Bearer {_token}"

    solicitud = Request(
        f"{URL_SERVIDOR}{ruta}",
        data=datos,
        headers=headers,
        method="POST" if datos is not None else "GET",
    )
    try:
        with urlopen(solicitud, timeout=10) as respuesta:
            resultado = json.loads(respuesta.read().decode("utf-8"))
    except HTTPError as error:
        try:
            detalle = json.loads(error.read().decode("utf-8"))
            mensaje = detalle.get("error", f"Error HTTP {error.code}.")
            if ruta == "/api/login" and error.code == 403:
                raise CorreoPendiente(str(mensaje)) from error
            if ruta == "/api/login" and error.code == 401:
                raise CredencialesInvalidas(str(mensaje)) from error
        except (UnicodeDecodeError, json.JSONDecodeError):
            mensaje = f"Error HTTP {error.code} al comunicarse con el servidor."
        raise RuntimeError(str(mensaje)) from error
    except (URLError, TimeoutError, OSError) as error:
        raise RuntimeError(
            f"No se pudo conectar con el servidor {URL_SERVIDOR}: {error}"
        ) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("El servidor respondió con datos inválidos.") from error

    if not isinstance(resultado, dict):
        raise RuntimeError("El servidor respondió con un formato inválido.")
    return resultado


def _guardar_sesion(respuesta: dict[str, object]) -> None:
    global _token, _usuario_actual
    token = respuesta.get("token")
    usuario = respuesta.get("user")
    if not isinstance(token, str) or not isinstance(usuario, dict):
        raise RuntimeError("El servidor no devolvió una sesión válida.")
    nombre = usuario.get("name")
    if not isinstance(nombre, str):
        raise RuntimeError("El servidor devolvió un perfil inválido.")
    _token = token
    _usuario_actual = nombre


def registrar_usuario(
    nombre: str,
    password: str,
    confirmacion: str,
    correo: str,
) -> dict[str, object]:
    return _solicitud(
        "/api/register",
        {
            "name": nombre,
            "email": correo,
            "password": password,
            "password_confirmation": confirmacion,
        },
    )


def autenticar_usuario(
    identificador: str, password: str
) -> dict[str, object] | None:
    try:
        respuesta = _solicitud(
            "/api/login",
            {"identifier": identificador, "password": password},
        )
    except CredencialesInvalidas:
        return None
    _guardar_sesion(respuesta)
    usuario = respuesta.get("user")
    if not isinstance(usuario, dict):
        raise RuntimeError("El servidor devolvió un perfil inválido.")
    return usuario


def obtener_usuario() -> dict[str, object]:
    respuesta = _solicitud("/api/profile", requiere_sesion=True)
    usuario = respuesta.get("user")
    if not isinstance(usuario, dict):
        raise RuntimeError("El servidor devolvió un perfil inválido.")
    return usuario


def reenviar_verificacion(identificador: str) -> None:
    _solicitud(
        "/api/email/resend",
        {"identifier": identificador},
    )


def solicitar_recuperacion(identificador: str) -> None:
    _solicitud(
        "/api/password/recovery",
        {"identifier": identificador},
    )


def cerrar_sesion() -> None:
    global _token, _usuario_actual
    _token = None
    _usuario_actual = None


def usuario_actual() -> str | None:
    return _usuario_actual

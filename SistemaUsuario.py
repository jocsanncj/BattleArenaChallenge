import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


## @brief Dirección HTTP del servidor configurada al importar este módulo.
URL_SERVIDOR = os.getenv(
    "BATTLE_ARENA_SERVER", "http://127.0.0.1:8000"
).rstrip("/")
## @brief Token privado de sesión utilizado por las solicitudes protegidas.
_token: str | None = None
## @brief Nombre del jugador autenticado en este proceso cliente.
_usuario_actual: str | None = None


class CredencialesInvalidas(RuntimeError):
    ## @brief Excepción para credenciales rechazadas por el servidor.
    pass


class CorreoPendiente(RuntimeError):
    ## @brief Excepción para una cuenta cuyo correo aún no se verificó.
    pass


## @brief Envía una solicitud HTTP JSON al servidor y valida su respuesta.
## @param ruta Ruta relativa del endpoint dentro de la API.
## @param contenido Objeto opcional que se serializa como JSON en la petición.
## @param requiere_sesion Indica si la llamada necesita el token local.
## @return Diccionario Python obtenido del JSON de respuesta.
## @throws RuntimeError Para fallos HTTP no traducidos, de conexión o formato.
def _solicitud(
    ruta: str,
    contenido: dict[str, object] | None = None,
    requiere_sesion: bool = False,
) -> dict[str, object]:
    ## @brief Construye los encabezados y el cuerpo JSON si se proporcionaron datos.
    datos = None
    headers = {"Accept": "application/json"}
    if contenido is not None:
        datos = json.dumps(contenido).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if requiere_sesion:
        if _token is None:
            raise RuntimeError("Inicia sesión para consultar esta información.")
        headers["Authorization"] = f"Bearer {_token}"

    ## @brief Crea el objeto HTTP con GET sin cuerpo o POST con JSON.
    solicitud = Request(
        f"{URL_SERVIDOR}{ruta}",
        data=datos,
        headers=headers,
        method="POST" if datos is not None else "GET",
    )
    ## @brief Envía la petición con límite de diez segundos y decodifica el JSON.
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

    ## @brief Asegura que las funciones llamadoras reciban siempre un objeto JSON.
    if not isinstance(resultado, dict):
        raise RuntimeError("El servidor respondió con un formato inválido.")
    return resultado


## @brief Guarda el token y el nombre después de recibir un login exitoso.
## @param respuesta Respuesta JSON de inicio de sesión con token y perfil.
## @return None.
## @throws RuntimeError Si los campos obligatorios no tienen el tipo esperado.
def _guardar_sesion(respuesta: dict[str, object]) -> None:
    global _token, _usuario_actual
    ## @brief Extrae las dos partes de la sesión devueltas por la API.
    token = respuesta.get("token")
    usuario = respuesta.get("user")
    if not isinstance(token, str) or not isinstance(usuario, dict):
        raise RuntimeError("El servidor no devolvió una sesión válida.")
    ## @brief Comprueba que el perfil incluye un nombre de jugador válido.
    nombre = usuario.get("name")
    if not isinstance(nombre, str):
        raise RuntimeError("El servidor devolvió un perfil inválido.")
    _token = token
    _usuario_actual = nombre


## @brief Solicita la creación de una cuenta y su correo de verificación.
## @param nombre Nombre elegido para la cuenta.
## @param password Contraseña de la cuenta.
## @param confirmacion Repetición de la contraseña.
## @param correo Dirección de correo a verificar.
## @return Respuesta JSON del servidor con el estado del registro.
def registrar_usuario(
    nombre: str,
    password: str,
    confirmacion: str,
    correo: str,
) -> dict[str, object]:
    ## @brief Adapta los campos de la interfaz al contrato JSON del backend.
    return _solicitud(
        "/api/register",
        {
            "name": nombre,
            "email": correo,
            "password": password,
            "password_confirmation": confirmacion,
        },
    )


## @brief Inicia sesión con nombre/correo y almacena el token recibido.
## @param identificador Nombre de usuario o dirección de correo.
## @param password Contraseña proporcionada.
## @return Perfil autenticado, o None cuando las credenciales son incorrectas.
## @throws CorreoPendiente Si la contraseña coincide pero falta verificar correo.
def autenticar_usuario(
    identificador: str, password: str
) -> dict[str, object] | None:
    ## @brief Envía las credenciales a la API; traduce el rechazo en None.
    try:
        respuesta = _solicitud(
            "/api/login",
            {"identifier": identificador, "password": password},
        )
    except CredencialesInvalidas:
        return None
    ## @brief Conserva el token solo después de una respuesta de login válida.
    _guardar_sesion(respuesta)
    usuario = respuesta.get("user")
    if not isinstance(usuario, dict):
        raise RuntimeError("El servidor devolvió un perfil inválido.")
    return usuario


## @brief Solicita el perfil completo asociado a la sesión local.
## @return Diccionario con los datos del jugador.
## @throws RuntimeError Si no hay sesión o el servidor devuelve error.
def obtener_usuario() -> dict[str, object]:
    ## @brief La opción requiere_sesion agrega el encabezado de autorización.
    respuesta = _solicitud("/api/profile", requiere_sesion=True)
    usuario = respuesta.get("user")
    if not isinstance(usuario, dict):
        raise RuntimeError("El servidor devolvió un perfil inválido.")
    return usuario


## @brief Solicita el reenvío del enlace para activar una cuenta.
## @param identificador Nombre o correo de la cuenta.
## @return None.
def reenviar_verificacion(identificador: str) -> None:
    ## @brief Pasa el identificador al endpoint de reenvío de correo.
    _solicitud(
        "/api/email/resend",
        {"identifier": identificador},
    )


## @brief Solicita al servidor un enlace para establecer otra contraseña.
## @param identificador Nombre o correo de la cuenta.
## @return None.
def solicitar_recuperacion(identificador: str) -> None:
    ## @brief El servidor responde de forma genérica para esta solicitud.
    _solicitud(
        "/api/password/recovery",
        {"identifier": identificador},
    )


## @brief Elimina el token y el nombre guardados en el cliente.
## @return None.
def cerrar_sesion() -> None:
    global _token, _usuario_actual
    ## @brief Borra la credencial usada por las llamadas que requieren sesión.
    _token = None
    _usuario_actual = None


## @brief Devuelve el nombre guardado para la sesión actual.
## @return Nombre del usuario o None cuando no hay sesión.
def usuario_actual() -> str | None:
    ## @brief No expone el token privado a las escenas.
    return _usuario_actual

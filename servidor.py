import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend.repository import (
    DuplicateEmail,
    DuplicateUsername,
    RepositoryError,
    SQLiteRepository,
    UserNotFound,
)
from backend.services import (
    AccountService,
    EmailNotVerified,
    EmailService,
    InvalidCredentials,
    InvalidEmailLink,
    InvalidInput,
)


# Define la duración de las sesiones guardadas temporalmente en memoria.
SESSION_LIFETIME = timedelta(days=7)
# Limita el tamaño máximo de los cuerpos recibidos por la API.
MAX_REQUEST_BYTES = 1_048_576


## @brief Contenedor de dependencias y sesiones compartido por el servidor.
class Application:
    ## @brief Construye y conecta persistencia, cuentas, correo y sesiones.
    def __init__(self):
        # Lee la carpeta persistente, usando una carpeta data junto al servidor.
        data_directory = Path(os.getenv("DATA_DIR", Path(__file__).parent / "data"))
        # Permite importar usuarios del JSON antiguo salvo que se configure otra ruta.
        legacy_file_value = os.getenv(
            "LEGACY_USERS_FILE", str(Path(__file__).parent / "DatosUser.json")
        )
        # Convierte la ruta opcional a Path, o desactiva la migración si está vacía.
        legacy_file = Path(legacy_file_value) if legacy_file_value else None
        # Crea el repositorio y prepara el esquema antes de aceptar solicitudes.
        self.repository = SQLiteRepository(data_directory, legacy_file)
        self.repository.initialize()
        # Une las reglas de cuenta con el repositorio y el servicio SMTP.
        self.accounts = AccountService(self.repository, EmailService())
        # Mantiene sesiones en memoria: no sobreviven a reiniciar el proceso.
        self.sessions: dict[str, tuple[str, datetime]] = {}
        # Protege el diccionario frente a solicitudes concurrentes del servidor.
        self.session_lock = threading.Lock()

    ## @brief Crea un token aleatorio de sesión con fecha límite.
    ## @param name Nombre del usuario autenticado.
    ## @return Token que el cliente presentará en las rutas privadas.
    def create_session(self, name: str) -> str:
        # Crea un secreto impredecible para identificar la sesión.
        token = secrets.token_urlsafe(32)
        # Calcula la expiración a partir de la hora UTC actual.
        expires_at = datetime.now(timezone.utc) + SESSION_LIFETIME
        # Inserta el par usuario/expiración bajo bloqueo de concurrencia.
        with self.session_lock:
            self.sessions[token] = (name, expires_at)
        return token

    ## @brief Valida un token de sesión y devuelve su usuario si sigue vigente.
    ## @param token Token recibido por el encabezado de autorización.
    ## @return Nombre de usuario o None si no existe o expiró.
    def session_user(self, token: str) -> str | None:
        # Lee y posiblemente modifica sesiones bajo el mismo bloqueo.
        with self.session_lock:
            session = self.sessions.get(token)
            # Un token desconocido no representa una sesión válida.
            if session is None:
                return None
            # Separa la identidad de la fecha de expiración.
            name, expires_at = session
            # Elimina sesiones vencidas para no conservarlas indefinidamente.
            if expires_at <= datetime.now(timezone.utc):
                del self.sessions[token]
                return None
            return name


## @brief Traduce solicitudes HTTP en operaciones de cuenta y perfil.
class APIHandler(BaseHTTPRequestHandler):
    ## @brief Identifica esta implementación en los encabezados HTTP.
    server_version = "BattleArenaAPI/1.0"

    @property
    ## @brief Devuelve la aplicación que pertenece al servidor HTTP.
    ## @return Instancia Application compartida por las solicitudes.
    def app(self) -> Application:
        return self.server.app

    ## @brief Registra la solicitud sin conservar parámetros que incluyan tokens.
    ## @param format Plantilla del mensaje proporcionada por BaseHTTPRequestHandler.
    ## @param args Valores usados para completar esa plantilla.
    ## @return None.
    def log_message(self, format, *args):
        # Formatea el mensaje HTTP original antes de sanitizar la ruta.
        message = format % args
        # Extrae solo la ruta y descarta query strings con tokens secretos.
        safe_path = urlparse(self.path).path
        if self.path != safe_path:
            message = message.replace(self.path, safe_path)
        print(f"{self.address_string()} - {message}")

    ## @brief Envía una respuesta JSON con encabezados de no almacenamiento.
    ## @param status Código de estado HTTP.
    ## @param content Diccionario que se serializa como JSON UTF-8.
    ## @return None.
    def _respond(self, status: int, content: dict[str, object]) -> None:
        # Serializa el contenido preservando caracteres españoles.
        body = json.dumps(content, ensure_ascii=False).encode("utf-8")
        # Escribe el estado y los encabezados necesarios para la respuesta.
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        # Escribe el JSON en el socket HTTP.
        self.wfile.write(body)

    ## @brief Envía una página HTML con encabezados básicos de seguridad.
    ## @param status Código HTTP que corresponde al resultado de la página.
    ## @param content HTML ya construido por los helpers del servidor.
    ## @return None.
    def _respond_html(self, status: int, content: str) -> None:
        # Convierte el HTML a bytes UTF-8 para transmitirlo por HTTP.
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        # Envía el contenido HTML al navegador del usuario.
        self.wfile.write(body)

    ## @brief Lee el cuerpo HTTP respetando el límite máximo configurado.
    ## @return Bytes recibidos desde el cliente.
    ## @throws InvalidInput Si el tamaño es inválido, vacío o demasiado grande.
    def _read_body(self) -> bytes:
        # Convierte Content-Length a entero para validar cuánto se leerá.
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise InvalidInput("Content-Length no es válido.") from error
        # Rechaza solicitudes sin cuerpo y cargas excesivamente grandes.
        if length < 1 or length > MAX_REQUEST_BYTES:
            raise InvalidInput(
                "La solicitud está vacía o excede el tamaño permitido."
            )
        return self.rfile.read(length)

    ## @brief Lee y valida un objeto JSON recibido en el cuerpo HTTP.
    ## @return Diccionario Python con los campos de la solicitud.
    ## @throws InvalidInput Si el JSON está mal formado o no es un objeto.
    def _read_json(self) -> dict[str, object]:
        # Convierte los bytes del cuerpo y valida el tipo superior.
        try:
            data = json.loads(self._read_body())
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidInput("La solicitud no contiene JSON válido.") from error
        if not isinstance(data, dict):
            raise InvalidInput("El cuerpo debe ser un objeto JSON.")
        return data

    ## @brief Lee campos de formulario URL-encoded, usado por enlaces web.
    ## @return Diccionario de nombre de campo a su último valor.
    ## @throws InvalidInput Si el formulario no se puede decodificar.
    def _read_form(self) -> dict[str, str]:
        # Decodifica pares de formulario, como el token enviado desde el navegador.
        try:
            values = parse_qs(self._read_body().decode("utf-8"), strict_parsing=True)
        except (UnicodeDecodeError, ValueError) as error:
            raise InvalidInput("El formulario recibido no es válido.") from error
        return {key: value[-1] for key, value in values.items() if value}

    ## @brief Identifica al usuario desde el token HTTP de autorización.
    ## @return Nombre de usuario si la sesión es válida.
    ## @throws PermissionError Si falta el token o la sesión venció.
    def _bearer_user(self) -> str:
        # Separa el esquema Bearer del secreto recibido en el encabezado.
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        name = (
            self.app.session_user(token)
            if scheme.casefold() == "bearer" and token
            else None
        )
        # Exige una sesión válida antes de devolver un perfil protegido.
        if name is None:
            raise PermissionError("Inicia sesión para consultar el perfil.")
        return name

    ## @brief Enruta consultas de salud, perfil y páginas de enlace.
    ## @return None.
    def do_GET(self) -> None:
        # Separa la ruta de la query string para enrutar sin divulgar tokens.
        request = urlparse(self.path)
        try:
            # La ruta health comprueba disponibilidad sin requerir sesión.
            if request.path == "/health":
                self._respond(200, {"status": "ok"})
            # El perfil privado requiere que el token identifique una sesión.
            elif request.path == "/api/profile":
                name = self._bearer_user()
                self._respond(
                    200, {"user": self.app.accounts.get_profile(name).to_dict()}
                )
            # Las páginas web extraen el token de la query y renderizan el formulario.
            elif request.path == "/verify-email":
                token = parse_qs(request.query).get("token", [""])[0]
                self._show_email_verification(token)
            elif request.path == "/reset-password":
                token = parse_qs(request.query).get("token", [""])[0]
                self._show_password_form(token)
            else:
                self._respond(404, {"error": "Ruta no encontrada."})
        # Traduce problemas de autorización o persistencia a estados HTTP.
        except PermissionError as error:
            self._respond(401, {"error": str(error)})
        except RepositoryError as error:
            print(f"Error GET {request.path}: {type(error).__name__}: {error}")
            self._respond(500, {"error": str(error)})

    ## @brief Enruta formularios web y operaciones JSON de cuenta.
    ## @return None.
    def do_POST(self) -> None:
        # Analiza la ruta sin incluir los parámetros en el registro.
        request = urlparse(self.path)
        try:
            # Los formularios del navegador usan formato URL-encoded.
            if request.path in ("/verify-email", "/reset-password"):
                form = self._read_form()
                if request.path == "/verify-email":
                    self._confirm_email(form.get("token", ""))
                else:
                    self._save_new_password(form)
                return

            # Los endpoints de API reciben un objeto JSON.
            data = self._read_json()
            if request.path == "/api/register":
                self._register(data)
            elif request.path == "/api/login":
                self._login(data)
            elif request.path == "/api/email/resend":
                self._resend_verification(data)
            elif request.path == "/api/password/recovery":
                self._request_password_recovery(data)
            else:
                self._respond(404, {"error": "Ruta no encontrada."})
        # Convierte errores de dominio a respuestas HTTP explícitas.
        except EmailNotVerified as error:
            self._respond(403, {"error": str(error), "email_unverified": True})
        except InvalidCredentials as error:
            self._respond(401, {"error": str(error)})
        except PermissionError as error:
            self._respond(401, {"error": str(error)})
        except (InvalidInput, InvalidEmailLink) as error:
            self._respond(400, {"error": str(error)})
        except DuplicateUsername as error:
            self._respond(409, {"error": str(error), "field": "name"})
        except DuplicateEmail as error:
            self._respond(409, {"error": str(error), "field": "email"})
        except UserNotFound as error:
            self._respond(404, {"error": str(error)})
        except RepositoryError as error:
            print(f"Error POST {request.path}: {type(error).__name__}: {error}")
            self._respond(500, {"error": str(error)})
        except RuntimeError as error:
            self._respond(503, {"error": str(error)})

    ## @brief Valida los campos JSON y registra la cuenta en la aplicación.
    ## @param data Objeto recibido en el cuerpo JSON.
    ## @return None; escribe directamente la respuesta HTTP.
    ## @throws InvalidInput Si faltan campos de texto obligatorios.
    def _register(self, data: dict[str, object]) -> None:
        # Extrae campos que forman parte del contrato de registro.
        name = data.get("name")
        email = data.get("email")
        password = data.get("password")
        confirmation = data.get("password_confirmation")
        # Evita que valores que no sean texto entren en las reglas de cuenta.
        if not all(
            isinstance(value, str)
            for value in (name, email, password, confirmation)
        ):
            raise InvalidInput("Nombre, correo y ambas contraseñas son obligatorios.")
        # Ejecuta las reglas de registro a través del servicio de aplicación.
        result = self.app.accounts.register(name, email, password, confirmation)
        self._respond(
            201,
            {
                "user": result.profile.to_dict(),
                "verification_required": True,
                "verification_sent": result.verification_sent,
                "email_error": result.email_error,
            },
        )

    ## @brief Autentica al usuario y devuelve un token de sesión.
    ## @param data Objeto JSON con identificador y contraseña.
    ## @return None; escribe la respuesta de login.
    def _login(self, data: dict[str, object]) -> None:
        # Recupera las credenciales solicitadas por el cliente.
        identifier = data.get("identifier")
        password = data.get("password")
        if not isinstance(identifier, str) or not isinstance(password, str):
            raise InvalidInput("Escribe tu usuario o correo y tu contraseña.")
        # Autentica antes de crear cualquier sesión.
        profile = self.app.accounts.authenticate(identifier, password)
        token = self.app.create_session(profile.name)
        self._respond(
            200, {"token": token, "user": profile.to_dict()}
        )

    ## @brief Solicita el reenvío del enlace de activación de correo.
    ## @param data Objeto JSON que contiene el identificador de cuenta.
    ## @return None; siempre devuelve un mensaje que no revela si existe la cuenta.
    def _resend_verification(self, data: dict[str, object]) -> None:
        # Valida que el identificador se pueda tratar como texto no vacío.
        identifier = data.get("identifier")
        if not isinstance(identifier, str) or not identifier.strip():
            raise InvalidInput("Escribe tu usuario o correo.")
        # Evita revelar la existencia de una cuenta inexistente a quien consulta.
        try:
            self.app.accounts.send_email_link(identifier, "verificacion")
        except UserNotFound:
            pass
        self._respond(
            200,
            {
                "message": (
                    "Si la cuenta existe y aún no está verificada, "
                    "se enviará un nuevo enlace."
                )
            },
        )

    ## @brief Pide un correo de recuperación para el identificador indicado.
    ## @param data Objeto JSON con nombre o correo.
    ## @return None; responde con un mensaje genérico.
    def _request_password_recovery(self, data: dict[str, object]) -> None:
        # Valida la entrada antes de iniciar el envío del correo.
        identifier = data.get("identifier")
        if not isinstance(identifier, str) or not identifier.strip():
            raise InvalidInput("Escribe tu usuario o correo.")
        self.app.accounts.send_email_link(identifier, "recuperacion")
        self._respond(
            200,
            {
                "message": (
                    "Si la cuenta existe, recibirás un enlace para recuperar "
                    "tu contraseña."
                )
            },
        )

    ## @brief Renderiza el formulario web para confirmar un enlace de correo.
    ## @param token Token recibido en la URL de verificación.
    ## @return None; envía una página HTML al navegador.
    def _show_email_verification(self, token: str) -> None:
        # Escapa el token para impedir que altere el atributo HTML del campo oculto.
        form = (
            '<form method="post" action="/verify-email">'
            f'<input type="hidden" name="token" value="{escape(token, quote=True)}">'
            '<button type="submit">Verificar correo</button></form>'
        )
        self._respond_html(
            200,
            _page(
                "Verificar correo",
                "Confirma que quieres verificar el correo de tu cuenta.",
                form,
            ),
        )

    ## @brief Consume el enlace y muestra el resultado de verificar el correo.
    ## @param token Token recibido mediante el formulario.
    ## @return None; escribe una página HTML de éxito o error.
    def _confirm_email(self, token: str) -> None:
        # El servicio valida vencimiento y uso único en el repositorio.
        try:
            self.app.accounts.verify_email(token)
        except InvalidEmailLink as error:
            self._respond_html(400, _page("Enlace inválido", str(error)))
            return
        self._respond_html(
            200,
            _page(
                "Correo verificado",
                "Tu cuenta está activa. Ya puedes volver al juego e iniciar sesión.",
            ),
        )

    ## @brief Muestra el formulario si el enlace de recuperación sigue vigente.
    ## @param token Token de recuperación extraído de la URL.
    ## @return None; envía una página HTML al navegador.
    def _show_password_form(self, token: str) -> None:
        # Evita mostrar el formulario si el enlace ya expiró o se consumió.
        if not self.app.accounts.recovery_link_is_valid(token):
            self._respond_html(
                400,
                _page(
                    "Enlace vencido",
                    "El enlace no es válido o ya venció. Solicita una recuperación nueva.",
                ),
            )
            return
        form = (
            '<form method="post" action="/reset-password">'
            f'<input type="hidden" name="token" value="{escape(token, quote=True)}">'
            '<label>Nueva contraseña'
            '<input type="password" name="password" minlength="8" maxlength="256" required>'
            '</label><label>Confirma la contraseña'
            '<input type="password" name="confirmation" minlength="8" maxlength="256" required>'
            '</label><button type="submit">Guardar nueva contraseña</button></form>'
        )
        self._respond_html(
            200,
            _page(
                "Recuperar contraseña",
                "Escribe y confirma una contraseña de al menos 8 caracteres.",
                form,
            ),
        )

    ## @brief Valida el formulario y guarda la contraseña nueva.
    ## @param form Campos enviados por el navegador.
    ## @return None; responde con HTML y un estado de éxito o error.
    def _save_new_password(self, form: dict[str, str]) -> None:
        # El servicio valida la longitud, coincidencia y vigencia del enlace.
        try:
            self.app.accounts.reset_password(
                form.get("token", ""),
                form.get("password", ""),
                form.get("confirmation", ""),
            )
        except (InvalidInput, InvalidEmailLink) as error:
            self._respond_html(
                400,
                _page(
                    "No se pudo cambiar la contraseña",
                    str(error),
                ),
            )
            return
        self._respond_html(
            200,
            _page(
                "Contraseña actualizada",
                "Ya puedes volver al juego e iniciar sesión con tu contraseña nueva.",
            ),
        )


## @brief Construye una página HTML común para verificación y recuperación.
## @param title Título escapado que se muestra en encabezado y pestaña.
## @param message Mensaje informativo que se muestra al usuario.
## @param content HTML adicional, como un formulario.
## @return Documento HTML completo como texto.
def _page(title: str, message: str, content: str = "") -> str:
    # Escapa texto externo para evitar que se interprete como marcado HTML.
    safe_title = escape(title)
    safe_message = escape(message)
    return (
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{safe_title}</title>"
        "<style>body{font:16px sans-serif;max-width:36rem;margin:4rem auto;"
        "padding:0 1rem;background:#18181b;color:#f4f4f5}form,label{display:grid;"
        "gap:.8rem}input,button{padding:.8rem;font:inherit}button{cursor:pointer}"
        "label{margin:1rem 0}</style></head><body>"
        f"<h1>{safe_title}</h1><p>{safe_message}</p>{content}"
        "</body></html>"
    )


## @brief Servidor HTTP multihilo que comparte una instancia de Application.
class BattleArenaHTTPServer(ThreadingHTTPServer):
    ## @brief Permite terminar los hilos de solicitudes sin bloquear el cierre.
    daemon_threads = True

    ## @brief Inicializa el servidor HTTP y asocia la aplicación compartida.
    ## @param address Tupla de host y puerto de escucha.
    ## @param handler Clase que procesa cada solicitud HTTP.
    ## @param app Instancia con servicios, repositorio y sesiones.
    def __init__(self, address, handler, app):
        # Hace accesible la aplicación desde cada APIHandler.
        self.app = app
        super().__init__(address, handler)


## @brief Crea la aplicación y el servidor HTTP listo para iniciar.
## @param host Dirección de red donde se aceptan conexiones.
## @param port Puerto TCP para la API.
## @return Servidor HTTP con la aplicación ya inicializada.
def create_server(host: str = "0.0.0.0", port: int = 8000):
    # Inicializa servicios y base de datos antes de crear el servidor.
    app = Application()
    return BattleArenaHTTPServer((host, port), APIHandler, app)


## @brief Punto de entrada que inicia la API cuando se ejecuta este archivo.
if __name__ == "__main__":
    # Construye el servidor usando host y puerto configurables por entorno.
    server = create_server(
        os.getenv("HOST", "0.0.0.0"), int(os.getenv("PORT", "8000"))
    )
    print(
        "Battle Arena API listening on "
        f"{server.server_address[0]}:{server.server_address[1]}"
    )
    # Atiende solicitudes hasta recibir una interrupción del proceso.
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server...")
    # Libera el socket de escucha tanto al salir normal como por interrupción.
    finally:
        server.server_close()

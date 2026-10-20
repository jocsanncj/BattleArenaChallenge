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


SESSION_LIFETIME = timedelta(days=7)
MAX_REQUEST_BYTES = 1_048_576


class Application:
    def __init__(self):
        data_directory = Path(os.getenv("DATA_DIR", Path(__file__).parent / "data"))
        legacy_file_value = os.getenv(
            "LEGACY_USERS_FILE", str(Path(__file__).parent / "DatosUser.json")
        )
        legacy_file = Path(legacy_file_value) if legacy_file_value else None
        self.repository = SQLiteRepository(data_directory, legacy_file)
        self.repository.initialize()
        self.accounts = AccountService(self.repository, EmailService())
        self.sessions: dict[str, tuple[str, datetime]] = {}
        self.session_lock = threading.Lock()

    def create_session(self, name: str) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + SESSION_LIFETIME
        with self.session_lock:
            self.sessions[token] = (name, expires_at)
        return token

    def session_user(self, token: str) -> str | None:
        with self.session_lock:
            session = self.sessions.get(token)
            if session is None:
                return None
            name, expires_at = session
            if expires_at <= datetime.now(timezone.utc):
                del self.sessions[token]
                return None
            return name


class APIHandler(BaseHTTPRequestHandler):
    server_version = "BattleArenaAPI/1.0"

    @property
    def app(self) -> Application:
        return self.server.app

    def log_message(self, format, *args):
        message = format % args
        safe_path = urlparse(self.path).path
        if self.path != safe_path:
            message = message.replace(self.path, safe_path)
        print(f"{self.address_string()} - {message}")

    def _respond(self, status: int, content: dict[str, object]) -> None:
        body = json.dumps(content, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _respond_html(self, status: int, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise InvalidInput("Content-Length no es válido.") from error
        if length < 1 or length > MAX_REQUEST_BYTES:
            raise InvalidInput(
                "La solicitud está vacía o excede el tamaño permitido."
            )
        return self.rfile.read(length)

    def _read_json(self) -> dict[str, object]:
        try:
            data = json.loads(self._read_body())
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidInput("La solicitud no contiene JSON válido.") from error
        if not isinstance(data, dict):
            raise InvalidInput("El cuerpo debe ser un objeto JSON.")
        return data

    def _read_form(self) -> dict[str, str]:
        try:
            values = parse_qs(self._read_body().decode("utf-8"), strict_parsing=True)
        except (UnicodeDecodeError, ValueError) as error:
            raise InvalidInput("El formulario recibido no es válido.") from error
        return {key: value[-1] for key, value in values.items() if value}

    def _bearer_user(self) -> str:
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        name = (
            self.app.session_user(token)
            if scheme.casefold() == "bearer" and token
            else None
        )
        if name is None:
            raise PermissionError("Inicia sesión para consultar el perfil.")
        return name

    def do_GET(self) -> None:
        request = urlparse(self.path)
        try:
            if request.path == "/health":
                self._respond(200, {"status": "ok"})
            elif request.path == "/api/profile":
                name = self._bearer_user()
                self._respond(
                    200, {"user": self.app.accounts.get_profile(name).to_dict()}
                )
            elif request.path == "/verify-email":
                token = parse_qs(request.query).get("token", [""])[0]
                self._show_email_verification(token)
            elif request.path == "/reset-password":
                token = parse_qs(request.query).get("token", [""])[0]
                self._show_password_form(token)
            else:
                self._respond(404, {"error": "Ruta no encontrada."})
        except PermissionError as error:
            self._respond(401, {"error": str(error)})
        except RepositoryError as error:
            print(f"Error GET {request.path}: {type(error).__name__}: {error}")
            self._respond(500, {"error": str(error)})

    def do_POST(self) -> None:
        request = urlparse(self.path)
        try:
            if request.path in ("/verify-email", "/reset-password"):
                form = self._read_form()
                if request.path == "/verify-email":
                    self._confirm_email(form.get("token", ""))
                else:
                    self._save_new_password(form)
                return

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

    def _register(self, data: dict[str, object]) -> None:
        name = data.get("name")
        email = data.get("email")
        password = data.get("password")
        confirmation = data.get("password_confirmation")
        if not all(
            isinstance(value, str)
            for value in (name, email, password, confirmation)
        ):
            raise InvalidInput("Nombre, correo y ambas contraseñas son obligatorios.")
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

    def _login(self, data: dict[str, object]) -> None:
        identifier = data.get("identifier")
        password = data.get("password")
        if not isinstance(identifier, str) or not isinstance(password, str):
            raise InvalidInput("Escribe tu usuario o correo y tu contraseña.")
        profile = self.app.accounts.authenticate(identifier, password)
        token = self.app.create_session(profile.name)
        self._respond(
            200, {"token": token, "user": profile.to_dict()}
        )

    def _resend_verification(self, data: dict[str, object]) -> None:
        identifier = data.get("identifier")
        if not isinstance(identifier, str) or not identifier.strip():
            raise InvalidInput("Escribe tu usuario o correo.")
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

    def _request_password_recovery(self, data: dict[str, object]) -> None:
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

    def _show_email_verification(self, token: str) -> None:
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

    def _confirm_email(self, token: str) -> None:
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

    def _show_password_form(self, token: str) -> None:
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

    def _save_new_password(self, form: dict[str, str]) -> None:
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


def _page(title: str, message: str, content: str = "") -> str:
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


class BattleArenaHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, app):
        self.app = app
        super().__init__(address, handler)


def create_server(host: str = "0.0.0.0", port: int = 8000):
    app = Application()
    return BattleArenaHTTPServer((host, port), APIHandler, app)


if __name__ == "__main__":
    server = create_server(
        os.getenv("HOST", "0.0.0.0"), int(os.getenv("PORT", "8000"))
    )
    print(
        "Battle Arena API listening on "
        f"{server.server_address[0]}:{server.server_address[1]}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server...")
    finally:
        server.server_close()

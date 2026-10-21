"""Servidor HTTP pequeño para perfiles y datos de juego persistidos en JSON."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import firebase_admin
from firebase_admin import auth, credentials
from firebase_admin.exceptions import FirebaseError

from backend.repository import JSONRepository, RepositoryError, UserNotFound


MAX_REQUEST_BYTES = 1_048_576


## @brief Reúne la persistencia JSON y el verificador de sesiones Firebase.
class Application:
    """Conecta el repositorio JSON con la verificación de identidad Firebase."""

    ## @brief Inicializa el almacenamiento y el bloqueo de Firebase Admin.
    def __init__(self):
        """Inicializa los datos persistentes y el bloqueo de Firebase Admin."""
        data_directory = Path(os.getenv("DATA_DIR", Path(__file__).parent / "data"))
        legacy_file_value = os.getenv(
            "LEGACY_USERS_FILE", str(Path(__file__).parent / "DatosUser.json")
        )
        legacy_file = Path(legacy_file_value) if legacy_file_value else None
        self.repository = JSONRepository(data_directory, legacy_file)
        self.repository.initialize()
        self.firebase_lock = threading.Lock()

    ## @brief Verifica criptográficamente el ID token recibido desde el cliente.
    ## @param token ID token Bearer proporcionado por Firebase Auth.
    ## @return Claims firmados, incluyendo UID, correo y verificación.
    ## @throws RuntimeError Si falta la credencial privada del servidor.
    ## @throws PermissionError Si Firebase rechaza el token.
    def verify_firebase_id_token(self, token: str) -> dict[str, object]:
        """Verifica el token y devuelve sus claims firmados por Firebase."""
        credentials_file = os.getenv("FIREBASE_ADMIN_CREDENTIALS", "").strip()
        if not credentials_file:
            raise RuntimeError(
                "Configura FIREBASE_ADMIN_CREDENTIALS en el servidor."
            )

        try:
            with self.firebase_lock:
                try:
                    firebase_app = firebase_admin.get_app()
                except ValueError:
                    firebase_app = firebase_admin.initialize_app(
                        credentials.Certificate(credentials_file)
                    )
        except (FirebaseError, OSError, ValueError) as error:
            raise RuntimeError(
                "No se pudo inicializar Firebase Admin. Revisa el archivo de cuenta "
                "de servicio y que pertenezca al mismo proyecto."
            ) from error

        try:
            claims = auth.verify_id_token(token, app=firebase_app, check_revoked=True)
        except (FirebaseError, ValueError) as error:
            raise PermissionError("La sesión de Firebase no es válida.") from error
        if not isinstance(claims, dict):
            raise PermissionError("Firebase devolvió una sesión inválida.")
        return claims


## @brief Atiende salud y operaciones de perfil protegidas con Firebase Auth.
class APIHandler(BaseHTTPRequestHandler):
    """Expone salud y perfil de juego; la autenticación pertenece a Firebase."""

    server_version = "BattleArenaProfileAPI/2.0"

    ## @brief Obtiene la aplicación compartida por todos los handlers.
    @property
    def app(self) -> Application:
        """Devuelve la aplicación compartida por los hilos HTTP."""
        return self.server.app

    ## @brief Registra la solicitud sin query strings que pudieran contener tokens.
    def log_message(self, format, *args):
        """Registra solo la ruta para no guardar tokens de URL por accidente."""
        message = format % args
        safe_path = urlparse(self.path).path
        if self.path != safe_path:
            message = message.replace(self.path, safe_path)
        print(f"{self.address_string()} - {message}")

    ## @brief Escribe una respuesta JSON con encabezados de no almacenamiento.
    ## @param status Código de estado HTTP.
    ## @param content Objeto JSON de respuesta.
    def _respond(self, status: int, content: dict[str, object]) -> None:
        """Envía una respuesta JSON sin caché."""
        body = json.dumps(content, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    ## @brief Lee y valida un objeto JSON del cuerpo HTTP.
    ## @return Diccionario con el contenido de la solicitud.
    ## @throws ValueError Si el cuerpo está vacío, es demasiado grande o inválido.
    def _read_json(self) -> dict[str, object]:
        """Lee y valida un objeto JSON del cuerpo de la solicitud."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Content-Length no es válido.") from error
        if length < 1 or length > MAX_REQUEST_BYTES:
            raise ValueError("La solicitud está vacía o excede el tamaño permitido.")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("La solicitud no contiene JSON válido.") from error
        if not isinstance(data, dict):
            raise ValueError("El cuerpo debe ser un objeto JSON.")
        return data

    ## @brief Valida la sesión Bearer e identifica al usuario Firebase.
    ## @return Claims firmados que incluyen UID y correo.
    ## @throws PermissionError Si falta la sesión o no se puede validar.
    def _firebase_claims(self) -> dict[str, object]:
        """Valida el bearer token y exige una identidad y correo utilizables."""
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme.casefold() != "bearer" or not token:
            raise PermissionError("Inicia sesión para consultar el perfil.")
        claims = self.app.verify_firebase_id_token(token)
        uid = claims.get("uid")
        email = claims.get("email")
        if not isinstance(uid, str) or not isinstance(email, str):
            raise PermissionError("La sesión no incluye una identidad válida.")
        return claims

    ## @brief Responde al chequeo de salud y a la consulta autenticada de perfil.
    def do_GET(self) -> None:
        """Responde al chequeo de salud y a la consulta privada de perfil."""
        request_path = urlparse(self.path).path
        try:
            if request_path == "/health":
                self._respond(200, {"status": "ok"})
                return
            if request_path == "/api/profile":
                claims = self._firebase_claims()
                if claims.get("email_verified") is not True:
                    raise PermissionError("Verifica tu correo para consultar el perfil.")
                profile = self.app.repository.get_firebase_profile(
                    str(claims["uid"])
                )
                self._respond(200, {"user": profile.to_dict()})
                return
            self._respond(404, {"error": "Ruta no encontrada."})
        except PermissionError as error:
            self._respond(401, {"error": str(error)})
        except UserNotFound as error:
            self._respond(404, {"error": str(error)})
        except RepositoryError as error:
            print(f"Error GET {request_path}: {type(error).__name__}: {error}")
            self._respond(500, {"error": "No se pudo consultar el perfil."})
        except RuntimeError as error:
            self._respond(503, {"error": str(error)})

    ## @brief Guarda el perfil de juego vinculado al usuario autenticado.
    def do_POST(self) -> None:
        """Registra o actualiza el perfil vinculado al usuario autenticado."""
        request_path = urlparse(self.path).path
        try:
            if request_path != "/api/profile":
                self._respond(404, {"error": "Ruta no encontrada."})
                return
            claims = self._firebase_claims()
            data = self._read_json()
            name = data.get("name")
            email = claims.get("email")
            email_verified = claims.get("email_verified")
            if not isinstance(name, str) or not name.strip() or len(name) > 40:
                raise ValueError("El nombre debe tener entre 1 y 40 caracteres.")
            if not isinstance(email, str) or not isinstance(email_verified, bool):
                raise PermissionError("La sesión no incluye un correo válido.")
            self.app.repository.upsert_firebase_profile(
                str(claims["uid"]), name, email, email_verified
            )
            profile = self.app.repository.get_firebase_profile(str(claims["uid"]))
            self._respond(200, {"user": profile.to_dict()})
        except PermissionError as error:
            self._respond(401, {"error": str(error)})
        except ValueError as error:
            self._respond(400, {"error": str(error)})
        except RepositoryError as error:
            print(f"Error POST {request_path}: {type(error).__name__}: {error}")
            self._respond(500, {"error": "No se pudo guardar el perfil."})
        except RuntimeError as error:
            self._respond(503, {"error": str(error)})


## @brief Servidor HTTP multihilo que comparte una instancia de Application.
class BattleArenaHTTPServer(ThreadingHTTPServer):
    """Servidor multihilo que comparte una instancia de Application."""

    daemon_threads = True

    ## @brief Asocia la aplicación compartida al servidor HTTP.
    ## @param address Dirección IP y puerto de escucha.
    ## @param handler Clase que procesa las solicitudes.
    ## @param app Aplicación con repositorio y verificación Firebase.
    def __init__(self, address, handler, app):
        """Asocia la aplicación a todas las solicitudes entrantes."""
        self.app = app
        super().__init__(address, handler)


## @brief Construye un servidor listo para aceptar solicitudes de perfil.
## @param host Dirección de red en la que escucha el servicio.
## @param port Puerto TCP del servicio HTTP.
## @return Servidor multihilo configurado con la aplicación.
def create_server(host: str = "0.0.0.0", port: int = 8000):
    """Construye la aplicación JSON y el servidor HTTP listo para iniciar."""
    return BattleArenaHTTPServer((host, port), APIHandler, Application())


if __name__ == "__main__":
    server = create_server(
        os.getenv("HOST", "0.0.0.0"), int(os.getenv("PORT", "8000"))
    )
    print(
        "Battle Arena profile API listening on "
        f"{server.server_address[0]}:{server.server_address[1]}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server...")
    finally:
        server.server_close()

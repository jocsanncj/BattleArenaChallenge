import hashlib
import json
import os
import secrets
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from unittest.mock import patch

import SistemaUsuario
from backend.repository import SQLiteRepository
from backend.services import AccountService, EmailService
from servidor import create_server


## @brief Pruebas de aceptación para registro, correo, login y perfil.
class UserStories01To05Tests(unittest.TestCase):
    ## @brief Prepara servidor HTTP local, SQLite temporal y correo simulado.
    ## Cada prueba usa una instalación aislada para no compartir usuarios.
    def setUp(self):
        # Crea una carpeta temporal para guardar la base SQLite de la prueba.
        self.temp_dir = tempfile.TemporaryDirectory()
        # Redirige el almacenamiento, JSON legado y URL pública al entorno de test.
        self.environment = patch.dict(
            os.environ,
            {
                "DATA_DIR": self.temp_dir.name,
                "LEGACY_USERS_FILE": os.path.join(self.temp_dir.name, "missing.json"),
                "PUBLIC_BASE_URL": "http://127.0.0.1",
            },
        )
        # Activa las variables aisladas antes de construir la aplicación.
        self.environment.start()
        # Crea un servidor HTTP en un puerto libre de la máquina.
        self.server = create_server("127.0.0.1", 0)
        self.server.app.accounts.email_service.public_base_url = (
            f"http://127.0.0.1:{self.server.server_address[1]}"
        )
        # Sustituye SMTP para capturar tokens sin enviar correos reales.
        self.email_mock_patcher = patch.object(
            self.server.app.accounts.email_service, "send_link"
        )
        self.email_mock = self.email_mock_patcher.start()
        # Atiende solicitudes en segundo plano durante las pruebas.
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"
        # Apunta el adaptador de la interfaz al servidor local temporal.
        self.url_patcher = patch.object(
            SistemaUsuario, "URL_SERVIDOR", self.base_url
        )
        self.url_patcher.start()
        # Evita que una sesión anterior contamine los casos de autenticación.
        SistemaUsuario.cerrar_sesion()

    ## @brief Apaga el servidor y revierte los recursos temporales de setUp.
    ## @return None.
    def tearDown(self):
        # Deja de aceptar peticiones y espera el fin del hilo de servidor.
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        # Limpia la sesión del cliente y desactiva los parches de prueba.
        SistemaUsuario.cerrar_sesion()
        self.url_patcher.stop()
        self.email_mock_patcher.stop()
        self.environment.stop()
        # Borra la base temporal una vez terminadas las comprobaciones.
        self.temp_dir.cleanup()

    ## @brief Envía una petición HTTP de prueba y decodifica su respuesta.
    ## @param path Ruta relativa solicitada.
    ## @param payload Datos JSON o campos de formulario.
    ## @param token Token opcional para rutas protegidas.
    ## @param form True cuando el cuerpo utiliza formulario URL-encoded.
    ## @return Código HTTP y contenido de respuesta parseado.
    def request(self, path, payload=None, token=None, form=False):
        # Indica que se prefieren respuestas JSON.
        headers = {"Accept": "application/json"}
        body = None
        # Serializa los datos con el formato apropiado para el endpoint.
        if payload is not None:
            if form:
                body = urlencode(payload).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                body = json.dumps(payload).encode("utf-8")
                headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # Construye el objeto de solicitud con POST cuando existe cuerpo.
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        # Decodifica la respuesta normal o el cuerpo de error HTTP.
        try:
            with urlopen(request, timeout=5) as response:
                content_type = response.headers.get("Content-Type", "")
                raw = response.read().decode("utf-8")
                content = json.loads(raw) if "json" in content_type else raw
                return response.status, content
        except HTTPError as error:
            raw = error.read().decode("utf-8")
            content_type = error.headers.get("Content-Type", "")
            content = json.loads(raw) if "json" in content_type else raw
            return error.code, content

    ## @brief Envía una cuenta de prueba con valores predeterminados.
    ## @param name Nombre de usuario de la cuenta.
    ## @param email Correo opcional; se deriva del nombre si no se proporciona.
    ## @param password Contraseña válida por omisión en las pruebas.
    ## @return Estado HTTP y contenido JSON devueltos por el servidor.

    def register(self, name="player", email=None, password="valid-pass-123"):
        ## @brief Envía un registro de prueba con datos predeterminados.
        ## @param name Nombre de usuario que se registra.
        ## @param email Correo opcional; se deriva del nombre si no se proporciona.
        ## @param password Contraseña válida usada por omisión en las pruebas.
        ## @return Estado HTTP y contenido JSON devueltos por el servidor.
        return self.request(
            "/api/register",
            {
                "name": name,
                "email": email or f"{name}@example.com",
                "password": password,
                "password_confirmation": password,
            },
        )

    ## @brief Comprueba registro correcto, campos inválidos y duplicados.
    ## @return None.
    def test_us01_registers_and_reports_invalid_or_duplicate_data(self):
        # Confirma que el registro inicial requiere activar el correo.
        status, result = self.register()
        self.assertEqual(status, 201)
        self.assertTrue(result["verification_required"])
        self.assertTrue(result["verification_sent"])
        self.assertFalse(result["user"]["verificado"])

        # Agrupa ejemplos inválidos con el texto que debe informar cada rechazo.
        invalid_inputs = (
            (
                {
                    "name": "",
                    "email": "player@example.com",
                    "password": "valid-pass-123",
                    "password_confirmation": "valid-pass-123",
                },
                "obligatorios",
            ),
            (
                {
                    "name": "short",
                    "email": "short@example.com",
                    "password": "1234567",
                    "password_confirmation": "1234567",
                },
                "8",
            ),
            (
                {
                    "name": "bad-email",
                    "email": "not-an-email",
                    "password": "valid-pass-123",
                    "password_confirmation": "valid-pass-123",
                },
                "correo",
            ),
            (
                {
                    "name": "mismatch",
                    "email": "mismatch@example.com",
                    "password": "valid-pass-123",
                    "password_confirmation": "different-pass",
                },
                "coinciden",
            ),
        )
        # Ejecuta cada ejemplo aisladamente para identificar fallos concretos.
        for payload, expected_message in invalid_inputs:
            with self.subTest(payload=payload):
                status, response = self.request("/api/register", payload)
                self.assertEqual(status, 400)
                self.assertIn(expected_message, response["error"])

        # Valida que no se repita ni el nombre ni la dirección de correo.
        duplicate_name_status, duplicate_name = self.register(
            email="another@example.com"
        )
        self.assertEqual(duplicate_name_status, 409)
        self.assertEqual(duplicate_name["field"], "name")

        duplicate_email_status, duplicate_email = self.register(
            name="another-player", email="player@example.com"
        )
        self.assertEqual(duplicate_email_status, 409)
        self.assertEqual(duplicate_email["field"], "email")

        # Comprueba que el mínimo permitido de ocho caracteres sí se acepte.
        exact_minimum_status, _ = self.register(
            name="eight-characters",
            password="pass1234",
        )
        self.assertEqual(exact_minimum_status, 201)

    ## @brief Comprueba que una falla SMTP no elimine la cuenta ya registrada.
    ## @return None.
    def test_us01_registration_reports_email_delivery_failure(self):
        # Simula error del proveedor al intentar enviar el enlace.
        self.email_mock.side_effect = RuntimeError("SMTP no configurado")
        status, response = self.register()
        self.assertEqual(status, 201)
        self.assertFalse(response["verification_sent"])
        self.assertIn("SMTP no configurado", response["email_error"])
        self.assertFalse(
            self.server.app.accounts.get_profile("player").email_verified
        )

    ## @brief Comprueba la migración de una cuenta del JSON antiguo a SQLite.
    ## @return None.
    def test_us01_imports_existing_json_accounts_to_persistent_database(self):
        # Genera credenciales hasheadas compatibles con la implementación actual.
        legacy_file = os.path.join(self.temp_dir.name, "legacy.json")
        salt = secrets.token_bytes(16)
        password_hash = hashlib.pbkdf2_hmac(
            "sha256", b"legacy-password", salt, 600_000
        ).hex()
        # Escribe una cuenta legada con récord y correo ya verificado.
        with open(legacy_file, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "usuarios": {
                        "legacy": {
                            "email": "legacy@example.com",
                            "salt": salt.hex(),
                            "hash_password": password_hash,
                            "record": 19,
                            "verificado": True,
                        }
                    }
                },
                file,
            )
        # Inicializa otro repositorio apuntando al JSON de prueba.
        repository = SQLiteRepository(
            Path(self.temp_dir.name) / "migrated", Path(legacy_file)
        )
        repository.initialize()
        service = AccountService(repository, EmailService("http://localhost"))

        profile = service.authenticate("legacy@example.com", "legacy-password")

        self.assertEqual(profile.name, "legacy")
        self.assertEqual(profile.record, 19)
        self.assertTrue(profile.email_verified)

    ## @brief Comprueba la activación por enlace, uso único y tokens inválidos.
    ## @return None.
    def test_us02_verification_link_activates_once_and_rejects_invalid_link(self):
        # Crea una cuenta y recupera el token capturado por el mock SMTP.
        status, _ = self.register()
        self.assertEqual(status, 201)
        token = self.email_mock.call_args.args[2]
        link = urlparse(
            f"{self.base_url}/verify-email?token={token}"
        )
        self.assertIn("verify-email", link.path)

        # El GET muestra la confirmación y el POST consume el enlace una vez.
        status, page = self.request(f"/verify-email?token={token}")
        self.assertEqual(status, 200)
        self.assertIn("Verificar correo", page)

        status, confirmation = self.request(
            "/verify-email",
            {"token": token},
            form=True,
        )
        self.assertEqual(status, 200)
        self.assertIn("Correo verificado", confirmation)

        # Comprueba que el indicador actualizado quedó persistido.
        profile = self.server.app.accounts.get_profile("player").to_dict()
        self.assertTrue(profile["verificado"])

        repeated_status, repeated_response = self.request(
            "/verify-email", {"token": token}, form=True
        )
        self.assertEqual(repeated_status, 400)
        self.assertIn("no es válido", repeated_response)

        invalid_status, invalid_response = self.request(
            "/verify-email", {"token": "not-a-real-token"}, form=True
        )
        self.assertEqual(invalid_status, 400)
        self.assertIn("no es válido", invalid_response)

    ## @brief Comprueba las URL incluidas en ambos tipos de correo.
    ## @return None.
    def test_email_service_builds_links_for_verification_and_recovery(self):
        # Intercepta el envío para examinar los textos sin usar SMTP real.
        email_service = EmailService("http://server.example:8000")
        with patch.object(email_service, "_send") as send:
            email_service.send_link(
                "player@example.com", "player", "verify-token", "verificacion"
            )
            verification_message = send.call_args.args[2]
            email_service.send_link(
                "player@example.com", "player", "reset-token", "recuperacion"
            )
            recovery_message = send.call_args.args[2]

        self.assertIn(
            "http://server.example:8000/verify-email?token=verify-token",
            verification_message,
        )
        self.assertIn(
            "http://server.example:8000/reset-password?token=reset-token",
            recovery_message,
        )

    ## @brief Comprueba que un enlace expirado no active la cuenta.
    ## @return None.
    def test_us02_expired_verification_link_is_rejected(self):
        # Crea un token con una fecha de expiración pasada.
        self.register()
        token = "expired-verification-token"
        self.server.app.repository.save_email_link(
            self.server.app.accounts._token_hash(token),
            "player",
            "verificacion",
            self._past(),
        )
        status, response = self.request(
            "/verify-email", {"token": token}, form=True
        )
        self.assertEqual(status, 400)
        self.assertIn("venció", response)

    ## @brief Comprueba login por nombre/correo y bloqueo previo a verificación.
    ## @return None.
    def test_us03_login_accepts_username_or_email_and_blocks_unverified_users(self):
        # La cuenta no debe autenticar hasta consumir el enlace de correo.
        self.register()
        status, response = self.request(
            "/api/login",
            {"identifier": "player", "password": "valid-pass-123"},
        )
        self.assertEqual(status, 403)
        self.assertTrue(response["email_unverified"])

        # Verifica el correo y luego comprueba ambos identificadores permitidos.
        self.email_mock.reset_mock()
        self.request("/api/email/resend", {"identifier": "player"})
        token = self.email_mock.call_args.args[2]
        self.request("/verify-email", {"token": token}, form=True)

        for identifier in ("player", "player@example.com"):
            with self.subTest(identifier=identifier):
                status, response = self.request(
                    "/api/login",
                    {"identifier": identifier, "password": "valid-pass-123"},
                )
                self.assertEqual(status, 200)
                self.assertEqual(response["user"]["name"], "player")
                self.assertIsInstance(response["token"], str)

        # Las credenciales incorrectas y el usuario inexistente se rechazan.
        wrong_status, wrong_password = self.request(
            "/api/login",
            {"identifier": "player", "password": "wrong-password"},
        )
        self.assertEqual(wrong_status, 401)
        self.assertIn("incorrectos", wrong_password["error"])

        missing_status, missing_user = self.request(
            "/api/login",
            {"identifier": "unknown@example.com", "password": "valid-pass-123"},
        )
        self.assertEqual(missing_status, 401)
        self.assertIn("incorrectos", missing_user["error"])

    ## @brief Comprueba que perfil autenticado incluye estadísticas e historial.
    ## @return None.
    def test_us04_profile_includes_identity_statistics_achievements_and_history(self):
        # Prepara una cuenta activa y una sesión mediante el flujo HTTP.
        self.register()
        self.email_mock.reset_mock()
        self.request("/api/email/resend", {"identifier": "player"})
        token_link = self.email_mock.call_args.args[2]
        self.request("/verify-email", {"token": token_link}, form=True)
        _, login = self.request(
            "/api/login",
            {"identifier": "player@example.com", "password": "valid-pass-123"},
        )

        # Inserta registros de muestra para validar agregados y orden del historial.
        with self.server.app.repository._connection() as connection:
            connection.execute(
                "UPDATE usuarios SET record = 42 WHERE nombre = 'player'"
            )
            connection.execute(
                "INSERT INTO logros (nombre_usuario, titulo) VALUES (?, ?)",
                ("player", "Primera victoria"),
            )
            connection.execute(
                """
                INSERT INTO historial_partidas
                    (nombre_usuario, oponente, resultado, puntuacion, fecha)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("player", "rival", "victoria", 42, "2026-10-19T12:00:00+00:00"),
            )

        # Solicita el perfil usando la sesión obtenida durante el login.
        status, profile_response = self.request(
            "/api/profile", token=login["token"]
        )
        self.assertEqual(status, 200)
        profile = profile_response["user"]
        self.assertEqual(profile["name"], "player")
        self.assertIsNone(profile["avatar"])
        self.assertTrue(profile["verificado"])
        self.assertEqual(profile["record"], 42)
        self.assertEqual(profile["statistics"]["matches_played"], 1)
        self.assertEqual(profile["statistics"]["wins"], 1)
        self.assertIn("Primera victoria", profile["achievements"])
        self.assertEqual(profile["match_history"][0]["opponent"], "rival")
        self.assertIsInstance(profile["ranking"], int)

        # La misma ruta debe bloquear una petición sin token.
        unauthorized_status, _ = self.request("/api/profile")
        self.assertEqual(unauthorized_status, 401)

    ## @brief Comprueba que un perfil nuevo tenga estadísticas y listas vacías.
    ## @return None.
    def test_us04_new_player_profile_has_empty_history(self):
        # Crea el usuario y consulta su perfil antes de registrar partidas.
        self.register()
        profile = self.server.app.accounts.get_profile("player").to_dict()
        self.assertEqual(
            profile["statistics"],
            {"matches_played": 0, "wins": 0, "losses": 0, "draws": 0},
        )
        self.assertEqual(profile["achievements"], [])
        self.assertEqual(profile["match_history"], [])
        self.assertIsNone(profile["ranking"])

    ## @brief Comprueba recuperación válida y que su enlace solo se utilice una vez.
    ## @return None.
    def test_us05_recovery_link_resets_password_and_expires(self):
        # Verifica la cuenta para permitir la recuperación normal.
        self.register()
        self.request(
            "/verify-email",
            {"token": self.email_mock.call_args.args[2]},
            form=True,
        )
        self.email_mock.reset_mock()
        # Solicita el enlace, abre su formulario y envía la nueva contraseña.
        status, response = self.request(
            "/api/password/recovery", {"identifier": "player@example.com"}
        )
        self.assertEqual(status, 200)
        self.assertIn("recibirás un enlace", response["message"])
        token = self.email_mock.call_args.args[2]

        status, page = self.request(f"/reset-password?token={token}")
        self.assertEqual(status, 200)
        self.assertIn("Nueva contraseña", page)

        status, result = self.request(
            "/reset-password",
            {
                "token": token,
                "password": "new-password-456",
                "confirmation": "new-password-456",
            },
            form=True,
        )
        self.assertEqual(status, 200)
        self.assertIn("Contraseña actualizada", result)

        # La contraseña antigua debe fallar y la nueva debe autenticar.
        old_status, _ = self.request(
            "/api/login",
            {"identifier": "player", "password": "valid-pass-123"},
        )
        new_status, new_login = self.request(
            "/api/login",
            {"identifier": "player", "password": "new-password-456"},
        )
        self.assertEqual(old_status, 401)
        self.assertEqual(new_status, 200)
        self.assertEqual(new_login["user"]["name"], "player")

        reused_status, reused_page = self.request(
            "/reset-password",
            {
                "token": token,
                "password": "another-password",
                "confirmation": "another-password",
            },
            form=True,
        )
        self.assertEqual(reused_status, 400)
        self.assertIn("no es válido", reused_page)

    ## @brief Rechaza enlaces vencidos, tokens falsos y contraseñas cortas.
    ## @return None.
    def test_us05_recovery_rejects_invalid_expired_and_short_password(self):
        # Persiste un token vencido para comprobar que el backend lo rechaza.
        self.register()
        expired_token = "expired-recovery-token"
        self.server.app.repository.save_email_link(
            self.server.app.accounts._token_hash(expired_token),
            "player",
            "recuperacion",
            self._past(),
        )
        expired_status, _ = self.request(
            f"/reset-password?token={expired_token}"
        )
        self.assertEqual(expired_status, 400)

        # Un token inventado tampoco debe permitir modificar la cuenta.
        invalid_status, invalid_page = self.request(
            "/reset-password",
            {
                "token": "invalid-token",
                "password": "new-password",
                "confirmation": "new-password",
            },
            form=True,
        )
        self.assertEqual(invalid_status, 400)
        self.assertIn("no es válido", invalid_page)

        # Solicita un token válido y demuestra que la contraseña corta no se guarda.
        self.email_mock.reset_mock()
        self.request("/api/password/recovery", {"identifier": "player"})
        token = self.email_mock.call_args.args[2]
        short_status, short_page = self.request(
            "/reset-password",
            {
                "token": token,
                "password": "short",
                "confirmation": "short",
            },
            form=True,
        )
        self.assertEqual(short_status, 400)
        self.assertIn("8", short_page)

    ## @brief Comprueba login, lectura de perfil y limpieza de sesión del adaptador.
    ## @return None.
    def test_client_adapter_logs_in_and_reads_profile(self):
        # Prepara una cuenta verificada antes de utilizar el cliente público.
        self.register()
        self.email_mock.reset_mock()
        self.request("/api/email/resend", {"identifier": "player"})
        self.request(
            "/verify-email",
            {"token": self.email_mock.call_args.args[2]},
            form=True,
        )
        user = SistemaUsuario.autenticar_usuario(
            "player@example.com", "valid-pass-123"
        )
        self.assertEqual(user["name"], "player")
        self.assertEqual(SistemaUsuario.obtener_usuario()["email"], "player@example.com")
        # Comprueba que cerrar sesión impide posteriores consultas privadas.
        SistemaUsuario.cerrar_sesion()
        with self.assertRaises(RuntimeError):
            SistemaUsuario.obtener_usuario()

    @staticmethod
    ## @brief Calcula una fecha UTC pasada para crear enlaces vencidos.
    ## @return Fecha de hace un minuto.
    def _past():
        # Importa solo los tipos requeridos por este helper de pruebas.
        from datetime import datetime, timedelta, timezone

        return datetime.now(timezone.utc) - timedelta(minutes=1)


## @brief Ejecuta la suite directamente al iniciar este archivo.
if __name__ == "__main__":
    # Deja que unittest descubra y ejecute la clase de casos.
    unittest.main()

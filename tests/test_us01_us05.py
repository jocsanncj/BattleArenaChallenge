"""Pruebas del cliente Firebase Auth y del perfil JSON protegido."""

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import SistemaUsuario
from backend.repository import JSONRepository
from servidor import create_server


## @brief Pruebas unitarias del cliente Firebase Auth sin conexión externa.
class FirebaseClientTests(unittest.TestCase):
    """Comprueba el flujo de cuenta sin contactar servicios de Google."""

    ## @brief Limpia estado local antes de cada prueba.
    def setUp(self):
        SistemaUsuario.cerrar_sesion()

    ## @brief Borra los tokens guardados después de cada prueba.
    def tearDown(self):
        SistemaUsuario.cerrar_sesion()

    ## @brief Comprueba registro Firebase, verificación y perfil JSON.
    def test_registration_creates_firebase_user_and_game_profile(self):
        firebase_responses = [
            {
                "idToken": "signup-id-token",
                "refreshToken": "signup-refresh-token",
                "email": "player@example.com",
            },
            {
                "idToken": "updated-id-token",
                "refreshToken": "updated-refresh-token",
            },
            {},
        ]
        profile = {"name": "player", "email": "player@example.com"}
        with (
            patch.object(
                SistemaUsuario,
                "_firebase_request",
                side_effect=firebase_responses,
            ) as firebase_request,
            patch.object(
                SistemaUsuario, "_profile_request", return_value={"user": profile}
            ) as profile_request,
        ):
            result = SistemaUsuario.registrar_usuario(
                " player ", "valid-pass-123", "valid-pass-123", "player@example.com"
            )

        self.assertTrue(result["verification_required"])
        self.assertTrue(result["verification_sent"])
        self.assertEqual(firebase_request.call_args_list[0].args[0], "accounts:signUp")
        self.assertEqual(
            firebase_request.call_args_list[1].args[0], "accounts:update"
        )
        self.assertEqual(
            firebase_request.call_args_list[2].args[1]["requestType"],
            "VERIFY_EMAIL",
        )
        profile_request.assert_called_once_with("POST", {"name": "player"})

    ## @brief Rechaza confirmaciones distintas antes de contactar Firebase.
    def test_registration_rejects_mismatched_password_without_network_call(self):
        with patch.object(SistemaUsuario, "_firebase_request") as firebase_request:
            with self.assertRaisesRegex(ValueError, "no coinciden"):
                SistemaUsuario.registrar_usuario(
                    "player", "valid-pass-123", "different-pass", "player@example.com"
                )
        firebase_request.assert_not_called()

    ## @brief Exige correo verificado y sincroniza el perfil tras el login.
    def test_login_requires_verified_email_and_syncs_profile(self):
        profile = {"name": "player", "email": "player@example.com"}
        with (
            patch.object(
                SistemaUsuario,
                "_firebase_request",
                side_effect=[
                    {
                        "idToken": "login-id-token",
                        "refreshToken": "login-refresh-token",
                        "email": "player@example.com",
                    },
                    {
                        "users": [
                            {
                                "emailVerified": True,
                                "displayName": "player",
                            }
                        ]
                    },
                ],
            ),
            patch.object(
                SistemaUsuario, "_profile_request", return_value={"user": profile}
            ) as profile_request,
        ):
            authenticated = SistemaUsuario.autenticar_usuario(
                "player@example.com", "valid-pass-123"
            )

        self.assertEqual(authenticated, profile)
        profile_request.assert_called_once_with("POST", {"name": "player"})

    ## @brief Impide iniciar el flujo de juego con correo sin verificar.
    def test_login_blocks_unverified_email(self):
        with patch.object(
            SistemaUsuario,
            "_firebase_request",
            side_effect=[
                {
                    "idToken": "unverified-id-token",
                    "refreshToken": "unverified-refresh-token",
                    "email": "player@example.com",
                },
                {"users": [{"emailVerified": False, "displayName": "player"}]},
            ],
        ):
            with self.assertRaises(SistemaUsuario.CorreoPendiente):
                SistemaUsuario.autenticar_usuario(
                    "player@example.com", "valid-pass-123"
                )

    ## @brief Traduce credenciales rechazadas al resultado usado por la interfaz.
    def test_invalid_login_is_returned_as_none(self):
        with patch.object(
            SistemaUsuario,
            "_firebase_request",
            side_effect=SistemaUsuario.CredencialesInvalidas("wrong password"),
        ):
            self.assertIsNone(
                SistemaUsuario.autenticar_usuario(
                    "player@example.com", "incorrect"
                )
            )

    ## @brief Mantiene respuesta genérica para un correo inexistente.
    def test_password_recovery_does_not_disclose_missing_email(self):
        with patch.object(
            SistemaUsuario,
            "_firebase_request",
            side_effect=SistemaUsuario.FirebaseAPIError("EMAIL_NOT_FOUND"),
        ):
            SistemaUsuario.solicitar_recuperacion("unknown@example.com")


## @brief Pruebas HTTP del servidor de perfiles con verificación Firebase simulada.
class FirebaseProfileServerTests(unittest.TestCase):
    """Comprueba que el servidor valida identidad y persiste solo datos de juego."""

    ## @brief Prepara un servidor HTTP y JSON aislados para cada caso.
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "DATA_DIR": self.temp_dir.name,
                "LEGACY_USERS_FILE": "",
                "FIREBASE_ADMIN_CREDENTIALS": "",
            },
        )
        self.environment.start()
        self.server = create_server("127.0.0.1", 0)
        self.verify_patcher = patch.object(
            self.server.app, "verify_firebase_id_token"
        )
        self.verify_token = self.verify_patcher.start()
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    ## @brief Detiene el servidor y limpia los recursos temporales del caso.
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.verify_patcher.stop()
        self.environment.stop()
        self.temp_dir.cleanup()

    ## @brief Envía una solicitud HTTP JSON al servidor de prueba.
    ## @param path Ruta HTTP solicitada.
    ## @param method Método HTTP.
    ## @param payload Objeto JSON opcional.
    ## @param token Token Bearer opcional.
    ## @return Estado HTTP y diccionario JSON de respuesta.
    def request(self, path, method="GET", payload=None, token=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    ## @brief Confirma que el endpoint de salud no requiere iniciar sesión.
    def test_health_does_not_require_firebase_credentials(self):
        status, response = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(response, {"status": "ok"})

    ## @brief Guarda y consulta un perfil a partir de claims Firebase verificados.
    def test_profile_is_created_from_verified_firebase_claims(self):
        self.verify_token.return_value = {
            "uid": "firebase-uid-1",
            "email": "player@example.com",
            "email_verified": True,
        }
        status, created = self.request(
            "/api/profile",
            method="POST",
            payload={"name": "player"},
            token="valid-token",
        )
        self.assertEqual(status, 200)
        self.assertEqual(created["user"]["name"], "player")
        self.assertTrue(created["user"]["verificado"])
        self.assertEqual(created["user"]["record"], 0)
        self.assertIsNone(created["user"]["avatar"])

        status, loaded = self.request("/api/profile", token="valid-token")
        self.assertEqual(status, 200)
        self.assertEqual(loaded["user"], created["user"])

        stored = json.loads(
            (Path(self.temp_dir.name) / "usuarios.json").read_text(encoding="utf-8")
        )
        self.assertIn("firebase-uid-1", stored["firebase_profiles"])

    ## @brief Rechaza tokens ausentes, inválidos y de correos no verificados.
    def test_profile_requires_a_valid_firebase_token(self):
        status, response = self.request("/api/profile")
        self.assertEqual(status, 401)
        self.assertIn("Inicia sesión", response["error"])

        self.verify_token.return_value = {
            "uid": "firebase-uid-unverified",
            "email": "pending@example.com",
            "email_verified": False,
        }
        status, response = self.request("/api/profile", token="unverified-token")
        self.assertEqual(status, 401)
        self.assertIn("Verifica tu correo", response["error"])

        self.verify_token.side_effect = PermissionError("token inválido")
        status, response = self.request("/api/profile", token="invalid-token")
        self.assertEqual(status, 401)
        self.assertEqual(response["error"], "token inválido")

    ## @brief Comprueba que las rutas de login propias ya no están disponibles.
    def test_old_custom_auth_routes_are_removed(self):
        status, response = self.request(
            "/api/login", method="POST", payload={"identifier": "player"}
        )
        self.assertEqual(status, 404)
        self.assertEqual(response["error"], "Ruta no encontrada.")


## @brief Pruebas de persistencia JSON de perfiles Firebase.
class FirebaseProfileRepositoryTests(unittest.TestCase):
    """Comprueba que los perfiles de Firebase quedan persistidos en JSON."""

    ## @brief Comprueba que la sección nueva se guarda en un JSON anterior.
    def test_old_json_files_gain_firebase_profile_section_on_write(self):
        with tempfile.TemporaryDirectory() as directory:
            old_file = Path(directory) / "usuarios.json"
            old_file.write_text(
                json.dumps(
                    {
                        "usuarios": {},
                        "logros": {},
                        "historial_partidas": {},
                        "enlaces": {},
                    }
                ),
                encoding="utf-8",
            )
            repository = JSONRepository(Path(directory))
            repository.upsert_firebase_profile(
                "firebase-uid-2",
                "another-player",
                "another@example.com",
                False,
            )
            profile = repository.get_firebase_profile("firebase-uid-2")

            self.assertEqual(profile.name, "another-player")
            self.assertFalse(profile.email_verified)
            self.assertEqual(profile.record, 0)


if __name__ == "__main__":
    unittest.main()

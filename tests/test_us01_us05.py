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


class UserStories01To05Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "DATA_DIR": self.temp_dir.name,
                "LEGACY_USERS_FILE": os.path.join(self.temp_dir.name, "missing.json"),
                "PUBLIC_BASE_URL": "http://127.0.0.1",
            },
        )
        self.environment.start()
        self.server = create_server("127.0.0.1", 0)
        self.server.app.accounts.email_service.public_base_url = (
            f"http://127.0.0.1:{self.server.server_address[1]}"
        )
        self.email_mock_patcher = patch.object(
            self.server.app.accounts.email_service, "send_link"
        )
        self.email_mock = self.email_mock_patcher.start()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"
        self.url_patcher = patch.object(
            SistemaUsuario, "URL_SERVIDOR", self.base_url
        )
        self.url_patcher.start()
        SistemaUsuario.cerrar_sesion()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        SistemaUsuario.cerrar_sesion()
        self.url_patcher.stop()
        self.email_mock_patcher.stop()
        self.environment.stop()
        self.temp_dir.cleanup()

    def request(self, path, payload=None, token=None, form=False):
        headers = {"Accept": "application/json"}
        body = None
        if payload is not None:
            if form:
                body = urlencode(payload).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                body = json.dumps(payload).encode("utf-8")
                headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
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

    def register(self, name="player", email=None, password="valid-pass-123"):
        return self.request(
            "/api/register",
            {
                "name": name,
                "email": email or f"{name}@example.com",
                "password": password,
                "password_confirmation": password,
            },
        )

    def test_us01_registers_and_reports_invalid_or_duplicate_data(self):
        status, result = self.register()
        self.assertEqual(status, 201)
        self.assertTrue(result["verification_required"])
        self.assertTrue(result["verification_sent"])
        self.assertFalse(result["user"]["verificado"])

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
        for payload, expected_message in invalid_inputs:
            with self.subTest(payload=payload):
                status, response = self.request("/api/register", payload)
                self.assertEqual(status, 400)
                self.assertIn(expected_message, response["error"])

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

        exact_minimum_status, _ = self.register(
            name="eight-characters",
            password="pass1234",
        )
        self.assertEqual(exact_minimum_status, 201)

    def test_us01_registration_reports_email_delivery_failure(self):
        self.email_mock.side_effect = RuntimeError("SMTP no configurado")
        status, response = self.register()
        self.assertEqual(status, 201)
        self.assertFalse(response["verification_sent"])
        self.assertIn("SMTP no configurado", response["email_error"])
        self.assertFalse(
            self.server.app.accounts.get_profile("player").email_verified
        )

    def test_us01_imports_existing_json_accounts_to_persistent_database(self):
        legacy_file = os.path.join(self.temp_dir.name, "legacy.json")
        salt = secrets.token_bytes(16)
        password_hash = hashlib.pbkdf2_hmac(
            "sha256", b"legacy-password", salt, 600_000
        ).hex()
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
        repository = SQLiteRepository(
            Path(self.temp_dir.name) / "migrated", Path(legacy_file)
        )
        repository.initialize()
        service = AccountService(repository, EmailService("http://localhost"))

        profile = service.authenticate("legacy@example.com", "legacy-password")

        self.assertEqual(profile.name, "legacy")
        self.assertEqual(profile.record, 19)
        self.assertTrue(profile.email_verified)

    def test_us02_verification_link_activates_once_and_rejects_invalid_link(self):
        status, _ = self.register()
        self.assertEqual(status, 201)
        token = self.email_mock.call_args.args[2]
        link = urlparse(
            f"{self.base_url}/verify-email?token={token}"
        )
        self.assertIn("verify-email", link.path)

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

    def test_email_service_builds_links_for_verification_and_recovery(self):
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

    def test_us02_expired_verification_link_is_rejected(self):
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

    def test_us03_login_accepts_username_or_email_and_blocks_unverified_users(self):
        self.register()
        status, response = self.request(
            "/api/login",
            {"identifier": "player", "password": "valid-pass-123"},
        )
        self.assertEqual(status, 403)
        self.assertTrue(response["email_unverified"])

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

    def test_us04_profile_includes_identity_statistics_achievements_and_history(self):
        self.register()
        self.email_mock.reset_mock()
        self.request("/api/email/resend", {"identifier": "player"})
        token_link = self.email_mock.call_args.args[2]
        self.request("/verify-email", {"token": token_link}, form=True)
        _, login = self.request(
            "/api/login",
            {"identifier": "player@example.com", "password": "valid-pass-123"},
        )

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

        unauthorized_status, _ = self.request("/api/profile")
        self.assertEqual(unauthorized_status, 401)

    def test_us04_new_player_profile_has_empty_history(self):
        self.register()
        profile = self.server.app.accounts.get_profile("player").to_dict()
        self.assertEqual(
            profile["statistics"],
            {"matches_played": 0, "wins": 0, "losses": 0, "draws": 0},
        )
        self.assertEqual(profile["achievements"], [])
        self.assertEqual(profile["match_history"], [])
        self.assertIsNone(profile["ranking"])

    def test_us05_recovery_link_resets_password_and_expires(self):
        self.register()
        self.request(
            "/verify-email",
            {"token": self.email_mock.call_args.args[2]},
            form=True,
        )
        self.email_mock.reset_mock()
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

    def test_us05_recovery_rejects_invalid_expired_and_short_password(self):
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

    def test_client_adapter_logs_in_and_reads_profile(self):
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
        SistemaUsuario.cerrar_sesion()
        with self.assertRaises(RuntimeError):
            SistemaUsuario.obtener_usuario()

    @staticmethod
    def _past():
        from datetime import datetime, timedelta, timezone

        return datetime.now(timezone.utc) - timedelta(minutes=1)


if __name__ == "__main__":
    unittest.main()

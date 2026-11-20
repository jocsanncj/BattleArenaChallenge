import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pygame

from frontend.account.menu import MainMenuScene
from frontend.auth import google_web, service


class GoogleLoginTests(unittest.TestCase):
    origen = "http://localhost:8765"

    def setUp(self):
        if not pygame.font.get_init():
            pygame.font.init()
            self.addCleanup(pygame.font.quit)
        patches = (
            patch.object(google_web, "_servidor", SimpleNamespace(server_port=8765)),
            patch.object(google_web, "_intento_actual", None),
            patch.object(google_web.webbrowser, "open_new_tab", return_value=True),
            patch.object(service._servicio, "_sesion", None),
        )
        for parche in patches:
            parche.start()
            self.addCleanup(parche.stop)
        self.escena = MainMenuScene(pygame.font.Font(None, 20))
        self.escena._set_page("login")
        self.escena._iniciar_sesion_google()
        self.clave = self.escena.intento_google.clave
        self.cliente = google_web.app.test_client()

    def _enviar(self, accion, datos=None):
        return self.cliente.post(
            f"/login/google/{accion}",
            base_url=self.origen,
            headers={"Origin": self.origen, "X-Intento": self.clave},
            json=datos,
        )

    def test_cancelar_descarta_el_intento_y_su_clave(self):
        self.assertEqual(self._enviar("cancelar").status_code, 204)

        self.escena.update(None)

        self.assertEqual(self.escena.page, "login")
        self.assertEqual(self.escena.status, "Acceso con Google cancelado.")
        self.assertIsNone(self.escena.intento_google)
        self.assertIsNone(service.usuario_actual())
        self.assertEqual(self._enviar("cancelar").status_code, 409)

    def test_error_de_firebase_aparece_en_el_juego_y_permite_reintentar(self):
        respuesta = self._enviar("fallar", {"codigo": "auth/operation-not-allowed"})
        self.assertEqual(respuesta.status_code, 200)

        self.escena.update(None)

        self.assertEqual(self.escena.page, "login")
        self.assertEqual(self.escena.status, respuesta.get_json()["error"])
        self.assertIsNone(service.usuario_actual())
        self.escena._iniciar_sesion_google()
        self.assertNotEqual(self.escena.intento_google.clave, self.clave)
        self.assertEqual(self._enviar("fallar", {"codigo": "auth/popup-blocked"}).status_code, 409)

    def test_acceso_verificado_activa_el_perfil_en_el_siguiente_fotograma(self):
        sesion = service.Sesion("id-de-prueba", "refresh-de-prueba", "jugador@example.test", "Jugador")
        perfil = {"name": "Jugador"}
        with patch.object(google_web, "preparar_acceso_google", return_value=(sesion, perfil)) as preparar:
            self.assertEqual(self._enviar("completar", {"accessToken": "credencial-de-prueba"}).status_code, 204)
            preparar.assert_called_once_with("credencial-de-prueba")
        self.assertIsNone(service.usuario_actual())

        self.escena.update(None)

        self.assertEqual(self.escena.page, "menu")
        self.assertEqual(self.escena.current_user, perfil)
        self.assertEqual(service.usuario_actual(), "Jugador")

import unittest
from types import SimpleNamespace

from frontend.account.menu import MainMenuScene
from frontend.account.online import JuegoOnlineScene
from frontend.ui.arena import PantallaArena
from frontend.ui.avatar import PantallaAvatar
from frontend.ui.configuracion import PantallaConfiguracion
from frontend.ui.sala import PantallaSala


class UiModuleLayoutTests(unittest.TestCase):
    def test_online_scene_keeps_its_window_event_and_lifecycle_hooks(self):
        self.assertTrue(callable(JuegoOnlineScene.handle_event))
        self.assertTrue(callable(JuegoOnlineScene.update))
        self.assertTrue(callable(JuegoOnlineScene.on_close))

    def test_screens_are_exposed_from_their_frontend_packages(self):
        screens = (PantallaAvatar, PantallaSala, PantallaConfiguracion, PantallaArena)
        self.assertTrue(all(callable(screen) for screen in screens))

    def test_room_creator_check_uses_the_current_context_user(self):
        screen = object.__new__(PantallaSala)
        screen.ctx = SimpleNamespace(id_usuario=42)
        screen._partida = SimpleNamespace(
            jugadores=[SimpleNamespace(id_usuario=42)]
        )

        self.assertTrue(screen._es_creador())

        screen._partida.jugadores[0].id_usuario = 7
        self.assertFalse(screen._es_creador())


if __name__ == "__main__":
    unittest.main()

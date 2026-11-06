import unittest

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


if __name__ == "__main__":
    unittest.main()

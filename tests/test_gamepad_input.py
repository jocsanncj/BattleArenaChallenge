import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame

from acciones import ControlEntrada, MODO_GAMEPAD, MODO_TECLADO
from us10 import MultiplayerArena
from us110 import MultiplayerArena as MultiplayerArenaCompat


class GamepadInputTests(unittest.TestCase):
    def setUp(self):
        pygame.init()

    def tearDown(self):
        pygame.quit()

    def test_us110_reexports_the_us10_arena(self):
        self.assertIs(MultiplayerArenaCompat, MultiplayerArena)

    def test_keyboard_direction_tracks_key_press_and_release(self):
        control = ControlEntrada()

        control.procesar_evento(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_w))
        self.assertEqual(control.direccion_actual(), "up")

        control.procesar_evento(pygame.event.Event(pygame.KEYUP, key=pygame.K_w))
        self.assertIsNone(control.direccion_actual())

    def test_gamepad_mode_requires_a_connected_controller(self):
        with patch("acciones.pygame.joystick.get_count", return_value=0):
            control = ControlEntrada()
            with self.assertRaisesRegex(ValueError, "No se detectó un gamepad"):
                control.seleccionar(MODO_GAMEPAD)

    def test_gamepad_uses_hat_and_analog_stick(self):
        joystick = Mock()
        joystick.get_name.return_value = "MSI FORCE GC30 V2"
        joystick.get_instance_id.return_value = 7
        joystick.get_numhats.return_value = 1
        joystick.get_hat.return_value = (0, 1)
        joystick.get_numaxes.return_value = 2
        joystick.get_axis.side_effect = [0.0, 0.0]

        with (
            patch("acciones.pygame.joystick.get_count", return_value=1),
            patch("acciones.pygame.joystick.Joystick", return_value=joystick),
        ):
            control = ControlEntrada()
            control.seleccionar(MODO_GAMEPAD)

            self.assertEqual(control.nombre_gamepad, "MSI FORCE GC30 V2")
            self.assertEqual(control.direccion_actual(), "up")

            joystick.get_hat.return_value = (0, 0)
            joystick.get_axis.side_effect = [-0.9, 0.1]
            self.assertEqual(control.direccion_actual(), "left")

            joystick.get_axis.side_effect = [0.0, 0.0]
            control.procesar_evento(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_w))
            self.assertIsNone(control.direccion_actual())

    def test_gamepad_action_button_plays_effect_sound(self):
        joystick = Mock()
        joystick.get_instance_id.return_value = 7
        sound = Mock()
        with (
            patch("acciones.pygame.joystick.get_count", return_value=1),
            patch("acciones.pygame.joystick.Joystick", return_value=joystick),
            patch("acciones._sonido", sound),
        ):
            control = ControlEntrada()
            control.seleccionar(MODO_GAMEPAD)
            control.procesar_evento(
                pygame.event.Event(
                    pygame.JOYBUTTONDOWN,
                    instance_id=7,
                    button=0,
                )
            )

        sound.play.assert_called_once_with()

    def test_gamepad_action_button_is_ignored_when_keyboard_selected(self):
        joystick = Mock()
        joystick.get_instance_id.return_value = 7
        sound = Mock()
        with (
            patch("acciones.pygame.joystick.get_count", return_value=1),
            patch("acciones.pygame.joystick.Joystick", return_value=joystick),
            patch("acciones._sonido", sound),
        ):
            control = ControlEntrada()
            control.procesar_evento(
                pygame.event.Event(
                    pygame.JOYBUTTONDOWN,
                    instance_id=7,
                    button=0,
                )
            )

        sound.play.assert_not_called()

    def test_disconnect_falls_back_to_keyboard(self):
        joystick = Mock()
        joystick.get_instance_id.return_value = 7
        counts = iter((1, 0))
        with (
            patch("acciones.pygame.joystick.get_count", side_effect=lambda: next(counts)),
            patch("acciones.pygame.joystick.Joystick", return_value=joystick),
        ):
            control = ControlEntrada()
            control.seleccionar(MODO_GAMEPAD)
            control.procesar_evento(
                pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=7)
            )

        self.assertEqual(control.modo, MODO_TECLADO)
        self.assertIn("desconectó", control.aviso)
        joystick.quit.assert_called_once()


if __name__ == "__main__":
    unittest.main()

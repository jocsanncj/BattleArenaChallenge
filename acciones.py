"""Entrada de teclado y gamepad para la arena."""

from __future__ import annotations

import os
from collections.abc import Callable

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame

RUTA_SONIDO = "Media/Efecto.mp3"
MODO_TECLADO = "teclado"
MODO_GAMEPAD = "gamepad"
BOTON_GAMEPAD_ACCION = 0

_bindings: dict[str, Callable[[], None]] = {}
_abajo: set[str] = set()
_sonido: pygame.mixer.Sound | None = None

_DIRECCIONES_TECLADO = {
    pygame.K_UP: "up",
    pygame.K_w: "up",
    pygame.K_DOWN: "down",
    pygame.K_s: "down",
    pygame.K_LEFT: "left",
    pygame.K_a: "left",
    pygame.K_RIGHT: "right",
    pygame.K_d: "right",
}


def _reproducir_sonido() -> None:
    if _sonido:
        _sonido.play()


def bindear(tecla: str, funcion: Callable[[], None]) -> None:
    """Asocia una tecla de Pygame con una acción."""
    if not isinstance(tecla, str) or not tecla.strip():
        raise ValueError("La tecla debe ser un texto no vacío.")
    if not callable(funcion):
        raise ValueError("La acción asociada a la tecla debe poder ejecutarse.")
    _bindings[tecla.strip().lower()] = funcion


def iniciar() -> None:
    """Prepara el sonido y el subsistema de gamepads, sin crear listeners externos."""
    global _sonido

    ruta = RUTA_SONIDO
    if not os.path.isabs(ruta):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ruta)
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        _sonido = pygame.mixer.Sound(ruta)
    except (FileNotFoundError, pygame.error) as error:
        _sonido = None
        print(f"[acciones] No se pudo cargar el sonido '{ruta}': {error}")

    bindear("e", _reproducir_sonido)
    pygame.joystick.init()


class ControlEntrada:
    """Selecciona la entrada local y traduce teclado o controles SDL a direcciones."""

    UMBRAL_EJE = 0.5

    def __init__(self) -> None:
        pygame.joystick.init()
        self.modo = MODO_TECLADO
        self._teclas: set[int] = set()
        self._joystick: pygame.joystick.JoystickType | None = None
        self.aviso = ""
        _abajo.clear()
        self._abrir_primer_gamepad()

    @property
    def nombre_gamepad(self) -> str | None:
        if self._joystick is None:
            return None
        return self._joystick.get_name()

    @property
    def gamepad_conectado(self) -> bool:
        return self._joystick is not None

    def seleccionar(self, modo: str) -> None:
        if modo == MODO_TECLADO:
            self.modo = MODO_TECLADO
            self._teclas.clear()
            return
        if modo != MODO_GAMEPAD:
            raise ValueError("El control debe ser 'teclado' o 'gamepad'.")
        if self._joystick is None:
            self._abrir_primer_gamepad()
        if self._joystick is None:
            raise ValueError("No se detectó un gamepad. Conecta el MSI FORCE GC30 V2 e inténtalo de nuevo.")
        self.modo = MODO_GAMEPAD
        self._teclas.clear()

    def procesar_evento(self, evento: pygame.event.Event) -> None:
        if evento.type == pygame.KEYDOWN:
            nombre = pygame.key.name(evento.key).lower()
            if nombre not in _abajo:
                _abajo.add(nombre)
                accion = _bindings.get(nombre)
                if accion:
                    accion()
            self._teclas.add(evento.key)
        elif evento.type == pygame.KEYUP:
            nombre = pygame.key.name(evento.key).lower()
            _abajo.discard(nombre)
            self._teclas.discard(evento.key)
        elif (
            evento.type == pygame.JOYBUTTONDOWN
            and self.modo == MODO_GAMEPAD
            and self._joystick is not None
            and evento.instance_id == self._joystick.get_instance_id()
            and evento.button == BOTON_GAMEPAD_ACCION
        ):
            _reproducir_sonido()
        elif evento.type == pygame.WINDOWFOCUSLOST:
            self._teclas.clear()
            _abajo.clear()
        elif evento.type == pygame.JOYDEVICEADDED and self._joystick is None:
            try:
                self._abrir_primer_gamepad()
            except ValueError as error:
                self.aviso = str(error)
        elif evento.type == pygame.JOYDEVICEREMOVED:
            if self._joystick and evento.instance_id == self._joystick.get_instance_id():
                self._joystick.quit()
                self._joystick = None
                try:
                    self._abrir_primer_gamepad()
                except ValueError as error:
                    self.aviso = str(error)
                if self._joystick is None and self.modo == MODO_GAMEPAD:
                    self.modo = MODO_TECLADO
                    self.aviso = "Se desconectó el gamepad; se cambió al teclado."

    def direccion_actual(self) -> str | None:
        if self.modo == MODO_TECLADO:
            for tecla, direccion in _DIRECCIONES_TECLADO.items():
                if tecla in self._teclas:
                    return direccion
            return None
        if self._joystick is None:
            return None

        if self._joystick.get_numhats():
            x, y = self._joystick.get_hat(0)
            if y:
                return "up" if y > 0 else "down"
            if x:
                return "right" if x > 0 else "left"

        if self._joystick.get_numaxes() >= 2:
            x, y = self._joystick.get_axis(0), self._joystick.get_axis(1)
            if abs(x) >= self.UMBRAL_EJE or abs(y) >= self.UMBRAL_EJE:
                if abs(x) >= abs(y):
                    return "right" if x > 0 else "left"
                return "down" if y > 0 else "up"
        return None

    def _abrir_primer_gamepad(self) -> None:
        if self._joystick is not None:
            return
        try:
            if pygame.joystick.get_count() == 0:
                return
            joystick = pygame.joystick.Joystick(0)
            joystick.init()
        except pygame.error as error:
            raise ValueError(f"No se pudo iniciar el gamepad: {error}") from error
        self._joystick = joystick

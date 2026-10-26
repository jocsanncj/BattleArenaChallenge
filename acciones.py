import os

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame
from pynput import keyboard

# UBICACIÓN
RUTA_SONIDO = "Media/Efecto.mp3"

_bindings = {}    # {"w": funcion}
_abajo = set()    # Teclas apretadas (para ignorar la repetición al mantener)
_sonido = None


def _reproducir_sonido():
    if _sonido:
        _sonido.play()


def _nombre(tecla):
    """Convierte la tecla de pynput a texto: 'w', 'e', 'up', 'space'..."""
    caracter = getattr(tecla, "char", None)
    return caracter.lower() if caracter else getattr(tecla, "name", None)


def _al_presionar(tecla):
    nombre = _nombre(tecla)
    if nombre is None or nombre in _abajo:
        return
    _abajo.add(nombre)
    funcion = _bindings.get(nombre)
    if funcion:
        funcion()


def _al_soltar(tecla):
    _abajo.discard(_nombre(tecla))


def bindear(tecla, funcion):
    """Asocia una tecla ('w', 'up', 'space'...) a una función."""
    _bindings[tecla.lower()] = funcion


def iniciar():
    """Carga el sonido y empieza a escuchar el teclado en segundo plano."""
    global _sonido

    ruta = RUTA_SONIDO
    if not os.path.isabs(ruta):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ruta)
    try:
        pygame.mixer.init()
        _sonido = pygame.mixer.Sound(ruta)
    except (FileNotFoundError, pygame.error) as error:
        print(f"[teclado] No se pudo cargar el sonido '{ruta}': {error}")

    bindear("e", _reproducir_sonido)  # E = sonido

    escucha = keyboard.Listener(on_press=_al_presionar, on_release=_al_soltar)
    escucha.daemon = True  # Se cierra solo cuando termina tu programa
    escucha.start()
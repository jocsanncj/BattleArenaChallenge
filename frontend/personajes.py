"""Retratos para los paneles y figuras de cuerpo completo para el tablero."""
from functools import lru_cache
from pathlib import Path
import pygame
from shared.domain.avatares import NOMBRES_PERSONAJES as NOMBRES

MEDIA = Path(__file__).resolve().parents[1] / "Media"


@lru_cache(maxsize=96)
## @brief US-06 y US-07: carga y escala un retrato o sprite del catálogo.
def imagen(avatar_id, tam, tipo="retratos"):
    if avatar_id not in NOMBRES or tipo not in {"retratos", "personajes"}:
        raise ValueError("Personaje desconocido.")
    original = pygame.image.load(str(MEDIA / tipo / f"{avatar_id}.png"))
    return pygame.transform.smoothscale(original, (tam, tam))


## @brief US-06: obtiene la imagen correspondiente a la elección del usuario.
def de_usuario(servicio, uid, tam, tipo="retratos"):
    eleccion = servicio.obtener_eleccion(uid)
    if eleccion.tipo == "predeterminado" and eleccion.valor in NOMBRES:
        return imagen(eleccion.valor, tam, tipo)
    return servicio.obtener_superficie(uid, tam)

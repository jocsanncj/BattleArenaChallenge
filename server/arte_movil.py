"""Sirve el tablero de escritorio como PNG y las figuras de los guardianes para US30."""

from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pygame
from flask import Blueprint, abort, send_file, send_from_directory, url_for

from shared.arte_arena import PALETAS, PERIODO, reactor, tablero
from shared.escenarios import MAPAS


arte_movil = Blueprint("arte_movil", __name__)
GUARDIANES = Path(__file__).resolve().parents[1] / "Media" / "guardianes"
TIPOS_GUARDIAN = ("perseguidor", "vigilante")
LADO = 36


# Recibe los índices de escenario y paleta. Convierte una copia del tablero Pygame en bytes PNG y calcula
# su huella SHA-256. La caché reutiliza ambos valores cuando otro jugador solicita la misma combinación.
@lru_cache(maxsize=len(MAPAS) * len(PALETAS))
def _tablero_png(escenario, tema):
    # Se dibuja sobre una copia para conservar intacta la superficie que comparte el escritorio.
    mapa = MAPAS[escenario]
    superficie = tablero(mapa, tema, LADO).copy()
    reactor(superficie, mapa, tema, LADO, segundos=None)
    salida = BytesIO()
    pygame.image.save(superficie, salida, "tablero.png")
    contenido = salida.getvalue()
    return contenido, sha256(contenido).hexdigest()


# La URL elige un escenario y un tema del catálogo. Si existen, la respuesta lleva el PNG y su huella (ETag).
# Si el navegador envía la misma huella con If-None-Match, puede recibir 304 y reutilizar su copia local.
@arte_movil.get("/movil/arena/tableros/<int:escenario>/<int:tema>.png")
def imagen_tablero(escenario, tema):
    if escenario >= len(MAPAS) or tema >= len(PALETAS):
        abort(404)
    contenido, etiqueta = _tablero_png(escenario, tema)
    return send_file(BytesIO(contenido), mimetype="image/png", etag=etiqueta)


# El móvil usa el tipo comunicado por la arena para pedir la imagen del perseguidor o del vigilante.
# Ambos nombres identifican ficheros del juego. Cualquier otro tipo recibe un 404.
@arte_movil.get("/movil/arena/guardianes/<tipo>.png")
def imagen_guardian(tipo):
    if tipo not in TIPOS_GUARDIAN:
        abort(404)
    return send_from_directory(GUARDIANES, tipo + ".png")


# La plantilla de /movil llama a esta función y entrega el diccionario como JSON en arte-arena. El lienzo
# usa el tamaño de casilla, el centro del reactor y las URL por escenario y tema para dibujar a escala.
@arte_movil.app_template_global()
def catalogo_arte_arena():
    return {
        "lado": LADO,
        "periodo": PERIODO,
        "escenarios": [
            {
                "nombre": mapa.nombre,
                "centro": mapa.centro_reactor(),
                "tableros": [url_for("arte_movil.imagen_tablero", escenario=i, tema=t)
                             for t in range(len(PALETAS))],
            }
            for i, mapa in enumerate(MAPAS)
        ],
        "coloresLuz": ["#%02x%02x%02x" % paleta[-1] for paleta in PALETAS],
        "guardianes": {tipo: url_for("arte_movil.imagen_guardian", tipo=tipo)
                      for tipo in TIPOS_GUARDIAN},
    }

from io import BytesIO
import unittest

from flask import Flask
import pygame

from frontend import visual
from server.arte_movil import LADO, arte_movil, catalogo_arte_arena
from shared.escenarios import MAPAS


class ArteMovilTests(unittest.TestCase):
    def test_rotacion_mantiene_el_mapa_y_cambia_la_paleta_como_en_escritorio(self):
        app = Flask(__name__)
        app.register_blueprint(arte_movil)
        client = app.test_client()
        with app.test_request_context():
            catalogo = catalogo_arte_arena()
        for mapa, arte in zip(MAPAS, catalogo["escenarios"], strict=True):
            self.assertEqual(mapa.centro_reactor(), arte["centro"])
            self.assertEqual(len(arte["tableros"]), len(visual.PALETAS))
            for tema, ruta in enumerate(arte["tableros"]):
                with self.subTest(mapa=mapa.nombre, tema=tema), client.get(ruta) as respuesta:
                    self.assertEqual(respuesta.mimetype, "image/png")
                    recibido = pygame.image.load(BytesIO(respuesta.data), "tablero.png")
                    esperado = visual.tablero(mapa, tema, LADO).copy()
                    visual.reactor(esperado, mapa, tema, LADO, segundos=None)
                    self.assertEqual(pygame.image.tobytes(recibido, "RGB"), pygame.image.tobytes(esperado, "RGB"))
                    etag = respuesta.headers["ETag"]
                    self.assertEqual(client.get(ruta, headers={"If-None-Match": etag}).status_code, 304)

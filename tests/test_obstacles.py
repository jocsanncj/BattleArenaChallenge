"""Pruebas de aceptación de US-20: obstáculos de la arena."""
import unittest

from enum import Enum

from shared.game.obstacles import GestorObstaculos


class TipoCasilla(Enum):
    PISO = "."
    MURO = "#"
    REACTOR = "R"


class MapaPrueba:
    """Mapa pequeño independiente de la interfaz gráfica."""
    filas, columnas = 9, 13

    def __init__(self):
        self._inicio = [(1, 1), (11, 7), (1, 7), (11, 1)]
        self._reactor = {(6, 4)}

    def puntos_inicio(self):
        return list(self._inicio)

    def casilla_en(self, x, y):
        if (x, y) in self._reactor:
            return TipoCasilla.REACTOR
        if x in (0, self.columnas - 1) or y in (0, self.filas - 1):
            return TipoCasilla.MURO
        return TipoCasilla.PISO

    def es_transitable(self, x, y):
        return (0 <= x < self.columnas and 0 <= y < self.filas
                and self.casilla_en(x, y) is TipoCasilla.PISO)


class PruebasObstaculos(unittest.TestCase):
    def setUp(self):
        self.ahora = 100.0
        self.obstaculos = GestorObstaculos(
            MapaPrueba(),
            MapaPrueba().puntos_inicio()[:2],
            segundos_inmovilizacion=3,
            reloj=lambda: self.ahora,
            semilla=12,
        )

    def test_hay_tres_trampas_diferentes_y_una_puerta(self):
        estado = self.obstaculos.estado_publico(self.ahora)
        self.assertEqual(len(estado["trampas"]), 3)
        self.assertEqual(len({t["tipo"] for t in estado["trampas"]}), 3)
        self.assertEqual(len(estado["puertas"]), 1)

    def test_puerta_abierta_permite_y_cerrada_impide_el_paso(self):
        puerta = self.obstaculos.puertas[0]
        permitido, _ = self.obstaculos.validar_movimiento("jugador", puerta["x"], puerta["y"], self.ahora)
        self.assertTrue(permitido)
        puerta["abierta"] = False
        permitido, motivo = self.obstaculos.validar_movimiento("jugador", puerta["x"], puerta["y"], self.ahora)
        self.assertFalse(permitido)
        self.assertIn("puerta", motivo.lower())

    def test_limites_y_barreras_no_son_transitables(self):
        permitido, _ = self.obstaculos.validar_movimiento("jugador", 0, 0, self.ahora)
        self.assertFalse(permitido)

    def test_activar_trampa_inmoviliza_y_luego_libera(self):
        trampa = self.obstaculos.trampas[0]
        estado = self.obstaculos.activar_trampa("jugador", trampa.x, trampa.y, self.ahora)
        self.assertEqual(estado["estado"], "inmovilizado")
        permitido, motivo = self.obstaculos.validar_movimiento("jugador", trampa.x + 1, trampa.y, self.ahora + 1)
        self.assertFalse(permitido)
        self.assertIn("moverte", motivo.lower())
        permitido, _ = self.obstaculos.validar_movimiento(
            "jugador", trampa.x + 1, trampa.y, self.ahora + trampa.duracion + 0.1
        )
        self.assertTrue(permitido)

    def test_estado_de_puerta_se_actualiza_sin_recargar(self):
        puerta = self.obstaculos.puertas[0]
        estado_inicial = puerta["abierta"]
        self.obstaculos.actualizar(self.ahora + self.obstaculos.DURACION_PUERTA + 0.1)
        self.assertNotEqual(puerta["abierta"], estado_inicial)


if __name__ == "__main__":
    unittest.main()

"""Pruebas de aceptación de US-21: guardianes y estados temporales."""
import unittest
from enum import Enum

from shared.game.guardians import GestorGuardianes
from shared.game.obstacles import GestorObstaculos


class TipoCasilla(Enum):
    PISO = "."
    REACTOR = "R"


class MapaPrueba:
    filas, columnas = 9, 13

    def puntos_inicio(self):
        return [(1, 1), (11, 7), (1, 7), (11, 1)]

    def casilla_en(self, x, y):
        return TipoCasilla.REACTOR if (x, y) == (6, 4) else TipoCasilla.PISO

    def es_transitable(self, x, y):
        return 0 < x < self.columnas - 1 and 0 < y < self.filas - 1 and (x, y) != (6, 4)


class PruebasGuardianes(unittest.TestCase):
    def setUp(self):
        self.ahora = 100.0
        self.mapa = MapaPrueba()
        self.obstaculos = GestorObstaculos(
            self.mapa, self.mapa.puntos_inicio()[:2],
            reloj=lambda: self.ahora, semilla=7,
        )
        self.guardianes = GestorGuardianes(
            self.mapa, self.obstaculos, segundos_congelacion=3,
            reloj=lambda: self.ahora,
        )

    def test_hay_cuatro_guardianes_en_el_perimetro(self):
        self.assertEqual(len(self.guardianes.guardianes), 4)
        for guardian in self.guardianes.guardianes:
            self.assertTrue(0 < guardian["x"] < self.mapa.columnas - 1)
            self.assertTrue(0 < guardian["y"] < self.mapa.filas - 1)

    def test_velocidad_de_persecucion_es_moderada(self):
        self.assertGreater(self.guardianes.INTERVALO_MOVIMIENTO, 0.5)
        self.assertLess(self.guardianes.INTERVALO_MOVIMIENTO, 1.0)

    def test_evade_congelados_pero_puede_acumular_tiempo_en_trampas(self):
        self.obstaculos.aplicar_congelamiento("congelado", 5, self.ahora)
        self.obstaculos.activar_trampa(
            "inmovilizado",
            self.obstaculos.trampas[0].x,
            self.obstaculos.trampas[0].y,
            self.ahora,
        )
        jugadores = [
            {"player_id": "congelado", "x": 2, "y": 2, "connected": True},
            {"player_id": "inmovilizado", "x": 3, "y": 2, "connected": True},
            {"player_id": "libre", "x": 8, "y": 6, "connected": True},
        ]
        self.guardianes.actualizar(jugadores, self.ahora + 1.3)
        objetivos = {g["objetivo"] for g in self.guardianes.guardianes}
        self.assertNotIn("congelado", objetivos)
        # CA-21.10 permite que el guardián alcance a quien está en una trampa
        # y acumule ese tiempo; CA-21.11 excluye al que ya está congelado.
        self.assertIn("inmovilizado", objetivos)
        self.assertIn("libre", objetivos)


    def test_guardian_no_reaplica_congelamiento_sin_separarse(self):
        guardian = self.guardianes.guardianes[0]
        jugador = {"player_id": "p1", "x": guardian["x"], "y": guardian["y"], "connected": True}
        self.guardianes.actualizar([jugador], self.ahora + 1.3)
        primer_estado = self.obstaculos.estado_jugador("p1", self.ahora + 1.3)
        hasta_original = primer_estado["hasta"]
        self.guardianes.actualizar([jugador], self.ahora + 2.6)
        segundo_estado = self.obstaculos.estado_jugador("p1", self.ahora + 2.6)
        self.assertEqual(segundo_estado["hasta"], hasta_original)

    def test_guardian_comienza_separado_de_los_puntos_de_inicio(self):
        inicios = set(self.mapa.puntos_inicio())
        for guardian in self.guardianes.guardianes:
            self.assertNotIn((guardian["x"], guardian["y"]), inicios)
            self.assertGreaterEqual(
                min(abs(guardian["x"] - x) + abs(guardian["y"] - y) for x, y in inicios),
                2,
            )

if __name__ == "__main__":
    unittest.main()

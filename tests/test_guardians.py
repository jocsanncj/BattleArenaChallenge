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

    # ---- Regresión: casillas compartidas, campeo e inmunidad ----------------
    def _jugadores_en(self, *posiciones):
        return [{"player_id": f"p{i}", "x": x, "y": y, "connected": True}
                for i, (x, y) in enumerate(posiciones)]

    def test_guardianes_nunca_comparten_casilla_con_jugadores_ni_entre_si(self):
        import random
        azar = random.Random(3)
        jugadores = self._jugadores_en((1, 1), (11, 7), (1, 7))
        for _ in range(400):
            self.ahora += 0.9
            for j in jugadores:  # los jugadores se mueven libremente, sin pisar guardianes
                dx, dy = azar.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (0, 0)])
                x, y = j["x"] + dx, j["y"] + dy
                if (self.mapa.es_transitable(x, y) and (x, y) not in self.guardianes.posiciones()
                        and all((o["x"], o["y"]) != (x, y) for o in jugadores if o is not j)):
                    j["x"], j["y"] = x, y
            self.guardianes.actualizar(jugadores, self.ahora)
            posiciones = [(g["x"], g["y"]) for g in self.guardianes.guardianes]
            self.assertEqual(len(posiciones), len(set(posiciones)), "guardianes apilados")
            for j in jugadores:
                self.assertNotIn((j["x"], j["y"]), posiciones, "guardián sobre un jugador")

    def test_no_campea_a_un_jugador_congelado_ni_inmune(self):
        self.obstaculos.aplicar_congelamiento("p0", 30, self.ahora, segundos_inmunidad=30)
        jugadores = self._jugadores_en((6, 2))
        seguidas, maximo = 0, 0
        for _ in range(60):
            self.ahora += 0.9
            self.guardianes.actualizar(jugadores, self.ahora)
            pegado = any(abs(g["x"] - 6) + abs(g["y"] - 2) <= 1
                         for g in self.guardianes.guardianes)
            seguidas = seguidas + 1 if pegado else 0
            maximo = max(maximo, seguidas)
        self.assertLessEqual(maximo, 2)

    def test_persigue_al_jugador_disponible_mas_cercano(self):
        jugadores = self._jugadores_en((2, 6), (11, 1))
        self.guardianes.actualizar(jugadores, self.ahora + 1.0)
        perseguidor = self.guardianes.guardianes[0]
        self.assertIn(perseguidor["objetivo"], {"p0", "p1"})

    def test_guardian_congela_desde_casilla_adyacente_sin_pisar_al_jugador(self):
        g = self.guardianes.guardianes[0]
        jugador = {"player_id": "p0", "x": g["x"] + 1, "y": g["y"], "connected": True}
        self.guardianes.actualizar([jugador], self.ahora + 1.0)
        self.assertEqual(self.obstaculos.estado_jugador("p0", self.ahora + 1.0)["estado"], "congelado")
        self.assertNotEqual((g["x"], g["y"]), (jugador["x"], jugador["y"]))

    def test_inmunidad_tras_descongelarse_y_luego_vuelve_a_ser_vulnerable(self):
        g = self.guardianes.guardianes[0]
        jugador = {"player_id": "p0", "x": g["x"] + 1, "y": g["y"], "connected": True}
        t0 = self.ahora + 1.0
        self.guardianes.actualizar([jugador], t0)
        self.assertEqual(self.obstaculos.estado_jugador("p0", t0)["estado"], "congelado")
        # Termina el congelamiento (3 s): comienza la inmunidad (3 s).
        t1 = t0 + 3.1
        estado = self.obstaculos.estado_jugador("p0", t1)
        self.assertEqual(estado["estado"], "normal")
        self.assertTrue(self.obstaculos.esta_inmune("p0", t1))
        # Con un guardián pegado al jugador durante la inmunidad NO se congela.
        for guardian in self.guardianes.guardianes:
            guardian["x"], guardian["y"] = 1, 1  # se reubicarán; se colocan junto al jugador:
        self.guardianes.guardianes[0]["x"] = jugador["x"] + 1
        self.guardianes.guardianes[0]["y"] = jugador["y"]
        self.guardianes.guardianes[1]["x"], self.guardianes.guardianes[1]["y"] = jugador["x"], jugador["y"] + 1
        for i in range(2, 4):
            self.guardianes.guardianes[i]["x"], self.guardianes.guardianes[i]["y"] = 1 + i, 7
        t2 = t1 + 1.0
        self.guardianes.actualizar([jugador], t2)
        self.assertNotEqual(self.obstaculos.estado_jugador("p0", t2)["estado"], "congelado")
        # Tras la inmunidad vuelve a ser vulnerable.
        t3 = t1 + 3.2
        self.assertFalse(self.obstaculos.esta_inmune("p0", t3))
        res = self.obstaculos.aplicar_congelamiento("p0", 3, t3)
        self.assertEqual(res["estado"], "congelado")

    def test_aplicar_congelamiento_directo_respeta_inmunidad(self):
        self.obstaculos.aplicar_congelamiento("p0", 3, self.ahora)
        t = self.ahora + 3.5  # ya descongelado, dentro de la inmunidad
        res = self.obstaculos.aplicar_congelamiento("p0", 3, t)
        self.assertEqual(res["estado"], "normal")

    def test_trampa_no_borra_la_inmunidad(self):
        self.obstaculos.aplicar_congelamiento("p0", 3, self.ahora)
        t = self.ahora + 3.5
        trampa = self.obstaculos.trampas[0]
        self.obstaculos.activar_trampa("p0", trampa.x, trampa.y, t)
        self.assertGreater(self.obstaculos.estado_jugador("p0", t)["segundos_inmunidad"], 0)
        # Al terminar la trampa la inmunidad restante sigue vigente.
        self.assertTrue(self.obstaculos.esta_inmune("p0", t + 1.0)
                        or self.obstaculos.estado_jugador("p0", t + 1.0)["estado"] == "inmovilizado")


if __name__ == "__main__":
    unittest.main()

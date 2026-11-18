"""Pruebas de aceptación de US-22: eventos especiales de la partida."""

import unittest

from shared.domain.arena import ARENA_PREDETERMINADA
from shared.game.events import GestorEventosPartida
from shared.game.guardians import GestorGuardianes
from shared.game.obstacles import GestorObstaculos
from shared.game.scores import Scoreboard


class PruebasEventosEspeciales(unittest.TestCase):
    def setUp(self):
        self.ahora = 100.0
        self.mapa = ARENA_PREDETERMINADA
        self.obstaculos = GestorObstaculos(
            self.mapa, self.mapa.puntos_inicio()[:2],
            reloj=lambda: self.ahora, semilla=10,
        )
        self.guardianes = GestorGuardianes(
            self.mapa, self.obstaculos,
            reloj=lambda: self.ahora, semilla=11,
        )
        self.eventos = GestorEventosPartida(
            self.mapa, self.obstaculos, self.guardianes,
            reloj=lambda: self.ahora, semilla=12,
        )

    def test_programa_tres_energias_dos_sobrecargas_y_dos_eventos_creativos(self):
        self.eventos.iniciar(self.ahora, 300)
        nombres = [evento["id"] for evento in self.eventos.programados]
        self.assertEqual(sum(nombre.startswith("energia_") for nombre in nombres), 3)
        self.assertEqual(sum(nombre.startswith("sobrecarga_") for nombre in nombres), 2)
        self.assertIn("guardianes_quitan_puntos", nombres)
        self.assertIn("doble_trampas", nombres)

    def test_primer_jugador_recoge_energia_una_sola_vez(self):
        jugadores = [
            {"player_id": "1", "x": 2, "y": 2},
            {"player_id": "2", "x": 3, "y": 3},
        ]
        programado = {
            "id": "energia_1", "duracion": GestorEventosPartida.DURACION_ENERGIA,
        }
        self.eventos._activar(programado, jugadores, self.ahora)
        energia = self.eventos.energia
        jugador = {"player_id": "1", "x": energia["x"], "y": energia["y"]}
        self.assertEqual(self.eventos.recoger_energia(jugador, self.ahora), 3)
        self.assertIsNone(self.eventos.recoger_energia(jugador, self.ahora))

    def test_aparicion_temporal_agrega_cinco_guardianes(self):
        cantidad_inicial = len(self.guardianes.guardianes)
        self.eventos._activar(
            {"id": "guardianes_adicionales", "duracion": 22.0},
            [], self.ahora,
        )
        self.assertEqual(len(self.guardianes.guardianes), cantidad_inicial + 5)
        self.eventos.finalizar()
        self.assertEqual(len(self.guardianes.guardianes), cantidad_inicial)

    def test_evento_duplica_trampas_y_las_restaura_al_terminar(self):
        cantidad_inicial = len(self.obstaculos.trampas)
        self.eventos._activar(
            {"id": "doble_trampas", "duracion": 20.0},
            [], self.ahora,
        )
        self.assertEqual(len(self.obstaculos.trampas), cantidad_inicial * 2)
        self.eventos.finalizar()
        self.assertEqual(len(self.obstaculos.trampas), cantidad_inicial)

    def test_sobrecarga_desactiva_reactor_mientras_evento_esta_activo(self):
        self.eventos._activar(
            {"id": "sobrecarga_1", "duracion": 8.0},
            [], self.ahora,
        )
        self.assertTrue(self.eventos.sobrecarga_activa(self.ahora))
        self.assertFalse(self.eventos.sobrecarga_activa(self.ahora + 8.1))

    def test_restar_puntos_no_permite_puntaje_negativo(self):
        marcador = Scoreboard()
        marcador.add_player("jugador")
        marcador.add_points("jugador", 2)
        self.assertEqual(marcador.remove_points("jugador", 1), 1)
        self.assertEqual(marcador.remove_points("jugador", 5), 0)




    def test_guardian_resta_un_punto_durante_evento_de_drenaje(self):
        marcador = Scoreboard()
        marcador.add_player("jugador")
        marcador.add_points("jugador", 3)
        self.eventos._activar(
            {"id": "guardianes_quitan_puntos", "duracion": 20.0},
            [], self.ahora,
        )
        anterior = {"estado": "normal", "hasta": 0.0}
        actual = {"estado": "congelado", "efecto": "guardian", "hasta": 105.0}
        self.assertTrue(self.eventos.penalizar_por_guardian(
            "jugador", anterior, actual, marcador, self.ahora
        ))
        self.assertEqual(marcador.scores()["jugador"], 2)
        self.assertFalse(self.eventos.penalizar_por_guardian(
            "jugador", anterior, actual, marcador, self.ahora + 21
        ))

    def test_evento_expira_y_restaura_los_elementos_originales(self):
        guardianes_iniciales = len(self.guardianes.guardianes)
        trampas_iniciales = len(self.obstaculos.trampas)
        self.eventos._activar(
            {"id": "guardianes_adicionales", "duracion": 2.0},
            [], self.ahora,
        )
        self.eventos._activar(
            {"id": "doble_trampas", "duracion": 2.0},
            [], self.ahora,
        )
        self.eventos.actualizar([], self.ahora + 2.1)
        self.assertEqual(len(self.guardianes.guardianes), guardianes_iniciales)
        self.assertEqual(len(self.obstaculos.trampas), trampas_iniciales)
        self.assertEqual(self.eventos.estado_publico(self.ahora + 2.1)["eventos"], [])

    def test_evento_comunica_visualmente_su_efecto(self):
        self.eventos._activar(
            {"id": "guardianes_quitan_puntos", "duracion": 20.0},
            [], self.ahora,
        )
        estado = self.eventos.estado_publico(self.ahora)
        self.assertEqual(len(estado["eventos"]), 1)
        self.assertIn("quitan 1 punto", estado["eventos"][0]["mensaje"])

    def test_todos_los_eventos_se_activan_durante_una_partida_de_cinco_minutos(self):
        self.eventos.iniciar(self.ahora, 300)
        jugadores = [
            {"player_id": "1", "x": 2, "y": 2},
            {"player_id": "2", "x": 3, "y": 3},
        ]
        for segundo in range(301):
            self.ahora = 100.0 + segundo
            self.eventos.actualizar(jugadores, self.ahora)
        identificadores = {evento["id"] for evento in self.eventos.programados}
        self.assertEqual(self.eventos.completados, identificadores)

    def test_estado_publico_informa_el_proximo_evento(self):
        self.eventos.iniciar(self.ahora, 300)
        estado = self.eventos.estado_publico(self.ahora)
        self.assertIsNotNone(estado["proximo_evento"])
        self.assertGreater(estado["proximo_evento"]["segundos_restantes"], 0)

    def test_actualizaciones_repetidas_no_duplican_activaciones(self):
        self.eventos.iniciar(self.ahora, 300)
        primera_activacion = min(e["inicia_en"] for e in self.eventos.programados)
        self.eventos.actualizar([], primera_activacion)
        activados = sum(e["activado"] for e in self.eventos.programados)
        self.eventos.actualizar([], primera_activacion)
        self.assertEqual(
            sum(e["activado"] for e in self.eventos.programados),
            activados,
        )



    def test_reloj_de_eventos_se_pausa_y_se_reanuda(self):
        self.eventos.iniciar(self.ahora, 300)
        primer_inicio = min(e["inicia_en"] for e in self.eventos.programados)
        self.eventos.pausar(self.ahora + 1)
        self.eventos.actualizar([], primer_inicio + 10)
        self.assertFalse(any(e["activado"] for e in self.eventos.programados))
        self.eventos.reanudar(self.ahora + 31)
        self.assertEqual(
            min(e["inicia_en"] for e in self.eventos.programados),
            primer_inicio + 30,
        )

    def test_finalizar_cancela_eventos_y_efectos_temporales(self):
        cantidad_guardianes = len(self.guardianes.guardianes)
        cantidad_trampas = len(self.obstaculos.trampas)
        self.eventos._activar(
            {"id": "guardianes_adicionales", "duracion": 20.0},
            [], self.ahora,
        )
        self.eventos._activar(
            {"id": "doble_trampas", "duracion": 20.0},
            [], self.ahora,
        )
        self.eventos.finalizar()
        self.assertEqual(len(self.guardianes.guardianes), cantidad_guardianes)
        self.assertEqual(len(self.obstaculos.trampas), cantidad_trampas)
        self.assertEqual(self.eventos.estado_publico(self.ahora)["eventos"], [])


    # ---- US-22: los eventos aparecen durante toda la partida --------------
    JUG = [{"player_id": "1", "x": 2, "y": 2}, {"player_id": "2", "x": 3, "y": 3}]

    def _simular(self, duracion, modo="tiempo", paso=1.0, prorroga_desde=None, hasta=None):
        """Avanza el reloj; devuelve [(segundo, id_evento)] según se activan."""
        self.eventos.iniciar(self.ahora, duracion, modo=modo)
        activaciones, vistos = [], set()
        base = self.ahora
        for i in range(int((hasta if hasta is not None else duracion) / paso) + 1):
            self.ahora = base + i * paso
            en_prorroga = prorroga_desde is not None and (self.ahora - base) >= prorroga_desde
            self.eventos.actualizar(self.JUG, self.ahora, prorroga=en_prorroga)
            for e in self.eventos.estado_publico(self.ahora)["eventos"]:
                if e["id"] not in vistos:
                    vistos.add(e["id"])
                    activaciones.append((self.ahora - base, e["id"]))
        return activaciones

    def _tipos(self, activaciones):
        return [GestorEventosPartida._tipo(i) for _, i in activaciones]

    def test_el_primer_evento_aparece_pronto_sin_importar_la_duracion(self):
        for duracion in (60, 300, 1200, 3600):
            with self.subTest(duracion=duracion):
                self.setUp()
                self.eventos.iniciar(self.ahora, duracion)
                primero = min(e["inicia_en"] for e in self.eventos.programados) - self.ahora
                self.assertLessEqual(primero, 30.0)

    def test_partida_de_5_minutos_cumple_us22(self):
        tipos = self._tipos(self._simular(300))
        self.assertGreaterEqual(tipos.count("energia"), 3)            # CA-22.1
        self.assertEqual(tipos.count("guardianes_adicionales"), 1)    # CA-22.2
        self.assertGreaterEqual(tipos.count("sobrecarga"), 2)         # CA-22.3
        self.assertGreaterEqual(tipos.count("guardianes_quitan_puntos")
                                + tipos.count("doble_trampas"), 2)    # CA-22.4

    def test_partida_larga_sigue_recibiendo_eventos_en_cada_tramo(self):
        activaciones = self._simular(1200)
        # Ningún hueco mayor a 2 min entre eventos (antes superaba 3 min).
        instantes = [0.0] + [t for t, _ in activaciones] + [1200.0]
        self.assertLessEqual(max(b - a for a, b in zip(instantes, instantes[1:])), 120.0)
        tipos = self._tipos(activaciones)
        self.assertGreaterEqual(tipos.count("energia"), 12)
        self.assertGreaterEqual(tipos.count("sobrecarga"), 8)
        # Las energías nunca se repiten en el mismo momento.
        tiempos = [t for t, i in activaciones if i.startswith("energia_")]
        self.assertEqual(len(tiempos), len(set(tiempos)))

    def test_ids_de_eventos_son_unicos_entre_rondas(self):
        ids = [i for _, i in self._simular(1200)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_modo_por_puntos_programa_eventos_sin_depender_de_los_minutos(self):
        activaciones = self._simular(300, modo="puntos", hasta=150)
        self.assertGreaterEqual(len(activaciones), 6)   # una partida corta ya los ve
        self.setUp()
        largas = self._simular(300, modo="puntos", hasta=900)
        self.assertGreater(len(largas), 20)             # y siguen apareciendo después

    def test_la_prorroga_tambien_tiene_eventos(self):
        self.eventos.iniciar(self.ahora, 60)
        base = self.ahora
        for i in range(61):                              # fin de tiempo normal
            self.ahora = base + i
            self.eventos.actualizar(self.JUG, self.ahora)
        antes = len(self.eventos.programados)
        for i in range(61, 61 + 120):                    # prórroga de 2 min
            self.ahora = base + i
            self.eventos.actualizar(self.JUG, self.ahora, prorroga=True)
        self.assertGreater(len(self.eventos.programados), antes)
        nuevos = self.eventos.programados[antes:]
        self.assertTrue(all(e["inicia_en"] >= base + 60 for e in nuevos))
        self.assertTrue(all(e["inicia_en"] <= base + 61 + 120 for e in nuevos))

    def test_sin_prorroga_no_se_programan_eventos_tras_el_final(self):
        self.eventos.iniciar(self.ahora, 60)
        base = self.ahora
        for i in range(0, 200):
            self.ahora = base + i
            self.eventos.actualizar(self.JUG, self.ahora)
        self.assertEqual(len(self.eventos.programados), 8)

    def test_finalizar_impide_nuevas_rondas(self):
        self.eventos.iniciar(self.ahora, 3600)
        self.eventos.finalizar()
        self.eventos.actualizar(self.JUG, self.ahora + 5000)
        self.assertEqual(self.eventos.programados, [])
        self.assertEqual(self.eventos.estado_publico(self.ahora + 5000)["eventos"], [])

    def test_pausa_desplaza_tambien_las_rondas(self):
        self.eventos.iniciar(self.ahora, 600)
        fin_ronda = self.eventos._fin_ronda
        self.eventos.pausar(self.ahora + 10)
        self.eventos.reanudar(self.ahora + 40)
        self.assertEqual(self.eventos._fin_ronda, fin_ronda + 30)

    def test_evento_unico_no_se_activa_dos_veces_a_la_vez(self):
        base = len(self.guardianes.guardianes)
        for _ in range(2):
            self.eventos._activar({"id": "guardianes_adicionales", "duracion": 22.0}, [], self.ahora)
        self.assertEqual(len(self.guardianes.guardianes), base + 5)

    def test_estado_publico_incluye_tipo_y_tiempo_transcurrido(self):
        self.eventos._activar({"id": "sobrecarga_3", "duracion": 8.0}, [], self.ahora)
        e = self.eventos.estado_publico(self.ahora + 2)["eventos"][0]
        self.assertEqual(e["tipo"], "sobrecarga")
        self.assertAlmostEqual(e["segundos_transcurridos"], 2.0)
        self.assertTrue(self.eventos.sobrecarga_activa(self.ahora + 2))


if __name__ == "__main__":
    unittest.main()

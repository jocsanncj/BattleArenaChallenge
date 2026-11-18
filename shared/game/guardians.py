"""Comportamiento autoritativo de los guardianes de la arena (US-21)."""
from __future__ import annotations

from collections import deque
import time
from typing import Callable


class GestorGuardianes:
    """Administra cuatro guardianes que persiguen al jugador elegible más cercano.

    Los guardianes avanzan una casilla cada INTERVALO_MOVIMIENTO segundos por
    rutas transitables. Al alcanzar a un jugador, lo congela durante el tiempo
    configurado. Si ya estaba inmovilizado por una trampa, el tiempo se suma.
    Un jugador congelado por un guardián no es seleccionado como objetivo.
    """

    INTERVALO_MOVIMIENTO = 0.45

    def __init__(self, mapa, obstaculos, segundos_congelacion=3,
                 reloj: Callable[[], float] = time.monotonic):
        self.mapa = mapa
        self.obstaculos = obstaculos
        self.reloj = reloj
        self.segundos_congelacion = max(1.0, float(segundos_congelacion))
        self._ultimo_movimiento = reloj()
        self.guardianes = []
        esquinas = ((1, 2), (mapa.columnas - 2, 2),
                    (1, mapa.filas - 3), (mapa.columnas - 2, mapa.filas - 3))
        reservadas = set(mapa.puntos_inicio())
        reservadas.update((t.x, t.y) for t in obstaculos.trampas)
        reservadas.update((p["x"], p["y"]) for p in obstaculos.puertas)
        for indice, posicion in enumerate(esquinas, 1):
            ubicacion = posicion if mapa.es_transitable(*posicion) and posicion not in reservadas else self._buscar_cercana(posicion, reservadas)
            if ubicacion is None:
                raise ValueError("No hay espacio suficiente para colocar los cuatro guardianes.")
            reservadas.add(ubicacion)
            self.guardianes.append({"id": f"guardian_{indice}", "x": ubicacion[0],
                                    "y": ubicacion[1], "objetivo": None})

    def _buscar_cercana(self, origen, reservadas):
        candidatas = [(x, y) for y in range(1, self.mapa.filas - 1)
                      for x in range(1, self.mapa.columnas - 1)
                      if self.mapa.es_transitable(x, y) and (x, y) not in reservadas]
        return min(candidatas, key=lambda p: abs(p[0] - origen[0]) + abs(p[1] - origen[1]), default=None)

    def _ruta_siguiente_paso(self, origen, destino):
        """Devuelve el primer paso de una ruta BFS que evita muros, reactor y barreras."""
        cola = deque([(origen, None)])
        visitadas = {origen}
        while cola:
            actual, primer_paso = cola.popleft()
            if actual == destino:
                return primer_paso
            x, y = actual
            for siguiente in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if siguiente in visitadas or not self.mapa.es_transitable(*siguiente):
                    continue
                visitadas.add(siguiente)
                cola.append((siguiente, siguiente if primer_paso is None else primer_paso))
        return None

    def actualizar(self, jugadores, ahora=None):
        """Mueve guardianes, detecta alcances y devuelve su estado público."""
        ahora = self.reloj() if ahora is None else ahora
        if ahora - self._ultimo_movimiento >= self.INTERVALO_MOVIMIENTO:
            # Se avanza como máximo una casilla por actualización para mantener una velocidad estable.
            self._ultimo_movimiento = ahora
            for guardian in self.guardianes:
                # Se vuelve a calcular después de cada guardián: si uno congela a
                # un jugador, los siguientes deben buscar a otro participante.
                elegibles = []
                for jugador in jugadores:
                    estado = self.obstaculos.estado_jugador(jugador["player_id"], ahora)
                    if jugador.get("connected", True) and estado["estado"] != "congelado":
                        elegibles.append(jugador)
                if not elegibles:
                    guardian["objetivo"] = None
                    continue
                objetivo = min(elegibles, key=lambda j: (
                    abs(guardian["x"] - int(j["x"])) + abs(guardian["y"] - int(j["y"])),
                    str(j["player_id"])))
                guardian["objetivo"] = objetivo["player_id"]
                destino = (int(objetivo["x"]), int(objetivo["y"]))
                origen = (guardian["x"], guardian["y"])
                paso = self._ruta_siguiente_paso(origen, destino)
                if paso is not None:
                    guardian["x"], guardian["y"] = paso
                if (guardian["x"], guardian["y"]) == destino:
                    self.obstaculos.aplicar_congelamiento(
                        objetivo["player_id"], self.segundos_congelacion, ahora,
                        "Un guardián te ha alcanzado")
        return self.estado_publico(jugadores, ahora)

    def estado_publico(self, jugadores=(), ahora=None):
        ahora = self.reloj() if ahora is None else ahora
        jugadores_por_id = {j["player_id"]: j for j in jugadores}
        resultado = []
        for guardian in self.guardianes:
            copia = guardian.copy()
            objetivo = jugadores_por_id.get(copia["objetivo"])
            if objetivo is None:
                copia["objetivo"] = None
            resultado.append(copia)
        return resultado

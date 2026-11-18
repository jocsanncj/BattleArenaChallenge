"""Comportamiento autoritativo de los guardianes de la arena (US-21)."""
from __future__ import annotations

import random
import time
from typing import Callable


class GestorGuardianes:
    """Administra dos guardianes perseguidores y dos guardianes vigilantes.

    Los perseguidores buscan jugadores disponibles de forma poco precisa.
    Los vigilantes se mantienen en zonas diferentes y se mueven aleatoriamente
    dentro de ellas. Al congelar a un jugador, el guardián se teletransporta
    a una esquina para evitar que permanezca junto a él.
    """

    INTERVALO_MOVIMIENTO = 0.8
    RADIO_VIGILANCIA = 4

    def __init__(self, mapa, obstaculos, segundos_congelacion=3,
                 reloj: Callable[[], float] = time.monotonic, semilla=None,
                 segundos_inmunidad=3):
        self.mapa = mapa
        self.obstaculos = obstaculos
        self.reloj = reloj
        self.aleatorio = random.Random(semilla)
        self.segundos_congelacion = max(1.0, float(segundos_congelacion))
        self.segundos_inmunidad = max(1.0, float(segundos_inmunidad))
        self._ultimo_movimiento = reloj()
        self.guardianes = []
        self._esquinas = self._obtener_esquinas()

        reservadas = set(mapa.puntos_inicio())
        reservadas.update((t.x, t.y) for t in obstaculos.trampas)
        reservadas.update((p["x"], p["y"]) for p in obstaculos.puertas)
        posiciones = self._buscar_posiciones_centro(4, reservadas)
        if len(posiciones) < 4:
            raise ValueError("No hay espacio suficiente para colocar los cuatro guardianes.")

        for indice, (x, y) in enumerate(posiciones, 1):
            tipo = "perseguidor" if indice <= 2 else "vigilante"
            guardian = {"id": f"guardian_{indice}", "x": x, "y": y,
                       "tipo": tipo, "objetivo": None}
            if tipo == "vigilante":
                centro = self._elegir_centro_vigilancia(guardian)
                guardian["zona"] = {"x": centro[0], "y": centro[1],
                                    "radio": self.RADIO_VIGILANCIA}
            self.guardianes.append(guardian)

    def _obtener_esquinas(self):
        mx = min(2, max(1, self.mapa.columnas // 5))
        my = min(2, max(1, self.mapa.filas // 5))
        return ((mx, my), (self.mapa.columnas - 1 - mx, my),
                (mx, self.mapa.filas - 1 - my),
                (self.mapa.columnas - 1 - mx, self.mapa.filas - 1 - my))

    def _reservadas(self):
        reservadas = set(self.mapa.puntos_inicio())
        reservadas.update((t.x, t.y) for t in self.obstaculos.trampas)
        reservadas.update((p["x"], p["y"]) for p in self.obstaculos.puertas)
        return reservadas

    def _casillas_validas(self, reservadas=()):
        reservadas = set(reservadas)
        return [(x, y) for y in range(1, self.mapa.filas - 1)
                for x in range(1, self.mapa.columnas - 1)
                if self.mapa.es_transitable(x, y) and (x, y) not in reservadas]

    def _buscar_posiciones_centro(self, cantidad, reservadas):
        cx, cy = (self.mapa.columnas - 1) / 2, (self.mapa.filas - 1) / 2
        candidatas = self._casillas_validas(reservadas)
        candidatas.sort(key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, p[1], p[0]))
        return candidatas[:cantidad]

    def _elegir_centro_vigilancia(self, guardian):
        otros = [g.get("zona") for g in self.guardianes if g.get("zona")]
        ocupadas = {(g["x"], g["y"]) for g in self.guardianes}
        opciones = self._casillas_validas(self._reservadas() | ocupadas)
        if not opciones:
            return (guardian["x"], guardian["y"])
        # Escoge zonas separadas para que los dos vigilantes no patrullen juntos.
        separadas = [p for p in opciones if all(
            abs(p[0] - z["x"]) + abs(p[1] - z["y"]) >= self.RADIO_VIGILANCIA * 2
            for z in otros)]
        return self.aleatorio.choice(separadas or opciones)

    def _casillas_vecinas(self, x, y):
        candidatas = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        return [p for p in candidatas if self.mapa.es_transitable(*p)]

    def _teletransportar_a_esquina(self, guardian):
        ocupadas = {(g["x"], g["y"]) for g in self.guardianes if g is not guardian}
        reservadas = self._reservadas()
        opciones = [p for p in self._esquinas if self.mapa.es_transitable(*p)
                    and p not in ocupadas and p not in reservadas]
        if not opciones:
            opciones = self._casillas_validas(reservadas | ocupadas)
        if opciones:
            x, y = self.aleatorio.choice(opciones)
            guardian["x"], guardian["y"] = x, y
        guardian["objetivo"] = None

    def _jugador_disponible(self, jugador, ahora):
        """Solo considera jugadores libres y cuya inmunidad ya terminó."""
        estado = self.obstaculos.estado_jugador(str(jugador["player_id"]), ahora)
        # Se excluyen congelados e inmunes. Un jugador inmovilizado por una
        # trampa sí puede seguir siendo objetivo: el tiempo del guardián se
        # acumula sobre el tiempo restante de la trampa.
        return (
            estado.get("estado", "normal") != "congelado"
            and estado.get("segundos_inmunidad", 0.0) <= 0.0
        )

    def _mover_perseguidor(self, guardian, jugadores, ahora, objetivos_asignados=None):
        disponibles = [j for j in jugadores if self._jugador_disponible(j, ahora)]
        # Evita que ambos perseguidores elijan al mismo jugador cuando hay
        # al menos dos objetivos disponibles. Si solo queda uno, ambos pueden
        # perseguirlo.
        if objetivos_asignados:
            sin_asignar = [j for j in disponibles
                           if str(j["player_id"]) not in objetivos_asignados]
            if sin_asignar:
                disponibles = sin_asignar
        if not disponibles:
            # No se queda esperando junto a un jugador congelado.
            guardian["objetivo"] = None
            self._mover_sin_objetivo(guardian)
            return

        objetivo = self.aleatorio.choice(disponibles)
        guardian["objetivo"] = str(objetivo["player_id"])
        if objetivos_asignados is not None:
            objetivos_asignados.add(str(objetivo["player_id"]))
        destino_jugador = (int(objetivo["x"]), int(objetivo["y"]))
        vecinos = self._casillas_vecinas(guardian["x"], guardian["y"])
        if not vecinos:
            return

        # Nunca se coloca al guardián sobre la casilla del jugador.
        # Si el siguiente paso sería alcanzarlo, lo congela desde la casilla
        # adyacente y se teletransporta sin ocupar su posición.
        if destino_jugador in vecinos and self.aleatorio.random() < 0.30:
            self._congelar_y_reubicar(guardian, objetivo, ahora)
            return

        # Movimiento deliberadamente poco inteligente: mayormente aleatorio.
        opciones = [p for p in vecinos if p != destino_jugador]
        if not opciones:
            # No hay una casilla segura: no se mueve encima del jugador.
            self._congelar_y_reubicar(guardian, objetivo, ahora)
            return
        if self.aleatorio.random() < 0.30:
            distancia = min(
                abs(x - destino_jugador[0]) + abs(y - destino_jugador[1])
                for x, y in opciones
            )
            mejores = [p for p in opciones
                       if abs(p[0] - destino_jugador[0]) +
                       abs(p[1] - destino_jugador[1]) == distancia]
            siguiente = self.aleatorio.choice(mejores)
        else:
            siguiente = self.aleatorio.choice(opciones)
        guardian["x"], guardian["y"] = siguiente

    def _mover_sin_objetivo(self, guardian):
        vecinos = self._casillas_vecinas(guardian["x"], guardian["y"])
        ocupadas_jugadores = getattr(self, "_posiciones_jugadores", set())
        opciones = [p for p in vecinos if p not in ocupadas_jugadores]
        if opciones:
            guardian["x"], guardian["y"] = self.aleatorio.choice(opciones)

    def _congelar_y_reubicar(self, guardian, jugador, ahora):
        jid = str(jugador["player_id"])
        if not self._jugador_disponible(jugador, ahora):
            guardian["objetivo"] = None
            self._teletransportar_a_esquina(guardian)
            return
        self.obstaculos.aplicar_congelamiento(
            jid, self.segundos_congelacion, ahora,
            "Un guardián te ha alcanzado",
            segundos_inmunidad=self.segundos_inmunidad,
        )
        guardian["objetivo"] = None
        self._teletransportar_a_esquina(guardian)

    def _mover_vigilante(self, guardian):
        zona = guardian["zona"]
        vecinos = self._casillas_vecinas(guardian["x"], guardian["y"])
        dentro = [p for p in vecinos
                  if p not in getattr(self, "_posiciones_jugadores", set())
                  and abs(p[0] - zona["x"]) <= zona["radio"]
                  and abs(p[1] - zona["y"]) <= zona["radio"]]
        vecinos = [p for p in vecinos
                   if p not in getattr(self, "_posiciones_jugadores", set())]
        if dentro and self.aleatorio.random() < 0.85:
            siguiente = self.aleatorio.choice(dentro)
        else:
            # Si llegó al borde, da un paso hacia su zona; nunca persigue jugadores.
            opciones = dentro or vecinos
            if not opciones:
                return
            siguiente = min(opciones, key=lambda p: (
                abs(p[0] - zona["x"]) + abs(p[1] - zona["y"]) + self.aleatorio.random() * 2
            ))
        guardian["x"], guardian["y"] = siguiente
        guardian["objetivo"] = None

    def actualizar(self, jugadores, ahora=None):
        ahora = self.reloj() if ahora is None else ahora
        if ahora - self._ultimo_movimiento < self.INTERVALO_MOVIMIENTO:
            return self.estado_publico(jugadores, ahora)
        self._ultimo_movimiento = ahora
        conectados = [j for j in jugadores if j.get("connected", True)]
        self._posiciones_jugadores = {
            (int(j["x"]), int(j["y"])) for j in conectados
        }

        objetivos_asignados = set()
        for guardian in self.guardianes:
            # Si por un estado previo quedó encima de un jugador, se retira
            # inmediatamente. Nunca se queda ocupando esa casilla.
            jugador_en_casilla = next((
                j for j in conectados
                if (int(j["x"]), int(j["y"])) == (guardian["x"], guardian["y"])
            ), None)
            if jugador_en_casilla is not None:
                if self._jugador_disponible(jugador_en_casilla, ahora):
                    self._congelar_y_reubicar(guardian, jugador_en_casilla, ahora)
                else:
                    guardian["objetivo"] = None
                    self._teletransportar_a_esquina(guardian)
                continue

            if guardian["tipo"] == "perseguidor":
                self._mover_perseguidor(guardian, conectados, ahora, objetivos_asignados)
            else:
                self._mover_vigilante(guardian)


        return self.estado_publico(jugadores, ahora)

    def estado_publico(self, jugadores=(), ahora=None):
        resultado = []
        for guardian in self.guardianes:
            copia = guardian.copy()
            if not any(str(j["player_id"]) == str(copia["objetivo"]) for j in jugadores):
                copia["objetivo"] = None
            resultado.append(copia)
        return resultado

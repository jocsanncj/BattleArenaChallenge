"""Comportamiento autoritativo de los guardianes de la arena (US-21)."""
from __future__ import annotations

from collections import deque
import random
import time
from typing import Callable


def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class GestorGuardianes:
    """Administra dos guardianes perseguidores y dos guardianes vigilantes.

    Reglas de convivencia (servidor autoritativo):
    - Un guardián NUNCA ocupa la casilla de un jugador (en cualquier estado)
      ni la de otro guardián. Congela desde una casilla adyacente.
    - Los perseguidores se dirigen, por el camino más corto, al jugador
      disponible más cercano (CA-21.11). Un jugador congelado o inmune no es
      objetivo y los guardianes se alejan de él en lugar de campearlo.
    - Los vigilantes patrullan su zona y solo congelan a quien se acerque
      a ella; nunca salen a perseguir.
    - Tras congelar, el guardián se reubica lejos de los jugadores.
    - Un guardián que permanece cerca de un jugador inmune/congelado o que
      queda inmóvil varias actualizaciones seguidas se reubica (anti-campeo).
    """

    # Actualizaciones seguidas junto a un jugador no disponible antes de reubicar.
    MAX_ACTUALIZACIONES_CERCA = 2
    # Actualizaciones seguidas sin moverse antes de reubicar.
    MAX_ACTUALIZACIONES_QUIETO = 3
    # Probabilidad de dar un paso aleatorio en vez del óptimo (poco precisos).
    PROB_PASO_ALEATORIO = 0.15

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
        self._memoria = {}
        self._conectados = []

        reservadas = set(mapa.puntos_inicio())
        reservadas.update((t.x, t.y) for t in obstaculos.trampas)
        reservadas.update((p["x"], p["y"]) for p in obstaculos.puertas)
        posiciones = self._buscar_posiciones_extremos(4, reservadas)
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

    def _puntos_extremos(self):
        """Puntos medios de los cuatro bordes de la zona jugable (arriba, abajo, izquierda, derecha).

        Las esquinas quedan libres porque son los puntos de inicio de los jugadores.
        """
        cx, cy = (self.mapa.columnas - 1) / 2, (self.mapa.filas - 1) / 2
        return ((cx, 1), (cx, self.mapa.filas - 2),
                (1, cy), (self.mapa.columnas - 2, cy))

    def _buscar_posiciones_extremos(self, cantidad, reservadas):
        """Coloca los guardianes en los extremos del escenario, lejos del reactor del centro.

        Para cada extremo elige la casilla válida libre más cercana; si está ocupada o
        reservada (trampa, puerta, inicio), usa la siguiente más próxima.
        """
        libres = self._casillas_validas(reservadas)
        elegidas = []
        for objetivo in self._puntos_extremos()[:cantidad]:
            disponibles = [p for p in libres if p not in elegidas]
            if not disponibles:
                break
            elegidas.append(min(disponibles, key=lambda p: (
                (p[0] - objetivo[0]) ** 2 + (p[1] - objetivo[1]) ** 2, p[1], p[0])))
        return elegidas

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

    # ------------------------------------------------------------------
    # Utilidades de consulta
    # ------------------------------------------------------------------
    def posiciones(self):
        """Casillas ocupadas por guardianes (el servidor las usa para bloquear a jugadores)."""
        return {(g["x"], g["y"]) for g in self.guardianes}

    def _memoria_de(self, guardian):
        return self._memoria.setdefault(
            guardian["id"], {"cerca": 0, "quieto": 0, "ultima": (guardian["x"], guardian["y"])})

    def _jugador_disponible(self, jugador, ahora):
        """Solo considera jugadores libres y cuya inmunidad ya terminó."""
        estado = self.obstaculos.estado_jugador(str(jugador["player_id"]), ahora)
        # Se excluyen congelados e inmunes. Un jugador inmovilizado por una
        # trampa sí puede seguir siendo objetivo: el tiempo del guardián se
        # acumula sobre el tiempo restante de la trampa (CA-21.10).
        return (
            estado.get("estado", "normal") != "congelado"
            and estado.get("segundos_inmunidad", 0.0) <= 0.0
        )

    def _clasificar(self, ahora):
        disponibles, no_disponibles = [], []
        for j in self._conectados:
            (disponibles if self._jugador_disponible(j, ahora) else no_disponibles).append(j)
        return disponibles, no_disponibles

    @staticmethod
    def _pos(jugador):
        return (int(jugador["x"]), int(jugador["y"]))

    def _zona_evitada(self, no_disponibles):
        """Casillas de un jugador congelado/inmune y las contiguas: no se campean."""
        evitar = set()
        for j in no_disponibles:
            x, y = self._pos(j)
            evitar.update({(x, y), (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)})
        return evitar

    def _otros_guardianes(self, guardian):
        return {(g["x"], g["y"]) for g in self.guardianes if g is not guardian}

    # ------------------------------------------------------------------
    # Rutas y reubicación
    # ------------------------------------------------------------------
    def _mapa_distancias(self, origen, bloqueadas, terminales):
        """BFS desde ``origen``. Las casillas de jugadores son terminales: se
        pueden alcanzar, pero nunca se atraviesan ni se pisan."""
        distancia, padre = {origen: 0}, {origen: None}
        cola = deque([origen])
        while cola:
            actual = cola.popleft()
            if actual in terminales and actual != origen:
                continue
            for vecino in self._casillas_vecinas(*actual):
                if vecino in distancia:
                    continue
                if vecino in bloqueadas and vecino not in terminales:
                    continue
                distancia[vecino] = distancia[actual] + 1
                padre[vecino] = actual
                cola.append(vecino)
        return distancia, padre

    @staticmethod
    def _primer_paso(padre, origen, destino):
        actual = destino
        while padre[actual] != origen:
            actual = padre[actual]
        return actual

    def _reubicar(self, guardian):
        """Teletransporta al guardián a una casilla libre y alejada de los jugadores."""
        ocupadas = self._otros_guardianes(guardian)
        posiciones_jugadores = [self._pos(j) for j in self._conectados]
        reservadas = self._reservadas()
        validas = [p for p in self._casillas_validas(reservadas | ocupadas)
                   if p not in posiciones_jugadores]
        if validas:
            def lejania(p):
                return min((_manhattan(p, q) for q in posiciones_jugadores), default=99)
            for minimo in (3, 2, 1):
                lejos = [p for p in validas if lejania(p) >= minimo]
                if not lejos:
                    continue
                preferidas = []
                zona = guardian.get("zona")
                if zona:
                    preferidas = [p for p in lejos
                                  if abs(p[0] - zona["x"]) <= zona["radio"]
                                  and abs(p[1] - zona["y"]) <= zona["radio"]]
                if not preferidas:
                    preferidas = [p for p in lejos if p in self._esquinas]
                guardian["x"], guardian["y"] = self.aleatorio.choice(preferidas or lejos)
                break
        guardian["objetivo"] = None
        memoria = self._memoria_de(guardian)
        memoria.update(cerca=0, quieto=0, ultima=(guardian["x"], guardian["y"]))

    def _congelar_y_reubicar(self, guardian, jugador, ahora):
        if not self._jugador_disponible(jugador, ahora):
            self._reubicar(guardian)
            return
        self.obstaculos.aplicar_congelamiento(
            str(jugador["player_id"]), self.segundos_congelacion, ahora,
            "Un guardián te ha alcanzado",
            segundos_inmunidad=self.segundos_inmunidad,
        )
        self._reubicar(guardian)

    # ------------------------------------------------------------------
    # Movimiento
    # ------------------------------------------------------------------
    def _pasos_libres(self, guardian, evitar=()):
        """Vecinos transitables sin guardianes ni jugadores encima."""
        bloqueadas = self._otros_guardianes(guardian) | {self._pos(j) for j in self._conectados}
        libres = [p for p in self._casillas_vecinas(guardian["x"], guardian["y"])
                  if p not in bloqueadas]
        preferidas = [p for p in libres if p not in evitar]
        return preferidas or libres

    def _alejarse(self, guardian, evitar):
        """Sin objetivo: se aleja de los jugadores en vez de quedarse junto a ellos."""
        guardian["objetivo"] = None
        origen = (guardian["x"], guardian["y"])
        opciones = self._pasos_libres(guardian, evitar)
        if not opciones:
            return
        posiciones = [self._pos(j) for j in self._conectados]
        actual = min((_manhattan(origen, q) for q in posiciones), default=99)
        if actual >= 3:
            guardian["x"], guardian["y"] = self.aleatorio.choice(opciones)
            return
        def lejania(p):
            return min((_manhattan(p, q) for q in posiciones), default=99)
        mejor = max(lejania(p) for p in opciones)
        guardian["x"], guardian["y"] = self.aleatorio.choice(
            [p for p in opciones if lejania(p) == mejor])

    def _mover_perseguidor(self, guardian, disponibles, evitar, ahora, asignados):
        origen = (guardian["x"], guardian["y"])
        posiciones_jugadores = {self._pos(j) for j in self._conectados}
        bloqueadas = self._otros_guardianes(guardian) | evitar
        distancia, padre = self._mapa_distancias(origen, bloqueadas, posiciones_jugadores)
        alcanzables = sorted(
            ((distancia[self._pos(j)], str(j["player_id"]), j)
             for j in disponibles if self._pos(j) in distancia),
            key=lambda t: (t[0], t[1]),
        )
        if not alcanzables:
            self._alejarse(guardian, evitar)
            return
        # Evita que ambos perseguidores elijan al mismo jugador si hay otro disponible.
        sin_asignar = [t for t in alcanzables if t[1] not in asignados]
        pasos, jid, objetivo = (sin_asignar or alcanzables)[0]
        guardian["objetivo"] = jid
        asignados.add(jid)
        destino = self._pos(objetivo)
        if pasos <= 1:
            # Adyacente: congela desde su casilla y se reubica. Nunca pisa al jugador.
            self._congelar_y_reubicar(guardian, objetivo, ahora)
            return
        if self.aleatorio.random() < self.PROB_PASO_ALEATORIO:
            opciones = self._pasos_libres(guardian, evitar)
            if opciones:
                guardian["x"], guardian["y"] = self.aleatorio.choice(opciones)
                return
        guardian["x"], guardian["y"] = self._primer_paso(padre, origen, destino)

    def _mover_vigilante(self, guardian, disponibles, evitar, ahora):
        zona = guardian["zona"]
        guardian["objetivo"] = None
        # Vigila su área: congela a quien quede pegado a él dentro de la zona.
        for jugador in disponibles:
            x, y = self._pos(jugador)
            if (_manhattan((x, y), (guardian["x"], guardian["y"])) == 1
                    and abs(x - zona["x"]) <= zona["radio"]
                    and abs(y - zona["y"]) <= zona["radio"]):
                self._congelar_y_reubicar(guardian, jugador, ahora)
                return
        vecinos = self._pasos_libres(guardian, evitar)
        dentro = [p for p in vecinos
                  if abs(p[0] - zona["x"]) <= zona["radio"]
                  and abs(p[1] - zona["y"]) <= zona["radio"]]
        if dentro and self.aleatorio.random() < 0.85:
            siguiente = self.aleatorio.choice(dentro)
        else:
            opciones = dentro or vecinos
            if not opciones:
                return
            siguiente = min(opciones, key=lambda p: (
                abs(p[0] - zona["x"]) + abs(p[1] - zona["y"]) + self.aleatorio.random() * 2))
        guardian["x"], guardian["y"] = siguiente

    def _vigilar_permanencia(self, guardian, no_disponibles):
        """Anti-campeo: reubica a un guardián que no se despega de un jugador
        congelado/inmune o que lleva varias actualizaciones sin moverse."""
        memoria = self._memoria_de(guardian)
        posicion = (guardian["x"], guardian["y"])
        cerca = any(_manhattan(posicion, self._pos(j)) <= 2 for j in no_disponibles)
        memoria["cerca"] = memoria["cerca"] + 1 if cerca else 0
        memoria["quieto"] = memoria["quieto"] + 1 if posicion == memoria["ultima"] else 0
        memoria["ultima"] = posicion
        if (memoria["cerca"] >= self.MAX_ACTUALIZACIONES_CERCA
                or memoria["quieto"] >= self.MAX_ACTUALIZACIONES_QUIETO):
            self._reubicar(guardian)

    def actualizar(self, jugadores, ahora=None):
        ahora = self.reloj() if ahora is None else ahora
        if ahora - self._ultimo_movimiento < self.INTERVALO_MOVIMIENTO:
            return self.estado_publico(jugadores, ahora)
        self._ultimo_movimiento = ahora
        self._conectados = [j for j in jugadores if j.get("connected", True)]

        asignados = set()
        for guardian in self.guardianes:
            # Se recalcula por guardián: otro guardián pudo congelar a alguien este turno.
            disponibles, no_disponibles = self._clasificar(ahora)
            evitar = self._zona_evitada(no_disponibles)

            # Estado heredado inválido: sobre un jugador. Congela (si procede) y se retira.
            encima = next((j for j in self._conectados
                           if self._pos(j) == (guardian["x"], guardian["y"])), None)
            if encima is not None:
                self._congelar_y_reubicar(guardian, encima, ahora)
                continue

            if guardian["tipo"] == "perseguidor":
                self._mover_perseguidor(guardian, disponibles, evitar, ahora, asignados)
            else:
                self._mover_vigilante(guardian, disponibles, evitar, ahora)
            _, no_disponibles = self._clasificar(ahora)
            self._vigilar_permanencia(guardian, no_disponibles)

        return self.estado_publico(jugadores, ahora)

    def estado_publico(self, jugadores=(), ahora=None):
        resultado = []
        for guardian in self.guardianes:
            copia = guardian.copy()
            if not any(str(j["player_id"]) == str(copia["objetivo"]) for j in jugadores):
                copia["objetivo"] = None
            resultado.append(copia)
        return resultado

    def agregar_adicionales(self, cantidad=5, posiciones_ocupadas=()):
        """Agrega guardianes temporales en casillas libres de la arena."""
        ocupadas = self._reservadas()
        ocupadas.update(posiciones_ocupadas)
        ocupadas.update((g["x"], g["y"]) for g in self.guardianes)
        # No aparecen sobre ni junto a un jugador (evita congelamientos instantáneos).
        cercanas = set()
        for x, y in posiciones_ocupadas:
            cercanas.update({(x, y), (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)})
        cantidad = max(0, int(cantidad))
        libres = self._casillas_validas(ocupadas | cercanas)
        if len(libres) < cantidad:
            libres = self._casillas_validas(ocupadas)
        posiciones = self.aleatorio.sample(libres, min(cantidad, len(libres)))
        nuevos = []
        siguiente = 1 + max(
            (int(g["id"].rsplit("_", 1)[-1]) for g in self.guardianes
             if g["id"].startswith("guardian_") and g["id"].rsplit("_", 1)[-1].isdigit()),
            default=0,
        )
        for indice, (x, y) in enumerate(posiciones, 1):
            guardian = {
                "id": f"guardian_extra_{siguiente + indice}",
                "x": x, "y": y, "tipo": "perseguidor",
                "objetivo": None, "adicional": True,
            }
            self.guardianes.append(guardian)
            nuevos.append(guardian["id"])
        return nuevos

    def quitar_adicionales(self, identificadores):
        """Retira únicamente los guardianes temporales creados por un evento."""
        conjunto = set(identificadores)
        self.guardianes = [
            g for g in self.guardianes
            if not (g.get("adicional") and g["id"] in conjunto)
        ]


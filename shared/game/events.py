"""Gestión autoritativa de los eventos especiales de la US-22."""

from __future__ import annotations

import random
import time
from typing import Callable


class GestorEventosPartida:
    """Programa, activa y finaliza eventos especiales una sola vez por partida."""

    DURACION_ENERGIA = 6.0
    DURACION_SOBRECARGA = 8.0
    DURACION_GUARDIANES = 22.0
    DURACION_EVENTO_CREATIVO = 20.0
    PUNTOS_ENERGIA = 3
    # Los eventos se programan por "rondas" para que sigan apareciendo durante
    # toda la partida, sin importar su duración, el modo de fin ni la prórroga.
    HORIZONTE_RONDA_MAX = 300.0     # una ronda dura como máximo 5 min
    HORIZONTE_RONDA_PUNTOS = 150.0  # en modo por puntos la duración es incierta
    HORIZONTE_PRORROGA = 120.0      # una prórroga dura exactamente 2 min
    MIN_HORIZONTE_RONDA = 30.0      # no se abre una ronda con menos tiempo útil

    ## @brief US-22: inicializa los eventos temporizados y sus dependencias de arena.
    def __init__(self, mapa, obstaculos, guardianes, reloj: Callable[[], float] = time.monotonic,
                 semilla=None):
        self.mapa = mapa
        self.obstaculos = obstaculos
        self.guardianes = guardianes
        self.reloj = reloj
        self.aleatorio = random.Random(semilla)
        self.iniciado_en = None
        self._pausado_en = None
        self.programados = []
        self.activos = {}
        self.completados = set()
        self._guardianes_extra = []
        self._trampas_extra = []
        self.energia = None
        self.modo = "tiempo"
        self._fin_partida = None
        self._fin_ronda = 0.0
        self._ronda = 0
        self._n_energia = 0
        self._n_sobrecarga = 0
        self._finalizado = False

    ## @brief US-22: identifica el tipo de evento a partir de su identificador.
    @staticmethod
    def _tipo(identificador):
        """Tipo de evento a partir de su id (las rondas posteriores añaden sufijos)."""
        for base in ("energia", "sobrecarga"):
            if identificador.startswith(base + "_"):
                return base
        for base in ("guardianes_adicionales", "guardianes_quitan_puntos", "doble_trampas"):
            if identificador.startswith(base):
                return base
        return identificador

    ## @brief US-22: programa la primera ronda según modo y duración de partida.
    def iniciar(self, ahora, duracion_partida, modo="tiempo"):
        """Programa la primera ronda de eventos.

        ``modo`` es ``"tiempo"`` (la partida dura ``duracion_partida`` segundos)
        o ``"puntos"`` (termina al alcanzar el objetivo; duración desconocida).
        """
        if self.iniciado_en is not None:
            return
        self.iniciado_en = float(ahora)
        self.modo = "puntos" if modo == "puntos" else "tiempo"
        if self.modo == "tiempo":
            duracion = max(self.MIN_HORIZONTE_RONDA, float(duracion_partida))
            self._fin_partida = self.iniciado_en + duracion
            horizonte = min(self.HORIZONTE_RONDA_MAX, duracion)
        else:
            self._fin_partida = None
            horizonte = self.HORIZONTE_RONDA_PUNTOS
        self._programar_ronda(self.iniciado_en, horizonte)

    ## @brief US-22: distribuye energías, sobrecargas y eventos en una ronda.
    def _programar_ronda(self, inicio, horizonte):
        """Añade una ronda completa que cumple la US-22: tres energías en momentos
        distintos, dos sobrecargas, guardianes adicionales y dos eventos creativos."""
        self._ronda += 1
        sufijo = "" if self._ronda == 1 else f"_r{self._ronda}"
        horizonte = max(self.MIN_HORIZONTE_RONDA, float(horizonte))
        margen = min(12.0, horizonte * 0.08)

        ## @brief Mantiene el inicio y fin de cada evento dentro del horizonte de ronda.
        def ubicar(instante, duracion):
            # Dentro de la ronda y terminando antes de que ella acabe.
            return min(max(margen, instante), max(margen, horizonte - duracion - 1))

        definiciones = []
        # Las tres energías quedan separadas: cada una puede recogerse antes de la siguiente.
        for proporcion in (0.06, 0.45, 0.78):
            self._n_energia += 1
            variacion = self.aleatorio.uniform(-0.025, 0.025) * horizonte
            definiciones.append((ubicar(horizonte * proporcion + variacion, self.DURACION_ENERGIA),
                                 f"energia_{self._n_energia}", self.DURACION_ENERGIA))
        for minimo, maximo in ((0.20, 0.38), (0.65, 0.84)):
            self._n_sobrecarga += 1
            definiciones.append((ubicar(self.aleatorio.uniform(horizonte * minimo, horizonte * maximo),
                                        self.DURACION_SOBRECARGA),
                                 f"sobrecarga_{self._n_sobrecarga}", self.DURACION_SOBRECARGA))
        for (minimo, maximo), nombre, duracion in (
            ((0.25, 0.55), "guardianes_adicionales", self.DURACION_GUARDIANES),
            ((0.45, 0.72), "guardianes_quitan_puntos", self.DURACION_EVENTO_CREATIVO),
            ((0.68, 0.92), "doble_trampas", self.DURACION_EVENTO_CREATIVO),
        ):
            definiciones.append((ubicar(self.aleatorio.uniform(horizonte * minimo, horizonte * maximo),
                                        duracion), nombre + sufijo, duracion))
        self.programados.extend(
            {"id": nombre, "nombre": nombre, "inicia_en": inicio + instante,
             "duracion": duracion, "activado": False}
            for instante, nombre, duracion in sorted(definiciones)
        )
        self._fin_ronda = inicio + horizonte

    ## @brief US-16 y US-22: programa otra ronda mientras continúe activa la partida.
    def _programar_siguiente_ronda(self, ahora, prorroga):
        """Abre otra ronda cuando la anterior terminó, mientras la partida siga activa."""
        if (self._finalizado or self.iniciado_en is None
                or ahora < self._fin_ronda
                or not all(e["activado"] for e in self.programados)):
            return
        if prorroga:
            horizonte = self.HORIZONTE_PRORROGA
        elif self.modo == "puntos":
            horizonte = self.HORIZONTE_RONDA_PUNTOS
        else:
            restante = self._fin_partida - ahora
            if restante < self.MIN_HORIZONTE_RONDA:
                return
            horizonte = min(self.HORIZONTE_RONDA_MAX, restante)
        self._programar_ronda(ahora, horizonte)

    ## @brief US-10 y US-22: pausa el reloj de eventos durante una desconexión.
    def pausar(self, ahora=None):
        """Detiene el reloj de eventos mientras la partida está pausada."""
        ahora = self.reloj() if ahora is None else float(ahora)
        if self.iniciado_en is not None and self._pausado_en is None:
            self._pausado_en = ahora

    ## @brief US-10 y US-22: desplaza vencimientos para conservar la duración restante.
    def reanudar(self, ahora=None):
        """Desplaza los vencimientos para conservar la duración restante de cada evento."""
        ahora = self.reloj() if ahora is None else float(ahora)
        if self._pausado_en is None:
            return
        desplazamiento = max(0.0, ahora - self._pausado_en)
        self.iniciado_en += desplazamiento
        self._fin_ronda += desplazamiento
        if self._fin_partida is not None:
            self._fin_partida += desplazamiento
        for evento in self.programados:
            evento["inicia_en"] += desplazamiento
        for evento in self.activos.values():
            evento["termina_en"] += desplazamiento
        if self.energia is not None:
            self.energia["termina_en"] += desplazamiento
        self._pausado_en = None

    ## @brief US-22: activa eventos programados, termina los vencidos y publica estado.
    def actualizar(self, jugadores, ahora=None, prorroga=False):
        ahora = self.reloj() if ahora is None else float(ahora)
        if self._pausado_en is not None:
            return self.estado_publico(ahora)
        if self.iniciado_en is not None and not self._finalizado:
            self._programar_siguiente_ronda(ahora, prorroga)
            for evento in self.programados:
                if evento["activado"] or ahora < evento["inicia_en"]:
                    continue
                evento["activado"] = True
                self.completados.add(evento["id"])
                self._activar(evento, jugadores, ahora)
        for identificador, evento in list(self.activos.items()):
            if ahora >= evento["termina_en"]:
                self._finalizar(identificador, evento)
        return self.estado_publico(ahora)

    ## @brief US-22: aplica los efectos asociados al tipo de evento que inicia.
    def _activar(self, programado, jugadores, ahora):
        identificador = programado["id"]
        nombre = self._tipo(identificador)
        if nombre in {"guardianes_adicionales", "guardianes_quitan_puntos", "doble_trampas"} and any(
                self._tipo(activo) == nombre for activo in self.activos):
            return  # CA-22.9: un evento único no se aplica dos veces a la vez.
        evento = {
            "id": identificador, "nombre": identificador, "tipo": nombre,
            "inicia_en": ahora, "termina_en": ahora + programado["duracion"],
            "mensaje": "", "efecto": nombre,
        }
        if nombre == "energia":
            ubicacion = self._ubicacion_energia(jugadores)
            if ubicacion is None:
                # Si no existe casilla segura, se reintenta en la siguiente actualización.
                programado["activado"] = False
                self.completados.discard(identificador)
                return
            self.energia = {
                "id": identificador, "x": ubicacion[0], "y": ubicacion[1],
                "puntos": self.PUNTOS_ENERGIA, "termina_en": evento["termina_en"],
            }
            evento["mensaje"] = (
                f"¡Energía adicional: +{self.PUNTOS_ENERGIA} puntos! "
                "Recógela antes de que desaparezca."
            )
        elif nombre == "sobrecarga":
            evento["mensaje"] = "¡Sobrecarga del reactor! No se pueden obtener puntos en el reactor."
        elif nombre == "guardianes_adicionales":
            self._guardianes_extra = self.guardianes.agregar_adicionales(
                5, {(int(j["x"]), int(j["y"])) for j in jugadores}
            )
            evento["mensaje"] = "¡Aparecieron 5 guardianes adicionales!"
        elif nombre == "guardianes_quitan_puntos":
            evento["mensaje"] = "¡Drenaje de puntos! Los guardianes quitan 1 punto al alcanzarte."
        elif nombre == "doble_trampas":
            self._trampas_extra = self.obstaculos.duplicar_trampas(
                {(int(j["x"]), int(j["y"])) for j in jugadores}
            )
            evento["mensaje"] = "¡Doble de trampas! La arena tiene el doble de trampas."
        self.activos[identificador] = evento

    ## @brief US-22: busca una casilla segura para la energía adicional.
    def _ubicacion_energia(self, jugadores):
        ocupadas = {(int(j["x"]), int(j["y"])) for j in jugadores}
        ocupadas.update(self.mapa.puntos_inicio())
        ocupadas.update((t.x, t.y) for t in self.obstaculos.trampas)
        ocupadas.update((p["x"], p["y"]) for p in self.obstaculos.puertas)
        ocupadas.update((g["x"], g["y"]) for g in self.guardianes.guardianes)
        ocupadas.update((x, y) for y in range(self.mapa.filas)
                        for x in range(self.mapa.columnas)
                        if self.mapa.casilla_en(x, y).value == "R")
        candidatas = [(x, y) for y in range(1, self.mapa.filas - 1)
                      for x in range(1, self.mapa.columnas - 1)
                      if self.mapa.es_transitable(x, y) and (x, y) not in ocupadas]
        return self.aleatorio.choice(candidatas) if candidatas else None

    ## @brief US-22: entrega una sola vez los puntos de energía al jugador que la recoge.
    def recoger_energia(self, jugador, ahora=None):
        """El primer jugador que ocupa la casilla recoge la energía una sola vez."""
        ahora = self.reloj() if ahora is None else float(ahora)
        if self.energia is None or ahora >= self.energia["termina_en"]:
            return None
        if (int(jugador["x"]), int(jugador["y"])) != (self.energia["x"], self.energia["y"]):
            return None
        puntos = self.energia["puntos"]
        identificador = self.energia["id"]
        self.energia = None
        self.activos.pop(identificador, None)
        return puntos

    ## @brief US-18–US-19 y US-22: indica si una sobrecarga está bloqueando el reactor.
    def sobrecarga_activa(self, ahora=None):
        ahora = self.reloj() if ahora is None else float(ahora)
        return any(
            nombre.startswith("sobrecarga_") and evento["termina_en"] > ahora
            for nombre, evento in self.activos.items()
        )

    ## @brief US-21–US-22: indica si los guardianes deben drenar puntos.
    def drenaje_activo(self, ahora=None):
        ahora = self.reloj() if ahora is None else float(ahora)
        return any(
            self._tipo(identificador) == "guardianes_quitan_puntos" and evento["termina_en"] > ahora
            for identificador, evento in self.activos.items()
        )

    ## @brief US-21–US-22: resta un punto ante un nuevo impacto durante el drenaje.
    def penalizar_por_guardian(self, jugador_id, estado_anterior, estado_actual,
                               marcador, ahora=None):
        """Resta un punto si un guardián alcanza al jugador durante el evento de drenaje."""
        if not self.drenaje_activo(ahora):
            return False
        if (
            estado_actual.get("estado") != "congelado"
            or estado_actual.get("efecto") != "guardian"
            or estado_actual.get("hasta", 0.0) <= estado_anterior.get("hasta", 0.0)
        ):
            return False
        marcador.remove_points(jugador_id, 1)
        return True

    ## @brief US-22: revierte los efectos temporales de un evento.
    def _finalizar(self, identificador, evento):
        tipo = self._tipo(identificador)
        if tipo == "guardianes_adicionales":
            self.guardianes.quitar_adicionales(self._guardianes_extra)
            self._guardianes_extra = []
        elif tipo == "doble_trampas":
            self.obstaculos.quitar_trampas_evento(self._trampas_extra)
            self._trampas_extra = []
        elif tipo == "energia" and self.energia is not None:
            if self.energia["id"] == identificador:
                self.energia = None
        self.activos.pop(identificador, None)

    ## @brief US-22 y US-30: prepara los eventos activos y próximos para los clientes.
    def estado_publico(self, ahora=None):
        ahora = self.reloj() if ahora is None else float(ahora)
        eventos = []
        for evento in self.activos.values():
            eventos.append({
                "id": evento["id"], "nombre": evento["nombre"],
                "tipo": evento.get("tipo", self._tipo(evento["id"])),
                "mensaje": evento["mensaje"],
                "segundos_restantes": max(0.0, evento["termina_en"] - ahora),
                "segundos_transcurridos": max(0.0, ahora - evento["inicia_en"]),
            })
        siguientes = [
            evento for evento in self.programados
            if not evento["activado"] and evento["inicia_en"] > ahora
        ]
        proximo_evento = None
        if siguientes:
            siguiente = min(siguientes, key=lambda evento: evento["inicia_en"])
            proximo_evento = {
                "id": siguiente["id"], "tipo": self._tipo(siguiente["id"]),
                "segundos_restantes": max(0.0, siguiente["inicia_en"] - ahora),
            }
        return {
            "eventos": eventos,
            "proximo_evento": proximo_evento,
            "energia_adicional": None if self.energia is None else {
                "x": self.energia["x"], "y": self.energia["y"],
                "puntos": self.energia["puntos"],
                "segundos_restantes": max(0.0, self.energia["termina_en"] - ahora),
            },
            "reactor_sobrecargado": self.sobrecarga_activa(ahora),
        }

    ## @brief US-22: cancela eventos pendientes y limpia los efectos de la partida.
    def finalizar(self):
        """Cancela los efectos temporales al finalizar la partida."""
        for identificador, evento in list(self.activos.items()):
            self._finalizar(identificador, evento)
        self.energia = None
        self.programados = []
        self._finalizado = True

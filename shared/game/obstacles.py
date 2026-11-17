"""Reglas autoritativas de barreras, puertas y trampas de la arena."""
from __future__ import annotations

from dataclasses import dataclass
import random
import time
from typing import Callable


@dataclass
class Trampa:
    """Trampa ubicada en una casilla transitable."""
    identificador: str
    tipo: str
    x: int
    y: int
    duracion: float
    activa: bool = True


class GestorObstaculos:
    """Administra obstáculos desde el servidor; los clientes solo reciben su estado."""

    DURACION_PUERTA = 7.0

    def __init__(self, mapa, puntos_inicio, segundos_inmovilizacion=3,
                 reloj: Callable[[], float] = time.monotonic, semilla=None):
        self.mapa = mapa
        self.reloj = reloj
        self.segundos_inmovilizacion = max(1, float(segundos_inmovilizacion))
        self.aleatorio = random.Random(semilla)
        # Se reservan todos los puntos de inicio del mapa, incluso si la sala usa menos jugadores.
        reservadas = set(mapa.puntos_inicio()) | set(puntos_inicio)
        reservadas.update((x, y) for y in range(mapa.filas) for x in range(mapa.columnas)
                          if mapa.casilla_en(x, y).value == "R")
        candidatas = [(x, y) for y in range(1, mapa.filas - 1)
                      for x in range(1, mapa.columnas - 1)
                      if mapa.es_transitable(x, y) and (x, y) not in reservadas]
        if len(candidatas) < 4:
            raise ValueError("No hay suficientes casillas para colocar los obstáculos.")
        seleccionadas = self.aleatorio.sample(candidatas, 4)
        self.puertas = [{"id": "puerta_principal", "x": seleccionadas[0][0],
                         "y": seleccionadas[0][1], "abierta": True,
                         "cambia_en": self.reloj() + self.DURACION_PUERTA}]
        tipos = (
            ("jaula", self.segundos_inmovilizacion),
            ("arenas_movedizas", self.segundos_inmovilizacion + 1),
            ("campo_electrico", self.segundos_inmovilizacion + 2),
        )
        self.trampas = [Trampa(f"trampa_{i + 1}", tipo, seleccionadas[i + 1][0],
                               seleccionadas[i + 1][1], duracion)
                        for i, (tipo, duracion) in enumerate(tipos)]
        self.estados_jugadores: dict[str, dict] = {}
        self._trampas_activadas: set[tuple[str, str]] = set()

    def actualizar(self, ahora=None):
        ahora = self.reloj() if ahora is None else ahora
        for puerta in self.puertas:
            if ahora >= puerta["cambia_en"]:
                puerta["abierta"] = not puerta["abierta"]
                puerta["cambia_en"] = ahora + self.DURACION_PUERTA
        for estado in self.estados_jugadores.values():
            if estado["hasta"] <= ahora:
                estado.update(estado="normal", hasta=0.0, efecto=None, mensaje="")

    def puerta_en(self, x, y):
        return next((puerta for puerta in self.puertas
                     if puerta["x"] == x and puerta["y"] == y), None)

    def jugador_inmovil(self, jugador_id, ahora=None):
        self.actualizar(ahora)
        estado = self.estados_jugadores.get(str(jugador_id), {})
        return estado.get("estado") == "inmovilizado"

    def validar_movimiento(self, jugador_id, x, y, ahora=None):
        """Valida límites, barreras, puertas y estado temporal del jugador."""
        ahora = self.reloj() if ahora is None else ahora
        self.actualizar(ahora)
        if self.jugador_inmovil(jugador_id, ahora):
            return False, "No puedes moverte: " + self.estados_jugadores[str(jugador_id)]["mensaje"]
        if not self.mapa.es_transitable(x, y):
            return False, "Una barrera o el límite de la arena impide el paso."
        puerta = self.puerta_en(x, y)
        if puerta is not None and not puerta["abierta"]:
            return False, "La puerta está cerrada. Espera a que se abra."
        return True, ""

    def activar_trampa(self, jugador_id, x, y, ahora=None):
        ahora = self.reloj() if ahora is None else ahora
        for trampa in self.trampas:
            clave = (str(jugador_id), trampa.identificador)
            if trampa.activa and (trampa.x, trampa.y) == (x, y) and clave not in self._trampas_activadas:
                self._trampas_activadas.add(clave)
                anterior = self.estados_jugadores.get(str(jugador_id), {})
                restante = max(0.0, anterior.get("hasta", 0.0) - ahora)
                hasta = ahora + restante + trampa.duracion
                nombres = {
                    "jaula": "una jaula de contención",
                    "arenas_movedizas": "arenas movedizas",
                    "campo_electrico": "un campo eléctrico",
                }
                self.estados_jugadores[str(jugador_id)] = {
                    "estado": "inmovilizado", "hasta": hasta,
                    "efecto": trampa.tipo,
                    "mensaje": f"Has caído en {nombres[trampa.tipo]}",
                }
                return self.estados_jugadores[str(jugador_id)].copy()
        return None

    def estado_publico(self, ahora=None):
        self.actualizar(ahora)
        trampas = [{"id": t.identificador, "tipo": t.tipo, "x": t.x, "y": t.y,
                    "activa": t.activa} for t in self.trampas]
        barreras = []
        for y in range(self.mapa.filas):
            for x in range(self.mapa.columnas):
                casilla = self.mapa.casilla_en(x, y).value
                if casilla in {"#", "X"}:
                    barreras.append({"x": x, "y": y,
                                     "tipo": "limite" if casilla == "#" else "barrera"})
        return {"barreras": barreras, "puertas": [p.copy() for p in self.puertas],
                "trampas": trampas}

    def estado_jugador(self, jugador_id, ahora=None):
        self.actualizar(ahora)
        estado = self.estados_jugadores.get(str(jugador_id),
                  {"estado": "normal", "hasta": 0.0, "efecto": None, "mensaje": ""})
        return {**estado, "segundos_restantes": max(0.0, estado["hasta"] - (self.reloj() if ahora is None else ahora))}

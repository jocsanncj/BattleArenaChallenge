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

    def actualizar(self, ahora=None):
        ahora = self.reloj() if ahora is None else ahora
        for puerta in self.puertas:
            if ahora >= puerta["cambia_en"]:
                puerta["abierta"] = not puerta["abierta"]
                puerta["cambia_en"] = ahora + self.DURACION_PUERTA
        for estado in self.estados_jugadores.values():
            if estado["hasta"] <= ahora and estado.get("estado") in {"congelado", "inmovilizado"}:
                # La inmunidad comienza justo al terminar el congelamiento del guardián.
                inmunidad = (estado["hasta"] + estado.get("duracion_inmunidad", 3.0)
                             if estado.get("efecto") == "guardian" else estado.get("inmunidad_hasta", 0.0))
                estado.update(estado="normal", hasta=0.0, efecto=None, mensaje="",
                              inmunidad_hasta=inmunidad)

    def puerta_en(self, x, y):
        return next((puerta for puerta in self.puertas
                     if puerta["x"] == x and puerta["y"] == y), None)

    def jugador_inmovil(self, jugador_id, ahora=None):
        self.actualizar(ahora)
        estado = self.estados_jugadores.get(str(jugador_id), {})
        return estado.get("estado") in {"inmovilizado", "congelado"}

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

    def _nueva_ubicacion_trampa(self, trampa, ubicaciones_ocupadas=()):
        """Busca una casilla aleatoria y segura para volver a colocar una trampa."""
        ocupadas = set(ubicaciones_ocupadas or ())
        ocupadas.update((puerta["x"], puerta["y"]) for puerta in self.puertas)
        ocupadas.update((otra.x, otra.y) for otra in self.trampas if otra is not trampa)
        # No se reutiliza la casilla que acaba de activar el jugador.
        ocupadas.add((trampa.x, trampa.y))
        ocupadas.update(self.mapa.puntos_inicio())
        ocupadas.update((x, y) for y in range(self.mapa.filas)
                        for x in range(self.mapa.columnas)
                        if self.mapa.casilla_en(x, y).value == "R")
        candidatas = [(x, y) for y in range(1, self.mapa.filas - 1)
                      for x in range(1, self.mapa.columnas - 1)
                      if self.mapa.es_transitable(x, y) and (x, y) not in ocupadas]
        if not candidatas:
            # Si el mapa está temporalmente lleno, la trampa permanece en su lugar.
            return False
        trampa.x, trampa.y = self.aleatorio.choice(candidatas)
        return True

    def activar_trampa(self, jugador_id, x, y, ahora=None, ubicaciones_ocupadas=()):
        ahora = self.reloj() if ahora is None else ahora
        # Resuelve primero expiraciones pendientes (p. ej. una inmunidad que aún
        # no se había materializado) para no perderlas al reemplazar el estado.
        self.actualizar(ahora)
        for trampa in self.trampas:
            if trampa.activa and (trampa.x, trampa.y) == (x, y):
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
                    # La inmunidad frente a guardianes no se pierde al pisar una trampa.
                    "inmunidad_hasta": anterior.get("inmunidad_hasta", 0.0),
                    "duracion_inmunidad": anterior.get("duracion_inmunidad", 3.0),
                }
                # La trampa reaparece en otra casilla al activarse; el servidor
                # publica la nueva posición en la siguiente actualización de estado.
                self._nueva_ubicacion_trampa(trampa, ubicaciones_ocupadas)
                return self.estados_jugadores[str(jugador_id)].copy()
        return None


    def aplicar_congelamiento(self, jugador_id, duracion, ahora=None, mensaje="Un guardián te ha alcanzado",
                              segundos_inmunidad=3.0):
        """Aplica congelamiento y configura la inmunidad que inicia al descongelarse."""
        ahora = self.reloj() if ahora is None else ahora
        self.actualizar(ahora)
        clave = str(jugador_id)
        anterior = self.estados_jugadores.get(clave, {})
        # Invulnerabilidad: un jugador inmune o ya congelado no puede ser congelado.
        if self.esta_inmune(clave, ahora) or anterior.get("estado") == "congelado":
            return self.estado_jugador(clave, ahora)
        restante = max(0.0, anterior.get("hasta", 0.0) - ahora)
        self.estados_jugadores[clave] = {
            "estado": "congelado", "hasta": ahora + restante + max(1.0, float(duracion)),
            "efecto": "guardian", "mensaje": mensaje,
            "duracion_inmunidad": max(1.0, float(segundos_inmunidad)),
            "inmunidad_hasta": anterior.get("inmunidad_hasta", 0.0),
        }
        return self.estado_jugador(clave, ahora)

    def esta_inmune(self, jugador_id, ahora=None):
        """True mientras dure la inmunidad posterior a un congelamiento."""
        instante = self.reloj() if ahora is None else ahora
        self.actualizar(instante)
        estado = self.estados_jugadores.get(str(jugador_id), {})
        return estado.get("inmunidad_hasta", 0.0) > instante

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
        instante = self.reloj() if ahora is None else ahora
        estado = self.estados_jugadores.get(str(jugador_id),
                  {"estado": "normal", "hasta": 0.0, "efecto": None, "mensaje": "",
                   "inmunidad_hasta": 0.0})
        return {**estado,
                "segundos_restantes": max(0.0, estado["hasta"] - instante),
                "segundos_inmunidad": max(0.0, estado.get("inmunidad_hasta", 0.0) - instante)}

    def duplicar_trampas(self, posiciones_ocupadas=()):
        """Crea una copia temporal de cada trampa activa en una casilla libre."""
        nuevas = []
        ocupadas = set(posiciones_ocupadas)
        ocupadas.update((t.x, t.y) for t in self.trampas)
        ocupadas.update((p["x"], p["y"]) for p in self.puertas)
        ocupadas.update(self.mapa.puntos_inicio())
        ocupadas.update((x, y) for y in range(self.mapa.filas)
                        for x in range(self.mapa.columnas)
                        if self.mapa.casilla_en(x, y).value == "R")
        originales = [t for t in self.trampas if t.activa]
        candidatas = [(x, y) for y in range(1, self.mapa.filas - 1)
                      for x in range(1, self.mapa.columnas - 1)
                      if self.mapa.es_transitable(x, y) and (x, y) not in ocupadas]
        self.aleatorio.shuffle(candidatas)
        for indice, trampa in enumerate(originales):
            if not candidatas:
                break
            x, y = candidatas.pop()
            copia = Trampa(
                f"trampa_evento_{int(time.monotonic() * 1000)}_{indice}",
                trampa.tipo, x, y, trampa.duracion, True,
            )
            self.trampas.append(copia)
            nuevas.append(copia.identificador)
        return nuevas

    def quitar_trampas_evento(self, identificadores):
        """Elimina las trampas adicionales de un evento sin alterar las originales."""
        conjunto = set(identificadores)
        self.trampas = [
            t for t in self.trampas
            if t.identificador not in conjunto
        ]


"""US-20: obstáculos autoritativos de la arena.

El servidor es dueño de las puertas, las trampas y los estados temporales. Los
clientes reciben una instantánea serializable y únicamente la representan.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable

from logica import ARENA_PREDETERMINADA, Casilla, MapaArena


@dataclass(frozen=True)
class Trampa:
    id: str
    nombre: str
    x: int
    y: int
    duracion: float
    color: tuple[int, int, int]


class ObstaculosArena:
    """Controla colisiones, puertas temporizadas y tres trampas distintas."""

    INTERVALO_PUERTA = 10.0
    PUERTAS = ((10, 2), (10, 12))
    TIPOS_TRAMPA = (
        ("jaula", "Jaula electromagnética", 4.0, (220, 80, 80)),
        ("arenas", "Arenas movedizas", 5.0, (190, 145, 65)),
        ("pulso", "Pulso invertido", 3.0, (155, 95, 220)),
    )

    def __init__(self, mapa: MapaArena = ARENA_PREDETERMINADA,
                 clock: Callable[[], float] = time.monotonic,
                 rng=None) -> None:
        self.mapa = mapa
        self._clock = clock
        self._inicio = float(clock())
        self._rng = rng or random.SystemRandom()
        self._congelados: dict[str, dict] = {}
        self._trampas = self._crear_trampas()

    def _crear_trampas(self) -> tuple[Trampa, ...]:
        excluidas = set(self.mapa.puntos_inicio()) | set(self.PUERTAS)
        libres = [
            (x, y)
            for y in range(1, self.mapa.filas - 1)
            for x in range(1, self.mapa.columnas - 1)
            if self.mapa.es_transitable(x, y) and (x, y) not in excluidas
        ]
        if len(libres) < len(self.TIPOS_TRAMPA):
            raise ValueError("La arena no tiene espacio suficiente para las tres trampas.")
        posiciones = self._rng.sample(libres, len(self.TIPOS_TRAMPA))
        return tuple(
            Trampa(tipo, nombre, x, y, duracion, color)
            for (tipo, nombre, duracion, color), (x, y)
            in zip(self.TIPOS_TRAMPA, posiciones)
        )

    def _puertas_abiertas(self, now: float) -> bool:
        periodo = int(max(0.0, now - self._inicio) // self.INTERVALO_PUERTA)
        return periodo % 2 == 0

    def puede_mover(self, player_id: str, x: int, y: int,
                    now: float | None = None) -> tuple[bool, str | None]:
        """Valida bloqueo temporal, límites, barreras y estado actual de las puertas."""
        now = float(self._clock() if now is None else now)
        self._actualizar_congelamientos(now)
        efecto = self._congelados.get(str(player_id))
        if efecto:
            restante = max(0.0, efecto["hasta"] - now)
            return False, f"Estás inmovilizado por {efecto['nombre']} ({restante:.1f} s)."
        if not self.mapa.es_transitable(x, y):
            return False, "Una barrera u obstáculo impide el paso."
        if (x, y) in self.PUERTAS and not self._puertas_abiertas(now):
            return False, "La puerta está cerrada. Espera a que se abra."
        return True, None

    def registrar_entrada(self, player_id: str, x: int, y: int,
                          now: float | None = None) -> dict | None:
        """Activa la trampa al entrar en su casilla; una activación no se duplica."""
        now = float(self._clock() if now is None else now)
        self._actualizar_congelamientos(now)
        trampa = next((t for t in self._trampas if (t.x, t.y) == (x, y)), None)
        if trampa is None:
            return None
        self._congelados[str(player_id)] = {
            "tipo": trampa.id,
            "nombre": trampa.nombre,
            "hasta": now + trampa.duracion,
            "duracion": trampa.duracion,
        }
        return {"tipo": trampa.id, "nombre": trampa.nombre,
                "duracion": trampa.duracion}

    def _actualizar_congelamientos(self, now: float) -> None:
        for player_id, efecto in list(self._congelados.items()):
            if now >= efecto["hasta"]:
                del self._congelados[player_id]

    def estado(self, now: float | None = None) -> dict:
        """Devuelve únicamente datos serializables para compartir con los clientes."""
        now = float(self._clock() if now is None else now)
        self._actualizar_congelamientos(now)
        puertas_abiertas = self._puertas_abiertas(now)
        jugadores = {
            player_id: {
                "frozen": True,
                "trap_effect": efecto["nombre"],
                "frozen_remaining": round(max(0.0, efecto["hasta"] - now), 2),
            }
            for player_id, efecto in self._congelados.items()
        }
        return {
            "barriers": [
                {"x": x, "y": y}
                for y in range(self.mapa.filas)
                for x in range(self.mapa.columnas)
                if self.mapa.casilla_en(x, y) is Casilla.OBSTACULO
            ],
            "doors": [
                {"x": x, "y": y, "open": puertas_abiertas}
                for x, y in self.PUERTAS
            ],
            "traps": [
                {"id": t.id, "name": t.nombre, "x": t.x, "y": t.y,
                 "duration": t.duracion, "color": t.color}
                for t in self._trampas
            ],
            "players": jugadores,
            "door_cycle_seconds": self.INTERVALO_PUERTA,
        }

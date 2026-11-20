"""
US16: determinación automática del ganador y prórroga por empate. El servidor proporciona el tiempo; no depende de Pygame.
"""

from __future__ import annotations

from copy import deepcopy
import math


class GameRules:
    """
    Gestiona las condiciones de finalización; US15 guarda los puntos y cada empate añade una prórroga fija de 120 segundos.

    now utiliza los segundos del mismo reloj monotónico, por ejemplo time.monotonic.
    La pausa no cambia el estado running/overtime; se indica por separado mediante paused.
    """

    OVERTIME_SECONDS = 120
    _EPSILON = 1e-9

    def __init__(self, mode: str = "time", duration_seconds: int = 60,
                 target_score: int = 20, overtime_seconds: int = 120) -> None:
        # Requiere US08: proporcionar el modo de finalización, el tiempo y el puntaje objetivo seleccionados al iniciar.
        # Si la interfaz de US08 recibe minutos, convertirlos primero a segundos mediante minutes * 60.
        if not isinstance(mode, str) or mode not in {"time", "points"}:
            raise ValueError("El modo debe ser 'time' o 'points'.")
        if type(duration_seconds) is not int or not 1 <= duration_seconds <= 3600:
            raise ValueError("La duración debe estar entre 1 y 3600 segundos.")
        if type(target_score) is not int or not 1 <= target_score <= 10000:
            raise ValueError("El objetivo debe estar entre 1 y 10000 puntos.")
        if type(overtime_seconds) is not int or overtime_seconds != self.OVERTIME_SECONDS:
            raise ValueError("La prórroga de US16 debe ser exactamente de 120 segundos.")
        self.mode = mode
        self.duration_seconds = duration_seconds
        self.target_score = target_score
        self.status = "waiting"
        self.paused = False
        self.overtime_count = 0
        self.winner_id: str | None = None
        self._elapsed = 0.0
        self._last_now: float | None = None
        self._observed_now: float | None = None
        self._deadline: float | None = None
        self._last_scores: dict[str, int] = {}
        self._final_state: dict | None = None

    def start(self, now: float) -> None:
        """
        El proceso de inicio llama una sola vez para establecer el reloj de esta partida.
        """
        # Requiere US09: llamar cuando al menos dos jugadores estén listos.
        if self.status != "waiting":
            raise ValueError("La partida ya comenzó.")
        self._validate_now(now)
        self.status = "running"
        self._last_now = float(now)
        self._deadline = float(self.duration_seconds) if self.mode == "time" else None

    def update(self, scores: dict[str, int], now: float) -> dict:
        """
        Comprueba el tiempo y los puntos, y devuelve una copia del estado actual; el resultado no cambia tras finalizar.
        """
        # Requiere US15: proporcionar los puntos actuales; US09 o el bucle principal debe llamar periódicamente para comprobar el tiempo aunque no haya movimientos.
        if self._final_state is not None:
            return deepcopy(self._final_state)
        self._validate_scores(scores)
        self._advance_clock(now)
        self._last_scores = dict(scores)
        if not self.paused:
            self._evaluate(self._last_scores)
        return self._state()

    def pause(self, now: float) -> None:
        """
        Pausa cuando US10 detecta una desconexión y conserva el tiempo transcurrido hasta entonces.
        """
        if self.status == "finished":
            return
        self._advance_clock(now)
        if self.status == "waiting" or self.paused:
            return
        self._evaluate(self._last_scores)
        if self.status != "finished":
            self.paused = True

    def resume(self, now: float) -> None:
        """
        Reanuda cuando US10 confirma la reconexión del mismo jugador; la desconexión no cuenta como tiempo de juego.
        """
        if self.status == "finished":
            return
        self._validate_now(now)
        if self.status != "waiting" and self.paused:
            self.paused = False
            self._last_now = float(now)

    @staticmethod
    def _validate_scores(scores: dict[str, int]) -> None:
        if not isinstance(scores, dict):
            raise ValueError("Los puntajes deben ser un diccionario de jugadores.")
        for player_id, value in scores.items():
            if not isinstance(player_id, str) or not player_id.strip():
                raise ValueError("Cada puntaje necesita un identificador de jugador válido.")
            if type(value) is not int or value < 0:
                raise ValueError("Los puntajes deben ser enteros no negativos.")

    def _validate_now(self, now: float) -> None:
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
            raise ValueError("El reloj debe proporcionar un tiempo finito.")
        if self._observed_now is not None and float(now) + self._EPSILON < self._observed_now:
            raise ValueError("El reloj debe ser monotónico.")
        self._observed_now = float(now)

    def _advance_clock(self, now: float) -> None:
        self._validate_now(now)
        if self.status in {"running", "overtime"} and not self.paused:
            self._elapsed += max(0.0, float(now) - self._last_now)
        self._last_now = float(now)

    def _evaluate(self, scores: dict[str, int]) -> None:
        if self.status not in {"running", "overtime"} or len(scores) < 2:
            return
        maximum = max(scores.values())
        leaders = [player_id for player_id, score in scores.items() if score == maximum]
        if self.status == "running":
            if self.mode == "time":
                reached = self._elapsed + self._EPSILON >= self._deadline
                boundary = self._deadline
            else:
                reached = maximum >= self.target_score
                boundary = self._elapsed
            if not reached:
                return
            if len(leaders) == 1:
                self._finish(leaders[0], boundary)
                return
            self.status = "overtime"
            self.overtime_count = 1
            self._deadline = boundary + self.OVERTIME_SECONDS

        # Durante la prórroga solo se considera su reloj; alcanzar antes el puntaje objetivo no vuelve a finalizar la partida de inmediato.
        if self._elapsed + self._EPSILON < self._deadline:
            return
        if len(leaders) == 1:
            self._finish(leaders[0], self._deadline)
            return
        # Si el reloj salta varias rondas, calcula todas las prórrogas completas de una vez para evitar un bucle enorme.
        extra_rounds = int((self._elapsed - self._deadline + self._EPSILON) // self.OVERTIME_SECONDS) + 1
        self.overtime_count += extra_rounds
        self._deadline += extra_rounds * self.OVERTIME_SECONDS

    def _finish(self, winner_id: str, boundary: float) -> None:
        self.status = "finished"
        self.paused = False
        self.winner_id = winner_id
        self._elapsed = boundary
        # Entregar a US17 para mostrar la ventana de victoria.
        self._final_state = self._state()

    def _state(self) -> dict:
        remaining = None
        if self._deadline is not None:
            remaining = round(max(0.0, self._deadline - self._elapsed), 6)
        elif self.status == "waiting" and self.mode == "time":
            remaining = float(self.duration_seconds)
        if self.status == "waiting":
            message = "Esperando el inicio de la partida."
        elif self.status == "finished":
            message = f"¡Felicidades! Ganador: {self.winner_id}."
        elif self.paused:
            message = "Partida en pausa: esperando la reconexión."
        elif self.status == "overtime":
            message = f"Empate: prórroga {self.overtime_count} de 120 segundos. Se conservan los puntos."
        else:
            message = "Partida en curso."
        return {
            "status": self.status,
            "paused": self.paused,
            "winner_id": self.winner_id,
            "scores": dict(self._last_scores),
            "remaining_seconds": remaining,
            "elapsed_seconds": round(self._elapsed, 6),
            "overtime_count": self.overtime_count,
            "message": message,
        }

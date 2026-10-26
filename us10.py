"""
US10: identidad, conexiones y estado compartido de la arena para dos jugadores.

El servidor usa MultiplayerArena para gestionar a los jugadores; el cliente dibuja con draw_players.

US13 se encarga del envío y la recepción por la red; este archivo recibe la función de difusión como parámetro.

Los puntos de integración con US03, US06, US07, US09 y US11 se indican en los comentarios correspondientes.

Coloque este archivo en el mismo directorio que us15.py, us16.py y us17.py; no se necesitan archivos de proyecto adicionales.

El programa principal del equipo importa estos cuatro archivos; las US correspondientes aportan el inicio de sesión, la comunicación de red y el bucle principal de la arena.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import math
import inspect
import threading
import time
from typing import Callable
from uuid import uuid4

from us15 import Scoreboard
from us16 import GameRules
import acciones

import pygame

acciones.iniciar()  #activa las funciones de movimiento y sonido al presionar la tecla E

@dataclass
class Player:
    player_id: str
    username: str
    avatar_id: str
    x: float
    y: float
    connected: bool = True


class MultiplayerArena:
    """
    Objeto del servidor: una partida de dos jugadores comparte una instancia; los clientes no deben crear estados de partida independientes.
    """

    def __init__(self, broadcast: Callable[[dict], None], scoreboard: Scoreboard | None = None,
                 rules: GameRules | None = None, clock: Callable[[], float] = time.monotonic):
        if not callable(broadcast) or inspect.iscoroutinefunction(broadcast):
            raise ValueError("US13 debe proporcionar la función de difusión de red broadcast(message).")
        # Requiere US13: esta función encola el JSON para difundirlo a todos los clientes sin bloquear el hilo del juego.
        # Para WebSockets asíncronos de FastAPI, use una función síncrona que encole mensajes; no pase directamente una función async def.
        self._broadcast = broadcast
        self._clock = clock
        self.scoreboard = scoreboard if scoreboard is not None else Scoreboard()
        # Requiere US08: cree GameRules con la configuración elegida y páselo mediante el parámetro rules.
        self.rules = rules if rules is not None else GameRules()
        self.match_id = uuid4().hex
        self._players: dict[str, Player] = {}
        self._connections: dict[str, str] = {}
        self._active = False
        self._final_result: dict | None = None
        self._lock = threading.RLock()
        self._rule_state = self.rules.update(self.scoreboard.scores(), self._clock())

    @staticmethod
    def _text(value: str, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} no puede estar vacío.")
        return value.strip()

    @staticmethod
    def _position(x: float, y: float) -> tuple[float, float]:
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (x, y)):
            raise ValueError("Las coordenadas deben ser valores numéricos finitos.")
        return float(x), float(y)

    def join_player(self, connection_id: str, player_id: str, username: str,
                    avatar_id: str, x: float, y: float) -> dict:
        """
        Agrega un jugador autenticado; tras desconectarse, la misma identidad puede recuperar su posición y puntaje con una nueva conexión.
        """
        # Requiere US03/US04: player_id y username deben proceder de una sesión validada y del perfil del jugador.
        # Requiere US06: proporcione el avatar_id elegido por el jugador; los dos jugadores deben tener avatares diferentes.
        # Requiere US09: al ingresar por primera vez, proporcione una posición inicial válida x, y; no confíe directamente en las coordenadas del cliente.
        connection_id = self._text(connection_id, "connection_id")
        player_id = self._text(player_id, "player_id")
        username = self._text(username, "username")
        avatar_id = self._text(avatar_id, "avatar_id")
        x, y = self._position(x, y)
        with self._lock:
            if self._final_result is not None:
                raise ValueError("La partida terminó; cree un nuevo MultiplayerArena para otra partida.")
            if connection_id in self._connections:
                raise ValueError("Esta conexión ya está vinculada a un jugador.")
            existing = self._players.get(player_id)
            if existing is not None:
                if existing.connected:
                    raise ValueError("Un mismo jugador no puede ocupar dos conexiones.")
                if (existing.username, existing.avatar_id) != (username, avatar_id):
                    raise ValueError("No se puede cambiar la identidad ni el avatar del jugador al reconectarse.")
                existing.connected = True
            else:
                if self.rules.status != "waiting":
                    raise ValueError("Después de iniciar la partida, solo pueden reconectarse los jugadores originales.")
                if len(self._players) >= 2:
                    raise ValueError("La arena de este MVP solo admite dos jugadores diferentes.")
                if any(p.username.casefold() == username.casefold() for p in self._players.values()):
                    raise ValueError("Los dos jugadores deben tener nombres de usuario diferentes.")
                if any(p.avatar_id == avatar_id for p in self._players.values()):
                    raise ValueError("Los dos jugadores deben tener avatares diferentes.")
                self.scoreboard.add_player(player_id)
                self._players[player_id] = Player(player_id, username, avatar_id, x, y)
            self._connections[connection_id] = player_id
            state = self._snapshot_locked()
            self._broadcast(deepcopy(state))
            return state

    def get_player_id(self, connection_id: str) -> str:
        """
        Identifica al autor por su conexión para impedir que un mensaje suplante a otro jugador.
        """
        with self._lock:
            try:
                return self._connections[connection_id]
            except (KeyError, TypeError) as exc:
                raise ValueError("La conexión no está vinculada a un jugador autenticado.") from exc

    def has_two_players(self) -> bool:
        with self._lock:
            return len(self._connections) == 2

    def begin_match(self, now: float | None = None) -> None:
        # Requiere US09: invoque este método cuando ambos jugadores estén listos; también reanuda la partida tras una reconexión.
        now = self._clock() if now is None else now
        with self._lock:
            if self._final_result is not None:
                raise ValueError("No se puede volver a iniciar una partida finalizada.")
            if len(self._connections) != 2:
                raise ValueError("Se necesitan al menos dos jugadores diferentes conectados.")
            if self.rules.status == "waiting":
                self.rules.start(now)
            elif self.rules.paused:
                self.rules.resume(now)
            else:
                raise ValueError("La partida ya está en curso.")
            self._rule_state = self.rules.update(self.scoreboard.scores(), now)
            if self._rule_state["status"] == "finished":
                self.finish_match(self._rule_state)
                return
            self._active = True
            self._broadcast(deepcopy(self._snapshot_locked()))

    def confirm_movement(self, connection_id: str, x: float, y: float,
                         now: float | None = None) -> bool:
        """
        Se invoca después de que US11 confirme el movimiento; actualiza posición y puntaje de forma atómica y difunde el resultado a ambos jugadores.
        """
        # Requiere US11: valide límites, colisiones, velocidad y operaciones repetidas antes de pasar las coordenadas x, y confirmadas.
        # connection_id procede de la conexión real de US13; no lo sustituya por un player_id declarado en el mensaje.
        x, y = self._position(x, y)
        now = self._clock() if now is None else now
        with self._lock:
            player_id = self.get_player_id(connection_id)
            if not self._active or self._final_result is not None:
                return False
            # US16 comprueba primero el límite de tiempo; no se cuentan los movimientos recibidos después del vencimiento.
            self._rule_state = self.rules.update(self.scoreboard.scores(), now)
            if self._rule_state["status"] == "finished":
                self.finish_match(self._rule_state)
                return False
            if self._rule_state["paused"]:
                return False
            player = self._players[player_id]
            if (player.x, player.y) == (x, y):
                return False
            # US15: cada movimiento real confirmado suma un punto; el puntaje no depende de los fotogramas dibujados.
            self.scoreboard.award_movement(player_id)
            player.x, player.y = x, y
            self._rule_state = self.rules.update(self.scoreboard.scores(), now)
            if self._rule_state["status"] == "finished":
                self.finish_match(self._rule_state)
            else:
                self._broadcast(deepcopy(self._snapshot_locked()))
            return True

    def disconnect_player(self, connection_id: str, now: float | None = None) -> None:
        now = self._clock() if now is None else now
        with self._lock:
            player_id = self._connections.pop(connection_id, None)
            if player_id is None:
                return
            self._players[player_id].connected = False
            self._active = False
            # Requiere US13: invoque este método al detectar una desconexión.
            self._rule_state = self.rules.update(self.scoreboard.scores(), now)
            self.rules.pause(now)
            self._rule_state = self.rules.update(self.scoreboard.scores(), now)
            if self._rule_state["status"] == "finished":
                self.finish_match(self._rule_state)
            else:
                self._broadcast(deepcopy(self._snapshot_locked()))

    def tick(self, now: float | None = None) -> dict:
        # Requiere el bucle principal de US09: invoque este método periódicamente, por ejemplo cada 0,1 segundos, para detectar el final aunque nadie se mueva.
        # Requiere US13: la función de difusión debe enviar a todos los clientes las actualizaciones de tiempo y estado generadas por este método.
        now = self._clock() if now is None else now
        with self._lock:
            if self._final_result is not None:
                return deepcopy(self._final_result)
            self._rule_state = self.rules.update(self.scoreboard.scores(), now)
            if self._rule_state["status"] == "finished":
                return self.finish_match(self._rule_state)
            state = self._snapshot_locked()
            self._broadcast(deepcopy(state))
            return state

    def snapshot(self) -> dict:
        with self._lock:
            if self._final_result is not None:
                return deepcopy(self._final_result)
            return deepcopy(self._snapshot_locked())

    def _snapshot_locked(self) -> dict:
        scores = self.scoreboard.scores()
        players = [dict(asdict(p), score=scores[p.player_id]) for p in self._players.values()]
        return dict(self._rule_state, type="arena_state", match_id=self.match_id,
                    players=players, scores=scores, active=self._active)

    def finish_match(self, rule_state: dict) -> dict:
        """
        Recibe la decisión final de US16, detiene los movimientos y envía a los clientes un resultado que puede entregarse a US17.
        """
        # Bucle principal del juego: state = rules.update(arena.scoreboard.scores(), now).
        # Si state['status'] == 'finished', invoque este método; de lo contrario, continúe la partida o la prórroga.
        with self._lock:
            if self._final_result is not None:
                return deepcopy(self._final_result)
            if rule_state.get("status") != "finished":
                raise ValueError("US16 debe proporcionar un resultado final con status='finished'.")
            winner_id = rule_state.get("winner_id")
            final_scores = rule_state.get("scores")
            if winner_id not in self._players or not isinstance(final_scores, dict):
                raise ValueError("El resultado final no contiene un ganador válido o los puntajes definitivos.")
            if set(final_scores) != set(self._players) or final_scores != self.scoreboard.scores():
                raise ValueError("Los puntajes de US16 deben coincidir con los puntajes más recientes de esta partida.")
            self._active = False
            result = self._snapshot_locked()
            result.update(deepcopy(rule_state))
            result["type"] = "match_finished"
            self._final_result = result
            # Requiere US13: al recibir match_finished, el cliente invoca la función de US17
            # launch_victory_window(result); no abra en el servidor las ventanas de todos los jugadores.
            # El cliente usa match_id para evitar duplicados y abrir una sola ventana de victoria por partida.
            # Requiere US06: el cliente obtiene primero, mediante avatar_id, la ruta local del avatar real en caché,
            # y la asigna a player['avatar_path'] para que US17 muestre la imagen elegida por cada jugador.
            self._broadcast(deepcopy(result))
            return deepcopy(result)


def draw_players(screen, state: dict, avatar_images: dict, *, offset=(0, 0), size=40):
    """
    El cliente dibuja a los dos jugadores a partir del estado difundido por el servidor; no calcula movimientos ni puntajes.
    """

    # Requiere US07: proporcione screen con la arena dibujada; offset indica la posición de su esquina superior izquierda en la ventana.
    # Requiere US13: state contiene el último estado difundido por el servidor; no actualice únicamente la posición del jugador local.
    # Requiere US06: avatar_images = {avatar_id: imagen del avatar como pygame.Surface}.
    font = pygame.font.Font(None, 24)
    for player in state.get("players", []):
        avatar = avatar_images.get(player["avatar_id"])
        if avatar is None:
            raise ValueError(f"US06 debe proporcionar la imagen del avatar: {player['avatar_id']}")
        image = pygame.transform.smoothscale(avatar, (size, size))
        center = (round(offset[0] + player["x"]), round(offset[1] + player["y"]))
        screen.blit(image, image.get_rect(center=center))
        label = font.render(player["username"], True, (240, 240, 240))
        screen.blit(label, label.get_rect(midbottom=(center[0], center[1] - size // 2 - 4)))

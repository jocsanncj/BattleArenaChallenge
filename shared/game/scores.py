"""
US15: puntuación básica y visualización de puntos con Pygame, sin leer entradas ni mover personajes.
"""

from __future__ import annotations
import pygame

class Scoreboard:
    """
    Guarda los puntos por ID de jugador proporcionado por US10; suma un punto por cada movimiento real completado.
    """

    def __init__(self) -> None:
        self._scores: dict[str, int] = {}

    @staticmethod
    def _validate_id(player_id: str) -> None:
        if not isinstance(player_id, str) or not player_id.strip():
            raise ValueError("El identificador del jugador debe ser un texto no vacío.")

    def add_player(self, player_id: str) -> None:
        """
        Registra al jugador; registrar de nuevo el mismo ID no borra los puntos existentes.
        """
        # Requiere US10: recibir el ID de un jugador cuya identidad ya fue confirmada; otro jugador no debe proporcionarlo en su nombre.
        self._validate_id(player_id)
        self._scores.setdefault(player_id, 0)

    def award_movement(self, player_id: str) -> int:
        """
        Suma un punto por un movimiento válido y devuelve el nuevo puntaje del jugador.
        """
        # Requiere US11: llamar solo cuando el servidor confirme un movimiento real completado; no sumar puntos en cada fotograma.
        self._validate_id(player_id)
        if player_id not in self._scores:
            raise ValueError("El jugador no está registrado en el marcador.")
        self._scores[player_id] += 1
        return self._scores[player_id]

    def scores(self) -> dict[str, int]:
        """
        Devuelve una copia para evitar que quien llama modifique accidentalmente los puntos internos.
        """
        # Requiere US10/US13: transmitir estos puntos confirmados a todos los jugadores y actualizar la interfaz.
        return dict(self._scores)

    def reset(self) -> None:
        """
        Reinicia los puntos a cero al comenzar otra partida, conservando los jugadores registrados.
        """
        for player_id in self._scores:
            self._scores[player_id] = 0


def draw_scores(screen, state: dict, position=(20, 20)) -> None:
    """
    Dibuja los puntos de ambos jugadores en cada fotograma usando el último estado del servidor; esta función no suma puntos.
    """
    

    # Requiere US07: proporcionar la ventana de la arena y llamar en cada fotograma; requiere US13: reemplazar state al recibir una transmisión.
    font = pygame.font.Font(None, 28)
    for index, player in enumerate(state.get("players", [])):
        label = font.render(f"{player['username']}: {player['score']}", True, (255, 220, 90))
        screen.blit(label, (position[0], position[1] + index * 30))

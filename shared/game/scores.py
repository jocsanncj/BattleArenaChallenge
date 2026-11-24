"""
US15: puntuación básica y visualización de puntos con Pygame, sin leer entradas ni mover personajes.
"""

from __future__ import annotations
import pygame

class Scoreboard:
    """
    Guarda los puntos por ID de jugador; suma un punto por cada extracción válida del reactor.
    """
    ## @brief US-15: inicializa el marcador sin puntajes de jugadores.
    def __init__(self) -> None:
        self._scores: dict[str, int] = {}
    ## @brief US-15: rechaza identificadores de jugador vacíos o inválidos.
    @staticmethod
    def _validate_id(player_id: str) -> None:
        if not isinstance(player_id, str) or not player_id.strip():
            raise ValueError("El identificador del jugador debe ser un texto no vacío.")
    ## @brief US-10 y US-15: registra al jugador y conserva sus puntos si ya existe.
    def add_player(self, player_id: str) -> None:
        """
        Registra al jugador; registrar de nuevo el mismo ID no borra los puntos existentes.
        """
        # Requiere US10: recibir el ID de un jugador cuya identidad ya fue confirmada; otro jugador no debe proporcionarlo en su nombre.
        self._validate_id(player_id)
        self._scores.setdefault(player_id, 0)
    ## @brief US-18–US-19: suma el punto obtenido por una extracción válida.
    def award_extraction(self, player_id: str) -> int:
        """Suma un punto por una extracción válida del reactor."""
        self._validate_id(player_id)
        if player_id not in self._scores:
            raise ValueError("El jugador no está registrado en el marcador.")
        self._scores[player_id] += 1
        return self._scores[player_id]
    ## @brief US-22: suma los puntos adicionales concedidos por un evento.
    def add_points(self, player_id: str, points: int) -> int:
        """Agrega puntos de un evento especial a un jugador registrado."""
        self._validate_id(player_id)
        if player_id not in self._scores:
            raise ValueError("El jugador no está registrado en el marcador.")
        if type(points) is not int or points < 0:
            raise ValueError("Los puntos deben ser un entero no negativo.")
        self._scores[player_id] += points
        return self._scores[player_id]

    ## @brief US-21–US-22: aplica una penalización sin permitir puntajes negativos.
    def remove_points(self, player_id: str, points: int = 1) -> int:
        """Resta puntos sin permitir que el marcador quede por debajo de cero."""
        self._validate_id(player_id)
        if player_id not in self._scores:
            raise ValueError("El jugador no está registrado en el marcador.")
        if type(points) is not int or points < 0:
            raise ValueError("Los puntos deben ser un entero no negativo.")
        self._scores[player_id] = max(0, self._scores[player_id] - points)
        return self._scores[player_id]

    ## @brief US-13 y US-15: devuelve una copia del marcador para sincronizar clientes.
    def scores(self) -> dict[str, int]:
        """
        Devuelve una copia para evitar que quien llama modifique accidentalmente los puntos internos.
        """
        # Requiere US10/US13: transmitir estos puntos confirmados a todos los jugadores y actualizar la interfaz.
        return dict(self._scores)
    ## @brief US-15: pone a cero los puntos antes de una nueva partida.
    def reset(self) -> None:
        """
        Reinicia los puntos a cero al comenzar otra partida, conservando los jugadores registrados.
        """
        for player_id in self._scores:
            self._scores[player_id] = 0
## @brief US-07 y US-15: dibuja los puntajes recibidos sin modificarlos.
def draw_scores(screen, state: dict, position=(20, 20)) -> None:
    """
    Dibuja los puntos de ambos jugadores en cada fotograma usando el último estado del servidor; esta función no suma puntos.
    """
    # Requiere US07: proporcionar la ventana de la arena y llamar en cada fotograma; requiere US13: reemplazar state al recibir una transmisión.
    font = pygame.font.Font(None, 28)
    for index, player in enumerate(state.get("players", [])):
        label = font.render(f"{player['username']}: {player['score']}", True, (255, 220, 90))
        screen.blit(label, (position[0], position[1] + index * 30))

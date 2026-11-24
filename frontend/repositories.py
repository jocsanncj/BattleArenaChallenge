"""Repositorios del cliente para leer y modificar el estado en el servidor."""

from dataclasses import asdict
from frontend.escenarios import ConfiguracionEscenario
from typing import Optional

from shared.data import (
    ConfiguracionPartida,
    EleccionAvatar,
    Jugador,
    Partida,
    RepositorioAvatares,
    RepositorioPartida,
    RepositorioPartidaOnline,
)


class RepositorioAvataresServidor(RepositorioAvatares):
    """Guarda y recupera elecciones de avatar mediante la API autenticada."""

    ## @brief Prepara la caché local de elecciones consultadas al servidor.
    def __init__(self) -> None:
        self._cache: dict[int, Optional[EleccionAvatar]] = {}

    @staticmethod
    ## @brief Obtiene el cliente HTTP autenticado del usuario actual.
    def _cliente_token():
        from .auth.service import cliente_juego, token_para_juego

        return cliente_juego(), token_para_juego()

    ## @brief US-06: carga y almacena en caché la selección de avatar.
    def obtener(self, id_usuario: int) -> Optional[EleccionAvatar]:
        if id_usuario in self._cache:
            return self._cache[id_usuario]

        cliente, token = self._cliente_token()
        respuesta = cliente.obtener_avatar(token, id_usuario)
        eleccion = (
            EleccionAvatar(respuesta["tipo"], respuesta["valor"])
            if isinstance(respuesta, dict)
            and respuesta.get("tipo")
            and respuesta.get("valor")
            else None
        )
        self._cache[id_usuario] = eleccion
        return eleccion

    ## @brief US-06: envía la selección de avatar y actualiza la caché.
    def guardar(self, id_usuario: int, eleccion: EleccionAvatar) -> None:
        cliente, token = self._cliente_token()
        cliente.guardar_avatar(token, {"tipo": eleccion.tipo, "valor": eleccion.valor})
        self._cache[id_usuario] = eleccion


class RepositorioPartidaServidor(RepositorioPartida):
    """Envía acciones de juego al servidor y recibe su estado autoritativo."""
    @staticmethod
    ## @brief Obtiene el cliente HTTP autenticado para las acciones de partida.
    def _cliente_token():
        from .auth.service import cliente_juego, token_para_juego
        return cliente_juego(), token_para_juego()
    ## @brief US-13: carga y valida el estado autoritativo de la partida.
    def cargar(self) -> Partida:
        cliente, token = self._cliente_token()
        respuesta = cliente.obtener_partida(token)
        datos = respuesta.get("partida")
        if not isinstance(datos, dict):
            raise ValueError("El servidor devolvió un estado de partida inválido.")
        try:
            return Partida(
                ConfiguracionEscenario(**datos.get("configuracion", {})),
                datos.get("estado", "esperando"),
                datos.get("iniciada_en"),
                [Jugador(**jugador) for jugador in datos.get("jugadores", [])],
                respuesta.get("game"),
            )
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("El servidor devolvió un estado de partida inválido.") from error
    ## @brief US-08: envía al servidor la configuración editable de la partida.
    def guardar(self, partida: Partida) -> None:
        cliente, token = self._cliente_token()
        cliente.guardar_configuracion_partida(token, asdict(partida.configuracion))
    ## @brief US-10: solicita al servidor unir al usuario a la sala.
    def unirse_online(self) -> None:
        cliente, token = self._cliente_token()
        cliente.unirse_partida(token)
    ## @brief US-10: solicita al servidor retirar al usuario de la sala.
    def salir_online(self) -> None:
        cliente, token = self._cliente_token()
        cliente.salir_partida(token)
    ## @brief US-09: solicita al servidor iniciar la partida.
    def iniciar_online(self) -> None:
        cliente, token = self._cliente_token()
        cliente.iniciar_partida(token)
    ## @brief US-11: envía un movimiento y propaga el error reportado por el servidor.
    def mover_online(self, direccion: str) -> None:
        cliente, token = self._cliente_token()
        respuesta = cliente.mover_jugador(token, direccion)
        if isinstance(respuesta, dict) and respuesta.get("error"):
            raise ValueError(respuesta["error"])
    ## @brief US-18: envía una interacción idempotente con el reactor.
    def interaccion_reactor_online(self, accion: str, event_id: str) -> None:
        cliente, token = self._cliente_token()
        cliente.interactuar_reactor(token, accion, event_id)


__all__ = ["RepositorioAvataresServidor", "RepositorioPartidaServidor"]

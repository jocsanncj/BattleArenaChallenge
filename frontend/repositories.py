"""Repositorios del cliente para leer y modificar el estado en el servidor."""

from dataclasses import asdict
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

    def __init__(self) -> None:
        self._cache: dict[int, Optional[EleccionAvatar]] = {}

    @staticmethod
    def _cliente_token():
        from .auth.service import cliente_juego, token_para_juego

        return cliente_juego(), token_para_juego()

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

    def guardar(self, id_usuario: int, eleccion: EleccionAvatar) -> None:
        cliente, token = self._cliente_token()
        cliente.guardar_avatar(token, {"tipo": eleccion.tipo, "valor": eleccion.valor})
        self._cache[id_usuario] = eleccion


class RepositorioPartidaServidor(RepositorioPartida):
    """Envía acciones de juego al servidor y recibe su estado autoritativo."""

    @staticmethod
    def _cliente_token():
        from .auth.service import cliente_juego, token_para_juego

        return cliente_juego(), token_para_juego()

    def cargar(self) -> Partida:
        cliente, token = self._cliente_token()
        respuesta = cliente.obtener_partida(token)
        datos = respuesta.get("partida")
        if not isinstance(datos, dict):
            raise ValueError("El servidor devolvió un estado de partida inválido.")

        try:
            return Partida(
                ConfiguracionPartida(**datos.get("configuracion", {})),
                datos.get("estado", "esperando"),
                datos.get("iniciada_en"),
                [Jugador(**jugador) for jugador in datos.get("jugadores", [])],
                respuesta.get("game"),
            )
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("El servidor devolvió un estado de partida inválido.") from error

    def guardar(self, partida: Partida) -> None:
        cliente, token = self._cliente_token()
        cliente.guardar_configuracion_partida(token, asdict(partida.configuracion))

    def unirse_online(self) -> None:
        cliente, token = self._cliente_token()
        cliente.unirse_partida(token)

    def salir_online(self) -> None:
        cliente, token = self._cliente_token()
        cliente.salir_partida(token)

    def iniciar_online(self) -> None:
        cliente, token = self._cliente_token()
        cliente.iniciar_partida(token)

    def mover_online(self, direccion: str) -> None:
        cliente, token = self._cliente_token()
        cliente.mover_jugador(token, direccion)


__all__ = ["RepositorioAvataresServidor", "RepositorioPartidaServidor"]

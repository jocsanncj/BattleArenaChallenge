"""Sala de espera, lista de jugadores y acceso a la partida."""

from typing import List, Optional

import pygame

from shared.domain import ServicioPartida
from .base import (ACENTO, ERROR, EXITO, GRIS, Boton, Contexto, Pantalla, describir_configuracion)

class PantallaSala(Pantalla):
    """
    Descripción:
        Sala de espera. Al abrirse, el jugador entra a la sala; la pantalla muestra
        quiénes están, la configuración actual y permite abrir la configuración, iniciar
        la partida o volver. Cada cierto tiempo vuelve a leer la partida, de modo que si
        otro jugador la inicia, esta pantalla pasa sola a la arena.
    Atributos:
        INTERVALO_MS (int): cada cuántos milisegundos se vuelve a leer la partida (500).
        _partida (Partida): última copia leída de la partida.
        _ultimo (int): momento (en ms) de la última lectura.
    """

    INTERVALO_MS = 500

    def __init__(self, ctx: Contexto, aviso: str = ""):
        """
        Descripción:
            Une al jugador a la sala mediante el servicio (esto puede lanzar un ErrorApp si la
            sala está llena o la partida ya inició; en ese caso la pantalla no se abre y
            frontend/account/online.py muestra el error). Luego carga la partida y anota el momento de la
            lectura.
        Entradas:
            ctx (Contexto): contexto de la aplicación.
            aviso (str): mensaje inicial opcional, que se muestra en rojo.
        Salidas:
            Ninguna.
        """
        super().__init__(ctx)
        ctx.partida.unirse(ctx.id_usuario, ctx.nombre_usuario)
        self._partida, self._ultimo = ctx.partida.obtener_partida(), pygame.time.get_ticks()
        if aviso:
            self.mensaje, self.color_mensaje = aviso, ERROR

    def botones(self) -> List[Boton]:
        """
        Descripción:
            Arma los tres botones: 'Configuración' (devuelve 'configuracion'), 'Iniciar
            partida' (en verde, ejecuta _iniciar) y 'Volver' (en gris, devuelve 'volver').
        Entradas:
            Ninguna.
        Salidas:
            List[Boton]: botones de la pantalla.
        """
        return [Boton(pygame.Rect(60, 400, 200, 40), "Configuración", lambda: "configuracion"),
                Boton(pygame.Rect(280, 400, 200, 40), "Iniciar partida", self._iniciar, EXITO),
                Boton(pygame.Rect(500, 400, 200, 40), "Volver", lambda: "volver", GRIS)]

    def _iniciar(self) -> str:
        """
        Descripción:
            Acción del botón 'Iniciar partida': le pide al servicio que inicie la partida. Si
            faltan jugadores el servicio lanza un ErrorApp ('Esperando jugador...') que se
            muestra en pantalla. Si todo sale bien devuelve 'arena' para pasar a la arena.
        Entradas:
            Ninguna.
        Salidas:
            str: 'arena' cuando la partida se inició.
        """
        self.ctx.partida.iniciar()
        return "arena"

    def actualizar(self) -> Optional[str]:
        """
        Descripción:
            Cada 500 ms vuelve a leer la partida desde el repositorio. Si descubre que ya está
            en estado 'jugando' y este jugador forma parte de ella, significa que otro jugador
            la inició, así que devuelve 'arena' para entrar también.
        Entradas:
            Ninguna.
        Salidas:
            Optional[str]: 'arena' si la partida ya inició, o None para continuar.
        """
        ahora = pygame.time.get_ticks()
        if ahora - self._ultimo >= self.INTERVALO_MS:
            self._ultimo, self._partida = ahora, self.ctx.partida.obtener_partida()
            if self._partida.estado == "jugando" and any(
                    j.id_usuario == self.ctx.id_usuario for j in self._partida.jugadores):
                return "arena"
        return None

    def dibujar(self, superficie) -> None:
        """
        Descripción:
            Dibuja la sala. Muestra un mensaje de estado: 'Esperando jugador...' mientras haya
            menos jugadores que el mínimo, o 'Jugadores listos...' cuando ya pueden iniciar
            (con un aviso adicional si está activo el modo provisional de un jugador). Luego
            lista los jugadores con su avatar y nombre, marcando '(tú)' al jugador de este
            programa y mostrando cuántos hay del total posible, la configuración actual y,
            por último, los botones.
        Entradas:
            superficie (pygame.Surface): superficie donde se dibuja.
        Salidas:
            Ninguna.
        """
        self.dibujar_encabezado(superficie, "Sala de espera")
        p, total = self._partida, min(2, len(self.ctx.partida.arena.puntos_inicio()))
        esperando = len(p.jugadores) < ServicioPartida.JUGADORES_MINIMOS
        msg = "Esperando jugador..." if esperando else "Jugadores listos. Pueden iniciar la partida."
        if esperando and ServicioPartida.PERMITIR_UN_JUGADOR:
            msg += " (modo provisional: puede iniciar solo)"
        color = EXITO if not esperando else (ACENTO if ServicioPartida.PERMITIR_UN_JUGADOR else ERROR)
        self.texto(superficie, msg, (60, 90), self.fuente, color)
        self.texto(superficie, f"Jugadores ({len(p.jugadores)}/{total})", (60, 130), self.fuente)
        for i, j in enumerate(p.jugadores):
            superficie.blit(self.ctx.avatares.obtener_superficie(j.id_usuario, 32), (60, 165 + i * 40))
            self.texto(superficie, j.nombre_usuario + (" (tú)" if j.id_usuario == self.ctx.id_usuario else ""),
                       (104, 174 + i * 40))
        self.texto(superficie, "Configuración actual", (430, 130), self.fuente)
        for i, linea in enumerate(describir_configuracion(p.configuracion)):
            self.texto(superficie, linea, (430, 165 + i * 28))
        self.dibujar_botones(superficie)

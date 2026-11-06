"""Edición y guardado de las reglas configurables de la partida."""

from dataclasses import replace
from typing import List

import pygame

from .base import Boton, EXITO, GRIS, Contexto, Pantalla

class PantallaConfiguracion(Pantalla):
    """
    Descripción:
        Pantalla para configurar la partida: elegir si termina por tiempo o por puntos,
        ajustar ese valor y ajustar los segundos de congelación. Trabaja sobre una copia
        de la configuración: los cambios solo se aplican cuando se pulsa 'Guardar'.
        ESC equivale a 'Volver'.
    Atributos:
        tecla_escape (str): 'volver'; al pulsar ESC la pantalla se cierra con ese texto.
        cfg (ConfiguracionPartida): copia editable de la configuración guardada.
    """

    tecla_escape = "volver"

    def __init__(self, ctx: Contexto):
        """
        Descripción:
            Verifica que la partida todavía se pueda configurar (si ya inició, el servicio
            lanza un ErrorApp y la pantalla no se abre) y crea una copia de la configuración
            guardada para editarla sin modificar la original.
        Entradas:
            ctx (Contexto): contexto de la aplicación.
        Salidas:
            Ninguna.
        """
        super().__init__(ctx)
        ctx.partida.verificar_configurable()
        self.cfg = replace(ctx.partida.obtener_partida().configuracion)

    def _campo_valor(self):
        """
        Descripción:
            Indica qué valor se edita con los botones '-' y '+' de arriba, según el modo de
            fin: minutos (de 1 a 60, de 1 en 1) si el modo es 'tiempo', o puntos (de 1 a 999,
            de 5 en 5) en el modo 'puntos'.
        Entradas:
            Ninguna.
        Salidas:
            tuple: (nombre del campo, texto a mostrar, mínimo, máximo, paso).
        """
        if self.cfg.modo_fin == "tiempo":
            return "minutos_fin", "Minutos de la partida", 1, 60, 1
        return "puntos_fin", "Puntos para terminar", 1, 999, 5

    def _cambiar(self, campo: str, delta: int, minimo: int, maximo: int) -> None:
        """
        Descripción:
            Suma o resta una cantidad a un campo de la configuración, sin salirse del rango
            permitido: el resultado nunca baja del mínimo ni sube del máximo.
        Entradas:
            campo (str): nombre del campo de ConfiguracionPartida que se modifica.
            delta (int): cantidad a sumar (negativa para restar).
            minimo (int): valor mínimo permitido.
            maximo (int): valor máximo permitido.
        Salidas:
            Ninguna. Efecto: el campo de la copia queda actualizado.
        """
        setattr(self.cfg, campo, max(minimo, min(maximo, getattr(self.cfg, campo) + delta)))

    def _alternar_modo(self) -> None:
        """
        Descripción:
            Cambia el modo de fin de partida: de 'tiempo' a 'puntos' y viceversa.
        Entradas:
            Ninguna.
        Salidas:
            Ninguna. Efecto: modo_fin de la copia cambiado.
        """
        self.cfg.modo_fin = "puntos" if self.cfg.modo_fin == "tiempo" else "tiempo"

    def _guardar(self) -> None:
        """
        Descripción:
            Acción del botón 'Guardar': envía la copia al servicio, que la valida y la guarda
            en la partida, y muestra un mensaje de confirmación. Si el servicio rechaza los
            datos lanza un ErrorApp que se muestra en pantalla.
        Entradas:
            Ninguna.
        Salidas:
            Ninguna.
        """
        self.ctx.partida.actualizar_configuracion(self.cfg)
        self.exito("Configuración guardada.")

    def botones(self) -> List[Boton]:
        """
        Descripción:
            Arma los botones: el que alterna el modo de fin, los '-' y '+' del valor principal
            (minutos o puntos), los '-' y '+' de los segundos de congelación (de 1 a 30),
            'Guardar' (verde) y 'Volver' (gris).
        Entradas:
            Ninguna.
        Salidas:
            List[Boton]: botones de la pantalla.
        """
        campo, _, minimo, maximo, paso = self._campo_valor()
        modo = "Tiempo" if self.cfg.modo_fin == "tiempo" else "Puntos"
        return [
            Boton(pygame.Rect(60, 110, 360, 40), f"Fin de partida por: {modo}", self._alternar_modo),
            Boton(pygame.Rect(420, 180, 40, 36), "-", lambda: self._cambiar(campo, -paso, minimo, maximo)),
            Boton(pygame.Rect(540, 180, 40, 36), "+", lambda: self._cambiar(campo, paso, minimo, maximo)),
            Boton(pygame.Rect(420, 250, 40, 36), "-", lambda: self._cambiar("segundos_congelacion", -1, 1, 30)),
            Boton(pygame.Rect(540, 250, 40, 36), "+", lambda: self._cambiar("segundos_congelacion", 1, 1, 30)),
            Boton(pygame.Rect(60, 350, 200, 40), "Guardar", self._guardar, EXITO),
            Boton(pygame.Rect(280, 350, 200, 40), "Volver", lambda: "volver", GRIS)]

    def dibujar(self, superficie) -> None:
        """
        Descripción:
            Dibuja el encabezado, las dos líneas de configuración con sus valores actuales (el
            valor principal según el modo y los segundos de congelación) y los botones.
        Entradas:
            superficie (pygame.Surface): superficie donde se dibuja.
        Salidas:
            Ninguna.
        """
        self.dibujar_encabezado(superficie, "Configuración del juego")
        campo, texto, *_ = self._campo_valor()
        self.texto(superficie, texto, (60, 190), self.fuente)
        self.texto(superficie, str(getattr(self.cfg, campo)), (475, 190), self.fuente)
        self.texto(superficie, "Segundos congelado", (60, 260), self.fuente)
        self.texto(superficie, str(self.cfg.segundos_congelacion), (475, 260), self.fuente)
        self.dibujar_botones(superficie)


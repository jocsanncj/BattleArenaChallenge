"""Selección y carga del avatar del jugador."""

from typing import List

import pygame

from .base import (ACENTO, ERROR, EXITO, PANEL, Boton, Contexto, Pantalla, elegir_archivo_imagen)

class PantallaAvatar(Pantalla):
    """
    Descripción:
        Pantalla donde el jugador elige su avatar: puede escoger uno de los avatares
        predeterminados o cargar una imagen propia, y ver cuál es su avatar actual. El
        botón 'Continuar' avanza a la sala de espera.
    Atributos:
        MINIATURA (int): lado en píxeles de cada avatar del catálogo en pantalla (80).
    """

    MINIATURA = 80

    def __init__(self, ctx: Contexto, aviso: str = ""):
        """
        Descripción:
            Crea la pantalla. Si recibe un aviso (por ejemplo, un error que ocurrió en otra
            pantalla y devolvió al jugador aquí) lo muestra en rojo.
        Entradas:
            ctx (Contexto): contexto de la aplicación.
            aviso (str): mensaje inicial opcional.
        Salidas:
            Ninguna.
        """
        super().__init__(ctx)
        if aviso:
            self.mensaje, self.color_mensaje = aviso, ERROR

    def _rect_miniatura(self, i: int) -> pygame.Rect:
        """
        Descripción:
            Calcula el rectángulo de la miniatura número i. Las miniaturas se colocan en una
            fila horizontal a partir de x = 60, con 25 píxeles de separación, a y = 130.
        Entradas:
            i (int): posición de la miniatura dentro del catálogo, empezando en 0.
        Salidas:
            pygame.Rect: zona que ocupa la miniatura.
        """
        return pygame.Rect(60 + i * (self.MINIATURA + 25), 130, self.MINIATURA, self.MINIATURA)

    def botones(self) -> List[Boton]:
        """
        Descripción:
            Arma los botones de la pantalla: uno sin etiqueta por cada avatar del catálogo
            (se ven como la imagen del avatar y al hacer clic lo eligen), el botón 'Cargar
            imagen...' y el botón verde 'Continuar', que devuelve 'siguiente'.
        Entradas:
            Ninguna.
        Salidas:
            List[Boton]: botones de la pantalla.
        """
        miniaturas = [Boton(self._rect_miniatura(i), "", lambda a=a: self._elegir(a))
                      for i, a in enumerate(self.ctx.avatares.listar_predeterminados())]
        return miniaturas + [Boton(pygame.Rect(60, 290, 260, 40), "Cargar imagen...", self._subir),
                             Boton(pygame.Rect(60, 350, 260, 40), "Continuar", lambda: "siguiente", EXITO)]

    def _elegir(self, avatar) -> None:
        """
        Descripción:
            Acción de una miniatura: guarda el avatar elegido a través del servicio y muestra
            un mensaje de confirmación con su nombre.
        Entradas:
            avatar (AvatarPredeterminado): avatar escogido.
        Salidas:
            Ninguna.
        """
        self.ctx.avatares.seleccionar_predeterminado(self.ctx.id_usuario, avatar.id)
        self.exito(f"Avatar «{avatar.nombre}» seleccionado.")

    def _subir(self) -> None:
        """
        Descripción:
            Acción del botón 'Cargar imagen...': abre el explorador de archivos y, si el
            usuario eligió una imagen, la sube como avatar personalizado y confirma. Si el
            usuario cancela no ocurre nada; si el archivo no es válido, el servicio lanza un
            ErrorApp que se muestra como mensaje en pantalla.
        Entradas:
            Ninguna.
        Salidas:
            Ninguna.
        """
        ruta = elegir_archivo_imagen()
        if ruta:
            self.ctx.avatares.subir_personalizado(self.ctx.id_usuario, ruta)
            self.exito("Imagen cargada como avatar.")

    def dibujar(self, superficie) -> None:
        """
        Descripción:
            Dibuja la pantalla: el encabezado, las miniaturas del catálogo (resaltando con un
            marco azul la que está elegida), una vista grande del avatar actual con su marco
            (azul si es personalizado) y su etiqueta 'Avatar actual', y por último los
            botones.
        Entradas:
            superficie (pygame.Surface): superficie donde se dibuja.
        Salidas:
            Ninguna.
        """
        self.dibujar_encabezado(superficie, "Selecciona tu avatar")
        actual = self.ctx.avatares.obtener_eleccion(self.ctx.id_usuario)
        for i, av in enumerate(self.ctx.avatares.listar_predeterminados()):
            r = self._rect_miniatura(i)
            elegido = actual.tipo == "predeterminado" and actual.valor == av.id
            pygame.draw.rect(superficie, ACENTO if elegido else PANEL, r.inflate(10, 10), border_radius=8)
            superficie.blit(self.ctx.avatares.dibujar_predeterminado(av, self.MINIATURA), r)
        pygame.draw.rect(superficie, ACENTO if actual.tipo == "personalizado" else PANEL, (560, 280, 148, 148),
                         border_radius=8)
        superficie.blit(self.ctx.avatares.obtener_superficie(self.ctx.id_usuario, 128), (570, 290))
        self.texto(superficie, "Avatar actual", (570, 435))
        self.dibujar_botones(superficie)


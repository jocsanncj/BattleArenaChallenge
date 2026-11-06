"""Adaptador de escenas de cuenta al flujo de juego online."""

import pygame

from frontend.auth.service import id_usuario_actual
from frontend.repositories import RepositorioAvataresServidor, RepositorioPartidaServidor
from frontend.results import launch_victory_window
from frontend.ui.arena import PantallaArena
from frontend.ui.avatar import PantallaAvatar
from frontend.ui.base import Contexto
from frontend.ui.configuracion import PantallaConfiguracion
from frontend.ui.sala import PantallaSala
from shared.domain import ErrorApp, ServicioAvatar, ServicioPartida
from .base import ERROR, BaseScene
from .menu import MainMenuScene


class JuegoOnlineScene(BaseScene):
    """Adaptador de escenas para avatar, sala, configuración y arena online."""

    def __init__(self, font, nombre_usuario):
        super().__init__()
        self.font = font
        self.nombre_usuario = nombre_usuario
        self.id_usuario = id_usuario_actual()
        self.ctx = Contexto(ServicioAvatar(RepositorioAvataresServidor()),
                            ServicioPartida(RepositorioPartidaServidor()),
                            self.id_usuario, self.nombre_usuario)
        self._tipos = {"avatar": PantallaAvatar, "sala": PantallaSala,
                       "configuracion": PantallaConfiguracion, "arena": PantallaArena}
        self.page = "avatar"
        self.screen = PantallaAvatar(self.ctx)
        self.status = ""
        self._victory_match_id = None

    def _cambiar(self, page):
        try:
            self.page = page
            if page == "avatar": self.screen = PantallaAvatar(self.ctx)
            elif page == "sala": self.screen = PantallaSala(self.ctx)
            elif page == "configuracion": self.screen = PantallaConfiguracion(self.ctx)
            elif page == "arena": self.screen = PantallaArena(self.ctx)
            elif page == "menu":
                menu = MainMenuScene(self.font)
                menu.user_name = self.nombre_usuario
                menu.page = "menu"
                menu.status = self.status
                menu._configure_page()
                self.window.set_scene(menu)
        except (ErrorApp, OSError, RuntimeError, ValueError) as error:
            self.status = str(error)
            self.page, self.screen = "sala", PantallaSala(self.ctx)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.page == "arena":
                try:
                    self.ctx.partida.salir(self.id_usuario)
                except (ErrorApp, OSError, RuntimeError, ValueError) as error:
                    self.status = str(error)
                self._cambiar("menu")
            elif self.page == "sala":
                try:
                    self.ctx.partida.salir(self.id_usuario)
                except (ErrorApp, OSError, RuntimeError, ValueError) as error:
                    self.status = str(error)
                self._cambiar("menu")
            elif self.page == "configuracion": self._cambiar("sala")
            else: self._cambiar("menu")
            return
        if self.page == "arena":
            self.screen.procesar_evento(event)
            if event.type != pygame.MOUSEBUTTONDOWN:
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for boton in self.screen.botones():
                if boton.rectangulo.collidepoint(event.pos):
                    try:
                        resultado = boton.accion()
                        if resultado == "siguiente": self._cambiar("sala")
                        elif resultado == "configuracion": self._cambiar("configuracion")
                        elif resultado == "volver":
                            if self.page == "configuracion": self._cambiar("sala")
                            else:
                                try:
                                    self.ctx.partida.salir(self.id_usuario)
                                except (ErrorApp, OSError, RuntimeError, ValueError) as error:
                                    self.status = str(error)
                                self._cambiar("menu")
                        elif resultado == "arena": self._cambiar("arena")
                    except (ErrorApp, OSError, RuntimeError, ValueError) as error:
                        self.screen.mensaje = str(error)
                    break
    def update(self, mouse_pos):
        try:
            resultado = self.screen.actualizar()
            if resultado == "arena": self._cambiar("arena")
            elif resultado == "volver": self._cambiar("sala")
            if self.page == "arena":
                juego = self.screen._partida.estado_juego
                if juego and juego.get("status") == "finished":
                    match_id = juego.get("match_id")
                    if match_id and match_id != self._victory_match_id:
                        launch_victory_window(juego)
                        self._victory_match_id = match_id
        except (ErrorApp, OSError, RuntimeError, ValueError) as error:
            self.screen.mensaje = str(error)

    def draw(self, surface):
        # CAMBIO ONLINE: conserva el tamaño de la ventana y el dibujo de cada pantalla.
        try:
            if self.page == "arena":
                superficie = surface
                superficie.fill((25, 28, 40))
                self.screen.dibujar(superficie)
            else:
                self.screen.dibujar(surface)
        except (OSError, RuntimeError, ValueError) as error:
            # Un fallo de red se informa en la escena en lugar de cerrar Pygame.
            self.status = str(error)
            surface.fill((25, 28, 40))
        if self.status:
            texto = self.font.render(self.status, True, ERROR)
            surface.blit(texto, (20, surface.get_height() - 30))

    def on_close(self):
        """Libera la plaza y pausa la partida cuando se cierra la ventana."""
        if self.page in {"sala", "configuracion", "arena"}:
            self.ctx.partida.salir(self.id_usuario)

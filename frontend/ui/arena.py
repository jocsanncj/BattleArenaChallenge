"""Renderizado de la arena, entrada local y estado visual de la partida."""

from typing import List, Optional

import pygame

from frontend import actions
from shared.domain import Casilla, ErrorApp
from shared.game.arena import draw_players
from shared.game.scores import draw_scores
from .base import (ACENTO, COLOR_CUADRICULA, COLOR_LIMITE, COLOR_MURO, COLOR_OBSTACULO, COLOR_PISO, COLOR_REACTOR, COLORES_INICIO, ERROR, FONDO, PANEL, Boton, Contexto, Pantalla, describir_configuracion, reproducir_musica)

class PantallaArena(Pantalla):
    """
    Descripción:
        Pantalla de la arena de juego. Se abre en una ventana completamente nueva, del
        tamaño exacto del mapa más un panel lateral. Dibuja el mapa, a los jugadores en
        sus puntos de inicio con su avatar, el estado de la partida, el temporizador y la
        configuración, y reproduce música de fondo mientras está abierta.
        Cada cliente puede seleccionar teclado o gamepad para mover a su jugador.
    Atributos:
        TAM_CASILLA (int): lado en píxeles de cada casilla (32).
        ANCHO_PANEL (int): ancho en píxeles del panel lateral (250).
        INTERVALO_MS (int): cada cuántos ms se vuelve a leer la partida (500).
        tecla_escape (str): 'volver'; ESC sale de la arena.
        mapa (MapaArena): escenario que se dibuja.
        fuente_grande (pygame.font.Font): fuente de tamaño 48 para el temporizador.
        control_entrada (actions.ControlEntrada): dispositivo de entrada local seleccionado.
        _partida (Partida) y _ultimo (int): última partida leída y momento de la lectura.
        _musica (Optional[pygame.mixer.Sound]): música en reproducción, o None.
    """

    TAM_CASILLA, ANCHO_PANEL, INTERVALO_MS = 32, 250, 500
    tecla_escape = "volver"

    def __init__(self, ctx: Contexto):
        """
        Descripción:
            Guarda el mapa de la partida, crea la fuente grande, carga la partida actual y
            deja la música sin iniciar (se inicia al abrir la ventana).
        Entradas:
            ctx (Contexto): contexto de la aplicación.
        Salidas:
            Ninguna.
        """
        super().__init__(ctx)
        self.mapa = ctx.partida.arena
        self.fuente_grande = pygame.font.SysFont(None, 48)
        self._partida, self._ultimo = ctx.partida.obtener_partida(), pygame.time.get_ticks()
        self._musica: Optional[pygame.mixer.Sound] = None
        actions.iniciar()
        self.control_entrada = actions.ControlEntrada()
        self._ultimo_movimiento = -self.INTERVALO_MOVIMIENTO_MS

    INTERVALO_MOVIMIENTO_MS = 150

    def _alternar_control(self) -> None:
        if self.control_entrada.modo == actions.MODO_TECLADO:
            self.control_entrada.seleccionar(actions.MODO_GAMEPAD)
            self.exito(f"Gamepad seleccionado: {self.control_entrada.nombre_gamepad}")
        else:
            self.control_entrada.seleccionar(actions.MODO_TECLADO)
            self.exito("Teclado seleccionado.")

    def botones(self) -> List[Boton]:
        if self._partida.estado_juego and self._partida.estado_juego.get("status") == "finished":
            return []
        etiqueta = ("Usar teclado" if self.control_entrada.modo == actions.MODO_GAMEPAD
                    else "Usar gamepad")
        x = self.mapa.columnas * self.TAM_CASILLA + 14
        y = self.mapa.filas * self.TAM_CASILLA - 102
        return [
            Boton(
                pygame.Rect(x, y, self.ANCHO_PANEL - 28, 34),
                etiqueta,
                self._alternar_control,
            )
        ]

    def procesar_evento(self, evento: pygame.event.Event) -> None:
        self.control_entrada.procesar_evento(evento)
        if self.control_entrada.aviso:
            self.mensaje, self.color_mensaje = self.control_entrada.aviso, ERROR
            self.control_entrada.aviso = ""

    def _procesar_movimiento(self) -> None:
        juego = self._partida.estado_juego
        if not juego or juego.get("status") not in {"running", "overtime"}:
            return
        direccion = self.control_entrada.direccion_actual()
        ahora = pygame.time.get_ticks()
        if direccion is None or ahora - self._ultimo_movimiento < self.INTERVALO_MOVIMIENTO_MS:
            return
        self._ultimo_movimiento = ahora
        try:
            self.ctx.partida.mover(direccion)
        except (ErrorApp, OSError, RuntimeError, ValueError) as error:
            self.mensaje, self.color_mensaje = str(error), ERROR

    def ejecutar(self, superficie=None) -> str:
        """
        Descripción:
            Sobrescribe el ciclo base para abrir una ventana nueva para la arena.

            Pasos:
            1. Cierra la ventana anterior y vuelve a iniciar el módulo de video, de modo que
               la arena aparezca en una ventana completamente nueva.
            2. Crea la ventana con el tamaño del mapa (columnas y filas por TAM_CASILLA) más
               el ancho del panel lateral, y le pone título.
            3. Inicia la música.
            4. Ejecuta el ciclo común de Pantalla y, pase lo que pase, detiene la música al
               terminar (bloque finally).
        Entradas:
            superficie (pygame.Surface): se ignora; la arena crea su propia ventana.
        Salidas:
            str: texto con el que terminó la pantalla ('salir' o 'volver').
        """
        pygame.display.quit()
        pygame.display.init()
        ventana = pygame.display.set_mode((self.mapa.columnas * self.TAM_CASILLA + self.ANCHO_PANEL,
                                           self.mapa.filas * self.TAM_CASILLA))
        pygame.display.set_caption("Battle Arena - Sala de juego")
        self._musica = reproducir_musica()
        try:
            return super().ejecutar(ventana)
        finally:
            if self._musica:
                self._musica.stop()

    def actualizar(self) -> Optional[str]:
        """
        Descripción:
            Cada 500 ms vuelve a leer la partida desde el repositorio para reflejar cambios
            (por ejemplo, jugadores que entran o salen). Nunca cierra la pantalla por sí sola.
        Entradas:
            Ninguna.
        Salidas:
            None: la arena solo se cierra con ESC o al cerrar la ventana.
        """
        ahora = pygame.time.get_ticks()
        self._procesar_movimiento()
        if ahora - self._ultimo >= self.INTERVALO_MS:
            self._ultimo, self._partida = ahora, self.ctx.partida.obtener_partida()
        return None

    def _dibujar_mapa(self, superficie: pygame.Surface) -> None:
        """
        Descripción:
            Dibuja el escenario casilla por casilla y sus elementos especiales.

            Pasos:
            1. Recorre la cuadrícula: muros en gris azulado, obstáculos en café con una X,
               reactor en azul verdoso, y piso o inicio en oscuro con una cuadrícula fina.
            2. Marca cada punto de inicio con un anillo del color de su jugador.
            3. Dibuja el reactor en el centro como dos círculos concéntricos.
            4. Dibuja un borde amarillo que señala el límite de la zona jugable (el interior
               del muro).
        Entradas:
            superficie (pygame.Surface): superficie donde se dibuja.
        Salidas:
            Ninguna.
        """
        T, m = self.TAM_CASILLA, self.mapa
        for f in range(m.filas):
            for c in range(m.columnas):
                casilla, rect = m.casilla_en(c, f), pygame.Rect(c * T, f * T, T, T)
                if casilla is Casilla.MURO:
                    pygame.draw.rect(superficie, COLOR_MURO, rect)
                elif casilla is Casilla.OBSTACULO:
                    pygame.draw.rect(superficie, COLOR_OBSTACULO, rect)
                    pygame.draw.line(superficie, (70, 50, 40), rect.topleft, rect.bottomright, 3)
                    pygame.draw.line(superficie, (70, 50, 40), rect.topright, rect.bottomleft, 3)
                elif casilla is Casilla.REACTOR:
                    pygame.draw.rect(superficie, COLOR_REACTOR, rect)
                else:
                    pygame.draw.rect(superficie, COLOR_PISO, rect)
                    pygame.draw.rect(superficie, COLOR_CUADRICULA, rect, 1)
        for i, (c, f) in enumerate(m.puntos_inicio()):
            pygame.draw.circle(superficie, COLORES_INICIO[i % 4], (c * T + T // 2, f * T + T // 2), T // 2 - 2, 2)
        cx, cy = m.centro_reactor()
        centro = (int((cx + 0.5) * T), int((cy + 0.5) * T))
        pygame.draw.circle(superficie, (60, 220, 230), centro, int(T * 1.4))
        pygame.draw.circle(superficie, (230, 255, 255), centro, int(T * 0.6))
        pygame.draw.rect(superficie, COLOR_LIMITE, pygame.Rect(T, T, (m.columnas - 2) * T, (m.filas - 2) * T), 3)

    def _temporizador(self):
        """
        Descripción:
            Calcula qué muestra el temporizador. Siempre corre, sin importar el modo de fin:
            - Si la partida termina por tiempo, muestra el tiempo restante (la duración
              menos lo transcurrido, sin bajar de cero) con la etiqueta 'Tiempo restante'.
            - Si termina por puntos, muestra el tiempo transcurrido con la etiqueta 'Tiempo
              transcurrido'.

            El tiempo se da en formato MM:SS.
        Entradas:
            Ninguna.
        Salidas:
            tuple: (etiqueta, tiempo en formato 'MM:SS').
        """
        cfg, transcurrido = self._partida.configuracion, self.ctx.partida.segundos_transcurridos(self._partida)
        juego = self._partida.estado_juego
        if juego:
            if cfg.modo_fin == "tiempo":
                segundos = juego.get("remaining_seconds")
                etiqueta = "Tiempo restante"
            else:
                segundos = juego.get("elapsed_seconds", 0)
                etiqueta = "Tiempo transcurrido"
            if segundos is not None:
                return etiqueta, f"{int(max(0, segundos)) // 60:02d}:{int(max(0, segundos)) % 60:02d}"
        if cfg.modo_fin == "tiempo":
            segundos, etiqueta = max(0, cfg.minutos_fin * 60 - transcurrido), "Tiempo restante"
        else:
            segundos, etiqueta = transcurrido, "Tiempo transcurrido"
        return etiqueta, f"{int(segundos) // 60:02d}:{int(segundos) % 60:02d}"

    def dibujar(self, superficie) -> None:
        """
        Descripción:
            Dibuja el cuadro completo de la arena.

            Pasos:
            1. Pinta el fondo y el mapa.
            2. Dibuja a cada jugador con su avatar sobre su punto de inicio; el jugador de
               este programa lleva además un aro azul.
            3. Dibuja el panel lateral con la insignia del jugador, el estado ('Partida en
               curso' o 'Esperando'), el temporizador, la configuración, la lista de jugadores
               (marcando '(tú)') y la indicación 'ESC: salir'.
        Entradas:
            superficie (pygame.Surface): ventana de la arena.
        Salidas:
            Ninguna.
        """
        T, m, p = self.TAM_CASILLA, self.mapa, self._partida
        superficie.fill(FONDO)
        self._dibujar_mapa(superficie)
        juego = p.estado_juego
        if juego:
            jugadores_dibujo = []
            imagenes_avatar = {}
            posicion_local = None
            for jugador in juego.get("players", []):
                user_id = jugador["user_id"]
                c, f = int(jugador["x"]), int(jugador["y"])
                jugadores_dibujo.append(dict(
                    jugador,
                    x=c * T + T // 2,
                    y=f * T + T // 2,
                ))
                imagenes_avatar[jugador["avatar_id"]] = self.ctx.avatares.obtener_superficie(user_id, T - 6)
                if user_id == self.ctx.id_usuario:
                    posicion_local = (c * T + T // 2, f * T + T // 2)
            draw_players(
                superficie,
                dict(juego, players=jugadores_dibujo),
                imagenes_avatar,
                size=T - 6,
            )
            if posicion_local:
                pygame.draw.circle(superficie, ACENTO, posicion_local, T // 2, 2)
        else:
            for j in p.jugadores:
                c, f = m.puntos_inicio()[j.indice_inicio]
                superficie.blit(self.ctx.avatares.obtener_superficie(j.id_usuario, T - 6),
                                (c * T + 3, f * T + 3))
                if j.id_usuario == self.ctx.id_usuario:
                    pygame.draw.circle(superficie, ACENTO,
                                       (c * T + T // 2, f * T + T // 2), T // 2, 2)
        x0 = m.columnas * T
        pygame.draw.rect(superficie, PANEL, (x0, 0, self.ANCHO_PANEL, superficie.get_height()))
        x = x0 + 14
        self.insignia.dibujar(superficie, (x, 12))
        mensaje_estado = (juego.get("message", "Partida en curso.") if juego else
                          "Partida en curso" if p.estado == "jugando" else "Esperando")
        self.texto(superficie, mensaje_estado, (x, 74))
        etiqueta, valor = self._temporizador()
        self.texto(superficie, etiqueta, (x, 104))
        self.texto(superficie, valor, (x, 124), self.fuente_grande)
        for i, linea in enumerate(describir_configuracion(p.configuracion)):
            self.texto(superficie, linea, (x, 184 + i * 22))
        self.texto(superficie, "Jugadores", (x, 244), self.fuente)
        if juego:
            for i, jugador in enumerate(juego.get("players", [])):
                user_id = jugador["user_id"]
                superficie.blit(self.ctx.avatares.obtener_superficie(user_id, 28), (x, 274 + i * 44))
            draw_scores(superficie, juego, position=(x + 36, 281))
            if juego.get("status") == "finished":
                self.texto(superficie, "ESC: volver al menú", (x, superficie.get_height() - 24))
            else:
                indicacion = ("Gamepad: stick / cruceta" if
                              self.control_entrada.modo == actions.MODO_GAMEPAD else
                              "WASD / flechas: mover")
                self.texto(superficie, indicacion, (x, superficie.get_height() - 44))
                self.texto(superficie, "ESC: salir", (x, superficie.get_height() - 24))
        else:
            for i, j in enumerate(p.jugadores):
                superficie.blit(self.ctx.avatares.obtener_superficie(j.id_usuario, 28), (x, 274 + i * 34))
                self.texto(superficie, j.nombre_usuario + (" (tú)" if j.id_usuario == self.ctx.id_usuario else ""),
                           (x + 36, 281 + i * 34))
            self.texto(superficie, "ESC: salir", (x, superficie.get_height() - 24))
        if self.mensaje:
            mensaje = self.mensaje
            while self.fuente_chica.size(mensaje)[0] > self.ANCHO_PANEL - 28:
                mensaje = mensaje[:-4] + "..."
            self.texto(superficie, mensaje, (x, superficie.get_height() - 130),
                       self.fuente_chica, self.color_mensaje)
        self.dibujar_botones(superficie)

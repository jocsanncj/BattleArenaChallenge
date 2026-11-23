"""Renderizado de la arena, entrada local y estado visual de la partida."""

import math
from typing import List, Optional

import pygame

from frontend import actions, visual as v
from frontend.audio import musica, sonido_extraccion
from frontend import personajes
from frontend.escenarios import MAPAS, indice_mapa
from shared.domain import ErrorApp
from shared.game.arena import draw_players
from .base import ACENTO, COLOR_LIMITE, ERROR, FONDO, Boton, Contexto, Pantalla

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
        INTERVALO_MS (int): cada cuántos ms se vuelve a leer la partida (300).
        tecla_escape (str): 'volver'; ESC sale de la arena.
        mapa (MapaArena): escenario que se dibuja.
        fuente_grande (pygame.font.Font): fuente de tamaño 48 para el temporizador.
        control_entrada (actions.ControlEntrada): dispositivo de entrada local seleccionado.
        _partida (Partida) y _ultimo (int): última partida leída y momento de la lectura.
        _musica (Optional[pygame.mixer.Sound]): música en reproducción, o None.
    """
    TAM_CASILLA, ANCHO_PANEL, INTERVALO_MS = 36, 244, 300
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
        self.mapa = MAPAS[indice_mapa(self._partida.configuracion)]
        self._ultima_extraccion = ((self._partida.estado_juego or {}).get("reactor") or {}).get("ultima_extraccion")
        self._recargando = (self._partida.estado_juego or {}).get("reactor", {}).get("status") == "recargando"
        self._aviso_hasta = 0
        self._imagenes = {}

        actions.iniciar()
        self.control_entrada = actions.ControlEntrada()
        self._ultimo_movimiento = -self.INTERVALO_MOVIMIENTO_MS
        self._ultima_accion_id = None
        self._interaccion_id = None
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
        y = self.mapa.filas * self.TAM_CASILLA - 80
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
    def _procesar_interaccion(self) -> None:
        event_id = self.control_entrada.accion_id
        if event_id is not None and event_id != self._ultima_accion_id:
            self._ultima_accion_id = event_id
            try:
                self.ctx.partida.interactuar_reactor("start", event_id)
                self._interaccion_id = event_id
            except (ErrorApp, OSError, RuntimeError, ValueError) as error:
                self.mensaje, self.color_mensaje = str(error), ERROR
        elif event_id is None and self._interaccion_id is not None:
            interaccion_id = self._interaccion_id
            self._interaccion_id = None
            try:
                self.ctx.partida.interactuar_reactor("stop", interaccion_id)
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
                                           self.mapa.filas * self.TAM_CASILLA + 60))
        pygame.display.set_caption("Battle Arena - Sala de juego")
        musica.iniciar()
        try:
            return super().ejecutar(ventana)
        finally:
            musica.detener()
    def actualizar(self) -> Optional[str]:
        """
        Descripción:
            Cada 300 ms vuelve a leer la partida desde el servidor para reflejar cambios
            (por ejemplo, jugadores que entran o salen). Nunca cierra la pantalla por sí sola.
        Entradas:
            Ninguna.
        Salidas:
            None: la arena solo se cierra con ESC o al cerrar la ventana.
        """
        ahora = pygame.time.get_ticks()
        self._procesar_movimiento()
        self._procesar_interaccion()
        if ahora - self._ultimo >= self.INTERVALO_MS:
            self._ultimo, self._partida = ahora, self.ctx.partida.obtener_partida()
            self._escuchar_extraccion(self._partida.estado_juego or {})
        return None
    def _escuchar_extraccion(self, juego):
        reactor = juego.get("reactor") or {}
        marca = reactor.get("ultima_extraccion")
        recargando = reactor.get("status") == "recargando"
        if "ultima_extraccion" in reactor:
            confirmada = marca is not None and marca != self._ultima_extraccion
        else:
            # Develop entra en recarga únicamente después de otorgar una extracción.
            confirmada = recargando and not self._recargando
        self._ultima_extraccion = marca
        self._recargando = recargando
        if confirmada:
            self._aviso_hasta = pygame.time.get_ticks() + 1800
            sonido_extraccion()

    def _avatar(self, user_id, tam, tipo="retratos"):
        clave = (user_id, tam, tipo)
        if clave not in self._imagenes:
            self._imagenes[clave] = personajes.de_usuario(self.ctx.avatares, user_id, tam, tipo)
        return self._imagenes[clave]

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
        juego = self._partida.estado_juego or {}
        reactor = juego.get("reactor", {})
        estado_reactor = reactor.get("status", "disponible")
        color_reactor = {
            "disponible": (60, 220, 230),
            "ocupado": (255, 170, 60),
            "recargando": (120, 130, 150),
            "sobrecargado": (230, 65, 65),
        }.get(estado_reactor, (60, 220, 230))
        segundos = juego.get("elapsed_seconds", 0)
        tema = self._tema(segundos)
        superficie.blit(v.tablero(m, tema, T), (0, 0))

        obstaculos = juego.get("obstaculos", {})
        for puerta in obstaculos.get("puertas", []):
            rect = pygame.Rect(puerta["x"] * T + 3, puerta["y"] * T + 3, T - 6, T - 6)
            color = (55, 205, 115) if puerta.get("abierta") else (220, 65, 65)
            pygame.draw.rect(superficie, color, rect, border_radius=5)
            pygame.draw.rect(superficie, (245, 245, 245), rect, 2, border_radius=5)
            marca = pygame.font.Font(None, 20).render("P", True, (255, 255, 255))
            superficie.blit(marca, marca.get_rect(center=rect.center))
        for trampa in obstaculos.get("trampas", []):
            if trampa.get("activa", True):
                sprite = v.sprite_trampa(trampa["tipo"], T - 2)
                superficie.blit(sprite, (trampa["x"] * T + 1, trampa["y"] * T + 1))

        # US-22.1: energía adicional enviada por el servidor.
        energia = juego.get("energia_adicional")
        if energia:
            centro_energia = (
                int(energia["x"]) * T + T // 2,
                int(energia["y"]) * T + T // 2,
            )
            pygame.draw.circle(superficie, (255, 220, 70), centro_energia, T // 2 - 2)
            pygame.draw.circle(superficie, (255, 255, 220), centro_energia, T // 2 - 2, 2)
            pygame.draw.line(
                superficie, (110, 75, 15),
                (centro_energia[0] - 6, centro_energia[1]),
                (centro_energia[0] + 6, centro_energia[1]), 3,
            )
            pygame.draw.line(
                superficie, (110, 75, 15),
                (centro_energia[0], centro_energia[1] - 6),
                (centro_energia[0], centro_energia[1] + 6), 3,
            )

        # US-21: guardianes con silueta propia, ojos y dirección hacia su objetivo.
        # La posición procede siempre del servidor; no se simula persecución en el cliente.
        for guardian in juego.get("guardianes", []):
            gx, gy = int(guardian["x"]), int(guardian["y"])
            sprite = v.guardian(guardian["tipo"], T-3)
            superficie.blit(sprite, (gx*T+1, gy*T))

        cx, cy = m.centro_reactor()
        centro = (int((cx + 0.5) * T), int((cy + 0.5) * T))
        v.reactor(superficie, m, tema, T, segundos)
        pygame.draw.circle(superficie, color_reactor, centro, int(T * 1.4), 3)
        etiquetas_reactor = {
            "disponible": "REACTOR DISPONIBLE",
            "ocupado": "REACTOR OCUPADO",
            "recargando": f"RECARGA {reactor.get('remaining_seconds', 0):.1f} s",
            "sobrecargado": "REACTOR SOBRECARGADO",
        }
        etiqueta_reactor = etiquetas_reactor.get(estado_reactor, "REACTOR DISPONIBLE")
        fuente_reactor = pygame.font.Font(None, 20)
        texto_reactor = fuente_reactor.render(etiqueta_reactor, True, (255, 255, 255))
        superficie.blit(
            texto_reactor,
            texto_reactor.get_rect(
                center=(centro[0], centro[1] + int(T * 1.5) + 10)
            ),
        )
        pygame.draw.rect(superficie, COLOR_LIMITE, pygame.Rect(T, T, (m.columnas - 2) * T, (m.filas - 2) * T), 3)
    def _tema(self, segundos):
        cfg = self._partida.configuracion
        indice = indice_mapa(cfg)
        return v.fase(indice, segundos) if getattr(cfg, "rotacion", False) else indice

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
                etiqueta = ("Prórroga · tiempo restante" if juego.get("status") == "overtime"
                            else "Tiempo restante")
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
    def _dibujar_indicadores_eventos(self, superficie: pygame.Surface, juego: dict) -> None:
        """Muestra sobre la arena los eventos que están afectando la partida."""
        eventos = juego.get("eventos", []) or []
        proximo_evento = juego.get("proximo_evento")


        nombres = {
            "guardianes_adicionales": "5 GUARDIANES ADICIONALES",
            "guardianes_quitan_puntos": "LOS GUARDIANES QUITAN PUNTOS",
            "doble_trampas": "DOBLE DE TRAMPAS",
            "sobrecarga_1": "SOBRECARGA DEL REACTOR",
            "sobrecarga_2": "SOBRECARGA DEL REACTOR",
            "energia_1": "ENERGIA ADICIONAL DISPONIBLE",
            "energia_2": "ENERGIA ADICIONAL DISPONIBLE",
            "energia_3": "ENERGIA ADICIONAL DISPONIBLE",
            # Las rondas posteriores usan ids nuevos; el servidor envía también el tipo.
            "energia": "ENERGIA ADICIONAL DISPONIBLE",
            "sobrecarga": "SOBRECARGA DEL REACTOR",
        }
        ancho_mapa = self.mapa.columnas * self.TAM_CASILLA
        y = self.mapa.filas*self.TAM_CASILLA+5
        if eventos:
            ancho = ancho_mapa // len(eventos)
            for i, evento in enumerate(eventos):
                titulo = nombres.get(evento.get("tipo"), evento["mensaje"])
                v.rotulo(superficie, f"Activo · {titulo}", (i*ancho+8,y), 13, v.MINT, True, ancho-16)
        else:
            v.rotulo(superficie, "Sin eventos activos", (12,y), 14, v.MUTED)
        if proximo_evento:
            segundos = proximo_evento["segundos_restantes"]
            if segundos <= 5:
                titulo = nombres.get(proximo_evento.get("tipo"), "Evento")
                pygame.draw.rect(superficie,(98,57,27),(8,y+22,ancho_mapa-16,27),border_radius=5)
                v.rotulo(superficie, f"ALERTA · {titulo} en {math.ceil(segundos)} s", (17,y+25),14,(255,221,139),True)
            else:
                v.rotulo(superficie, f"Próximo evento en {math.ceil(segundos)} s", (12,y+26),13,v.MUTED)

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
            posiciones_estados = []
            posicion_local = None
            for jugador in juego.get("players", []):
                user_id = jugador["user_id"]
                c, f = int(jugador["x"]), int(jugador["y"])
                jugadores_dibujo.append(dict(
                    jugador,
                    x=c * T + T // 2,
                    y=f * T + T // 2,
                ))
                imagenes_avatar[jugador["avatar_id"]] = self._avatar(user_id, T - 2, "personajes")
                if jugador.get("estado_temporal") in {"congelado", "inmovilizado"}:
                    posiciones_estados.append((
                        (c * T + T // 2, f * T + T // 2),
                        (90, 190, 255) if jugador["estado_temporal"] == "congelado"
                        else (255, 145, 75),
                    ))
                if user_id == self.ctx.id_usuario:
                    posicion_local = (c * T + T // 2, f * T + T // 2)
            draw_players(
                superficie,
                dict(juego, players=jugadores_dibujo),
                imagenes_avatar,
                size=T - 2,
            )
            for centro_estado, color_estado in posiciones_estados:
                pygame.draw.circle(superficie, color_estado, centro_estado, T // 2 - 1, 3)
            if posicion_local:
                pygame.draw.circle(superficie, ACENTO, posicion_local, T // 2, 2)
        else:
            for j in p.jugadores:
                c, f = m.puntos_inicio()[j.indice_inicio]
                superficie.blit(self._avatar(j.id_usuario, T - 2, "personajes"),
                                (c * T + 1, f * T + 1))
                if j.id_usuario == self.ctx.id_usuario:
                    pygame.draw.circle(superficie, ACENTO,
                                       (c * T + T // 2, f * T + T // 2), T // 2, 2)
        if juego:
            self._dibujar_indicadores_eventos(superficie, juego)
        x0 = m.columnas * T
        pygame.draw.rect(superficie, v.PANEL, (x0, 0, self.ANCHO_PANEL, superficie.get_height()))
        x = x0 + 14
        tema = self._tema((juego or {}).get("elapsed_seconds", 0))
        luz = v.PALETAS[tema][-1]
        local = next((j for j in (juego or {}).get("players", [])
                      if j["user_id"] == self.ctx.id_usuario), {})
        superficie.blit(self._avatar(self.ctx.id_usuario, 66), (x, 10))
        v.rotulo(superficie, "TU JUGADOR", (x+75, 14), 11, luz, True)
        v.rotulo(superficie, self.ctx.nombre_usuario, (x+75, 30), 16, v.TEXT, True, 137)
        energia = local.get("energia_extraida")
        dato = f"Energía extraída: {energia}" if energia is not None else f"Puntos: {local.get('score', 0)}"
        v.rotulo(superficie, dato, (x+75, 54), 13, v.TEXT, ancho=140)
        v.rotulo(superficie, v.NOMBRES[tema], (x, 80), 16, luz, True)
        etiqueta, valor = self._temporizador()
        v.rotulo(superficie, etiqueta, (x, 105), 13, v.MUTED)
        v.rotulo(superficie, valor, (x, 122), 27, v.TEXT, True)
        aviso = "Energía extraída" if pygame.time.get_ticks() < self._aviso_hasta else (juego or {}).get("message", "Esperando")
        v.lineas(superficie, aviso, pygame.Rect(x,158,self.ANCHO_PANEL-28,39), luz)
        v.rotulo(superficie, "MARCADOR", (x, 198), 12, v.MUTED, True)
        if juego:
            jugadores = juego.get("players", [])
            for i, jugador in enumerate(jugadores):
                y = 221 + i*34
                es_local = jugador["user_id"] == self.ctx.id_usuario
                superficie.blit(self._avatar(jugador["user_id"], 26), (x, y))
                v.rotulo(superficie, jugador["username"], (x+34, y+3), 14,
                         luz if es_local else v.TEXT, es_local, self.ANCHO_PANEL-106)
                puntos = v.fuente(17, True).render(str(jugador["score"]), True, v.TEXT)
                superficie.blit(puntos, puntos.get_rect(topright=(x0+self.ANCHO_PANEL-14,y)))
            jugador_local = next(
                (j for j in jugadores if j.get("user_id") == self.ctx.id_usuario),
                None,
            )
            if jugador_local and jugador_local.get("estado_temporal") in {"inmovilizado", "congelado"}:
                restante = jugador_local.get("segundos_inmovilizado", 0)
                estado_texto = (
                    "CONGELADO" if jugador_local.get("estado_temporal") == "congelado"
                    else "INMOVILIZADO"
                )
                color_estado = (
                    (120, 205, 255) if estado_texto == "CONGELADO"
                    else (255, 160, 100)
                )
                pygame.draw.rect(superficie, (45, 55, 75), (x, 330, self.ANCHO_PANEL - 28, 48), border_radius=6)
                self.texto(superficie, f"{estado_texto} · {restante:.1f} s",
                           (x + 8, 336), self.fuente, color_estado)
            elif jugador_local and jugador_local.get("inmune"):
                pygame.draw.rect(superficie, (45, 70, 55), (x, 330, self.ANCHO_PANEL - 28, 48), border_radius=6)
                self.texto(superficie,
                           f"INMUNE · {jugador_local.get('segundos_inmunidad', 0):.1f} s",
                           (x + 8, 336), self.fuente, (140, 235, 160))
            if juego.get("status") == "finished":
                self.texto(superficie, "ESC: volver al menú", (x, superficie.get_height() - 24))
            else:
                indicacion = (
                    "Gamepad: stick / cruceta" if self.control_entrada.modo == actions.MODO_GAMEPAD
                    else "WASD / flechas: mover"
                )
                accion_indicacion = (
                    "Botón 0 (X / A): extraer" if self.control_entrada.modo == actions.MODO_GAMEPAD
                    else "E: extraer energía"
                )
                self.texto(superficie, indicacion, (x, superficie.get_height() - 64))
                self.texto(superficie, accion_indicacion, (x, superficie.get_height() - 44))
                self.texto(superficie, "ESC: salir", (x, superficie.get_height() - 24))
        else:
            for i, j in enumerate(p.jugadores):
                superficie.blit(self._avatar(j.id_usuario, 28), (x, 220 + i * 36))
                self.texto(superficie, j.nombre_usuario + (" (tú)" if j.id_usuario == self.ctx.id_usuario else ""),
                           (x + 36, 227 + i * 36))
            self.texto(superficie, "ESC: salir", (x, superficie.get_height() - 24))
        if self.mensaje:
            v.lineas(superficie, self.mensaje, pygame.Rect(x, 385, self.ANCHO_PANEL-28, 64), self.color_mensaje)
        self.dibujar_botones(superficie)

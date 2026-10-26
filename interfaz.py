"""
CAPA DE INTERFAZ: dibuja las pantallas y reacciona a los clics

Este módulo usa pygame para mostrar información y recibir acciones del usuario.
No contiene reglas del juego: cada vez que algo importa (elegir avatar, iniciar
la partida, guardar la configuración) le pide el trabajo a la capa de lógica y
muestra el resultado o el error que esta le devuelva.

Pantallas (todas heredan de Pantalla):
    PantallaAvatar         ->  elegir el avatar (US-06).
    PantallaSala           ->  sala de espera e inicio de partida (US-09).
    PantallaConfiguracion  ->  configuración de la partida (US-08).
    PantallaArena          ->  arena en una ventana nueva, con temporizador y
                               música (US-07 y US-09).

Para agregar una pantalla nueva basta con heredar de Pantalla y definir los
métodos botones() y dibujar().

Estructura del archivo:
    1. Librerías
    2. Constantes de color
    3. Contexto y componentes compartidos
    4. Audio y explorador de archivos
    5. Base de las pantallas (Boton y Pantalla)
    6. Pantalla de avatar
    7. Pantalla de sala de espera
    8. Pantalla de configuración
    9. Pantalla de la arena
"""


# 1. LIBRERÍAS

# Librerías estándar de Python (vienen incluidas, no hay que instalarlas)

# io: BytesIO es un archivo en memoria donde se guarda la melodía generada, sin crear
# archivos en el disco.
import io

# math: seno (math.sin) y pi para calcular las ondas de sonido de la melodía.
import math

# struct: empaqueta los números de las muestras de audio en bytes de 16 bits.
import struct

# wave: escribe los bytes de audio con el formato de archivo WAV, que pygame sabe reproducir.
import wave

# dataclasses (dataclass, replace): dataclass crea Contexto y Boton sin código repetitivo;
# replace hace una copia de la configuración para editarla sin alterar la guardada.
from dataclasses import dataclass, replace

# typing (Callable, List, Optional): anotaciones de tipo que documentan qué recibe y
# devuelve cada función (Callable = una función; Optional = puede ser None).
from typing import Callable, List, Optional

# Librería externa (se instala con: pip install pygame)

# pygame: es la base de toda la interfaz: ventana, dibujo, fuentes, eventos de ratón y
# teclado, reloj de cuadros por segundo y el mezclador de audio de la música.
import pygame

# Módulos propios del proyecto

import acciones

# datos: ConfiguracionPartida, solo para indicar el tipo que describe describir_configuracion.
from datos import ConfiguracionPartida

# logica: Casilla (para saber cómo dibujar cada casilla), ErrorApp (para capturar y mostrar
# los errores), ServicioAvatar y ServicioPartida (servicios que usan las pantallas).
#
# Nota: tkinter (explorador de archivos) se importa dentro de elegir_archivo_imagen,
# porque solo se necesita al cargar un avatar propio.
from logica import Casilla, ErrorApp, ServicioAvatar, ServicioPartida
from us10 import draw_players
from us15 import draw_scores


# 2. CONSTANTES DE COLOR

# Colores generales de la interfaz (formato RGB): fondo, paneles y texto
FONDO, PANEL, TEXTO = (25, 28, 40), (45, 50, 70), (235, 235, 245)

# Colores de acento, mensajes de error, mensajes de éxito y botones secundarios
ACENTO, ERROR, EXITO, GRIS = (90, 160, 255), (230, 90, 90), (90, 200, 120), (150, 155, 180)

# Colores del mapa de la arena: piso, líneas de la cuadrícula y muros
COLOR_PISO, COLOR_CUADRICULA, COLOR_MURO = (34, 38, 54), (48, 53, 74), (95, 100, 130)

# Colores del mapa de la arena: obstáculos, reactor y borde de la zona jugable
COLOR_OBSTACULO, COLOR_REACTOR, COLOR_LIMITE = (125, 90, 70), (30, 110, 120), (255, 220, 80)

# Colores de los anillos de los puntos de inicio, uno por cada jugador posible
COLORES_INICIO = [(230, 90, 90), (90, 160, 255), (90, 200, 120), (230, 190, 60)]


# 3. CONTEXTO Y COMPONENTES COMPARTIDOS

@dataclass
class Contexto:
    """
    Descripción:
        Paquete con todo lo que necesita cualquier pantalla: los servicios de la lógica y
        los datos del jugador que está usando este programa. Se crea una sola vez en
        principal.py y se entrega a cada pantalla, así las pantallas no crean sus propios
        servicios.
    Atributos:
        avatares (ServicioAvatar): servicio de avatares.
        partida (ServicioPartida): servicio de la partida.
        id_usuario (int): identificador del jugador de este programa.
        nombre_usuario (str): nombre del jugador de este programa.
    """

    avatares: ServicioAvatar
    partida: ServicioPartida
    id_usuario: int
    nombre_usuario: str


class InsigniaAvatar:
    """
    Descripción:
        Componente que dibuja el avatar del jugador junto a su nombre. Se muestra en
        todas las pantallas para que el jugador siempre vea quién es.
    Atributos:
        _ctx (Contexto): contexto con el servicio de avatares y los datos del jugador.
        _fuente (pygame.font.Font): fuente de tamaño 22 con la que se escribe el nombre.
    """

    def __init__(self, ctx: Contexto):
        """
        Descripción:
            Guarda el contexto y crea la fuente del nombre. Debe crearse después de
            pygame.init(), porque las fuentes necesitan que pygame esté iniciado.
        Entradas:
            ctx (Contexto): contexto de la aplicación.
        Salidas:
            Ninguna.
        """
        self._ctx, self._fuente = ctx, pygame.font.SysFont(None, 22)

    def dibujar(self, superficie: pygame.Surface, esquina=(10, 10), tam: int = 48) -> None:
        """
        Descripción:
            Dibuja en la superficie el avatar actual del jugador (se vuelve a pedir a la
            lógica en cada dibujo, así un cambio de avatar se ve de inmediato) y a su derecha
            el nombre, centrado verticalmente respecto a la imagen.
        Entradas:
            superficie (pygame.Surface): superficie donde se dibuja.
            esquina (tuple): posición (x, y) de la esquina superior izquierda. Por defecto
                (10, 10).
            tam (int): tamaño en píxeles del avatar. Por defecto 48.
        Salidas:
            Ninguna. Efecto: avatar y nombre dibujados.
        """
        x, y = esquina
        superficie.blit(self._ctx.avatares.obtener_superficie(self._ctx.id_usuario, tam), (x, y))
        superficie.blit(self._fuente.render(self._ctx.nombre_usuario, True, TEXTO), (x + tam + 8, y + tam // 2 - 8))


def describir_configuracion(cfg: ConfiguracionPartida) -> List[str]:
    """
    Descripción:
        Convierte la configuración de la partida en dos líneas de texto listas para
        mostrar: cómo termina la partida (por minutos si el modo es 'tiempo', por puntos
        en caso contrario) y cuántos segundos dura la congelación.
    Entradas:
        cfg (ConfiguracionPartida): configuración que se quiere describir.
    Salidas:
        List[str]: dos líneas, por ejemplo ['Fin de partida: 5 minutos', 'Congelación: 3 s'].
    """
    fin = f"{cfg.minutos_fin} minutos" if cfg.modo_fin == "tiempo" else f"{cfg.puntos_fin} puntos"
    return [f"Fin de partida: {fin}", f"Congelación: {cfg.segundos_congelacion} s"]


# 4. AUDIO Y EXPLORADOR DE ARCHIVO

def _construir_melodia() -> io.BytesIO:
    """
    Descripción:
        Genera la música del juego por código, sin archivos de audio. Crea una melodía
        suave de 16 notas (un arpegio) calculando las ondas de sonido a mano.

        Pasos:
        1. Para cada nota genera 0.4 segundos de audio a 22050 muestras por segundo.
        2. Cada muestra es una onda seno de la frecuencia de la nota más una segunda onda
           de menor volumen al doble de frecuencia, que le da un timbre más agradable.
        3. Aplica una envolvente: el volumen sube rápido al comenzar la nota y baja
           suavemente hasta el final, para evitar chasquidos entre notas.
        4. Empaqueta todas las muestras como números de 16 bits y las escribe en un
           archivo WAV (mono) dentro de memoria.
        5. Rebobina el buffer para que pueda leerse desde el inicio.
    Entradas:
        Ninguna.
    Salidas:
        io.BytesIO: archivo WAV en memoria, listo para que pygame lo reproduzca.
    """
    frecuencia_muestreo, duracion = 22050, 0.4
    notas = [523.25, 659.25, 783.99, 880.0, 783.99, 659.25, 587.33, 659.25,
             523.25, 659.25, 783.99, 1046.5, 880.0, 783.99, 659.25, 587.33]
    muestras = []
    for nota in notas:
        n = int(frecuencia_muestreo * duracion)
        for i in range(n):
            envolvente = min(1.0, i / 200) * (1 - i / n)
            onda = math.sin(2 * math.pi * nota * i / frecuencia_muestreo) \
                + 0.3 * math.sin(4 * math.pi * nota * i / frecuencia_muestreo)
            muestras.append(int(9000 * envolvente * onda))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frecuencia_muestreo)
        w.writeframes(struct.pack(f"<{len(muestras)}h", *muestras))
    buffer.seek(0)
    return buffer


def reproducir_musica() -> Optional[pygame.mixer.Sound]:
    """
    Descripción:
        Inicia la música de fondo en bucle infinito.

        Pasos:
        1. Inicia el mezclador de audio de pygame si todavía no está iniciado.
        2. Crea un sonido a partir de la melodía generada, con volumen 0.4.
        3. Lo reproduce repitiéndose sin fin (loops=-1).

        Si el computador no tiene dispositivo de audio no detiene el juego: avisa por
        consola y devuelve None.
    Entradas:
        Ninguna.
    Salidas:
        Optional[pygame.mixer.Sound]: el sonido en reproducción (para poder detenerlo
            después con stop()), o None si no hay audio disponible.
    """
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        sonido = pygame.mixer.Sound(file=_construir_melodia())
        sonido.set_volume(0.4)
        sonido.play(loops=-1)
        return sonido
    except pygame.error:
        print("Sin dispositivo de audio: la música no se reproducirá.")
        return None


def elegir_archivo_imagen() -> Optional[str]:
    """
    Descripción:
        Abre el explorador de archivos del sistema operativo para que el usuario escoja una
        imagen. Usa tkinter porque pygame no incluye un selector de archivos. Crea una
        ventana raíz invisible, la deja al frente para que el diálogo no quede escondido,
        muestra el diálogo con filtro de imágenes (png, jpg, jpeg, bmp, gif) o todos los
        archivos, y destruye la ventana al terminar. tkinter se importa dentro de la
        función porque solo se necesita en este momento.
    Entradas:
        Ninguna.
    Salidas:
        Optional[str]: ruta del archivo elegido, o None si el usuario canceló.
    """
    import tkinter as tk
    from tkinter import filedialog
    raiz = tk.Tk()
    raiz.withdraw()
    raiz.attributes("-topmost", True)
    ruta = filedialog.askopenfilename(title="Seleccione una imagen",
                                      filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.bmp *.gif"), ("Todos", "*.*")])
    raiz.destroy()
    return ruta or None


# 5. BASE DE LAS PANTALLAS

@dataclass
class Boton:
    """
    Descripción:
        Modelo simple de un botón: dónde está, qué texto tiene y qué hace al hacer clic.
        La pantalla lo dibuja y detecta los clics; el botón solo describe sus datos.
    Atributos:
        rectangulo (pygame.Rect): zona de la pantalla que ocupa el botón.
        etiqueta (str): texto del botón. Si está vacía no se dibuja, pero el clic sí
            funciona (se usa en las miniaturas de avatar, que son imágenes).
        accion (Callable[[], Optional[str]]): función que se ejecuta al hacer clic;
            devuelve un texto para cerrar la pantalla con ese resultado, o None para
            quedarse en ella.
        color (tuple): color de fondo del botón. Por defecto ACENTO.
    """

    rectangulo: pygame.Rect
    etiqueta: str
    accion: Callable[[], Optional[str]]
    color: tuple = ACENTO


class Pantalla:
    """
    Descripción:
        Clase base de todas las pantallas. Contiene el ciclo principal (eventos,
        actualización, dibujo, 30 cuadros por segundo) y las utilidades de dibujo, para
        que cada pantalla concreta solo defina sus botones y su dibujo.
        Una pantalla termina cuando ejecutar() devuelve un texto; ese texto le indica a
        principal.py a qué pantalla ir.
    Atributos:
        tecla_escape (Optional[str]): texto que devuelve ejecutar() al pulsar ESC; si es
            None, ESC no hace nada.
        ctx (Contexto): contexto de la aplicación.
        fuente, fuente_chica (pygame.font.Font): fuentes de tamaño 28 y 22.
        insignia (InsigniaAvatar): avatar y nombre del jugador.
        mensaje (str) y color_mensaje (tuple): texto de aviso o error que se muestra en la
            parte inferior y su color.
    """

    tecla_escape: Optional[str] = None

    def __init__(self, ctx: Contexto):
        """
        Descripción:
            Guarda el contexto, crea las dos fuentes, la insignia del avatar y deja el mensaje
            de aviso vacío (en color de texto normal).
        Entradas:
            ctx (Contexto): contexto de la aplicación. Sus servicios pueden usar repositorios JSON
            para pruebas locales o repositorios HTTP para compartir los datos online.
        Salidas:
            Ninguna.
        """
        self.ctx = ctx
        self.fuente, self.fuente_chica = pygame.font.SysFont(None, 28), pygame.font.SysFont(None, 22)
        self.insignia = InsigniaAvatar(ctx)
        self.mensaje, self.color_mensaje = "", TEXTO

    # ----- Métodos que las pantallas hijas sobrescriben -----
    def botones(self) -> List[Boton]:
        """
        Descripción:
            Método para sobrescribir: devuelve los botones de la pantalla. Se consulta en cada
            cuadro (para dibujar y para detectar clics), así que los botones pueden cambiar
            según el estado de la pantalla. En la clase base no hay botones.
        Entradas:
            Ninguna.
        Salidas:
            List[Boton]: botones de la pantalla (lista vacía en la clase base).
        """
        return []

    def actualizar(self) -> Optional[str]:
        """
        Descripción:
            Método para sobrescribir: se llama una vez por cuadro, antes de dibujar, para
            actualizar información (por ejemplo, volver a leer la partida). Si devuelve un
            texto, la pantalla se cierra con ese resultado. En la clase base no hace nada.
        Entradas:
            Ninguna.
        Salidas:
            Optional[str]: texto para cambiar de pantalla, o None para continuar.
        """
        return None

    def procesar_evento(self, _evento: pygame.event.Event) -> None:
        """Método opcional para que una pantalla hija procese eventos de entrada."""

    def dibujar(self, superficie: pygame.Surface) -> None:
        """
        Descripción:
            Método para sobrescribir: dibuja el contenido de la pantalla. Se llama una vez por
            cuadro. En la clase base no dibuja nada.
        Entradas:
            superficie (pygame.Surface): superficie donde se debe dibujar.
        Salidas:
            Ninguna.
        """
        pass

    # ----- Ciclo principal común -----
    def ejecutar(self, superficie: pygame.Surface) -> str:
        """
        Descripción:
            Ciclo principal de la pantalla: se repite hasta que algo devuelve un resultado.

            En cada vuelta:
            1. Revisa los eventos. Cerrar la ventana devuelve 'salir'. ESC devuelve
               tecla_escape si la pantalla la definió. Un clic izquierdo recorre los botones y
               ejecuta la acción del primero que contenga el punto del clic; si la acción
               devuelve un texto, ese texto es el resultado de la pantalla.
            2. Llama a actualizar(); si devuelve un texto, termina con él.
            3. Dibuja la pantalla y refresca la ventana.
            4. Limita la velocidad a 30 cuadros por segundo para no gastar procesador.
        Entradas:
            superficie (pygame.Surface): ventana donde se dibuja.
        Salidas:
            str: texto que indica por qué terminó ('salir', 'volver', 'arena', etc.).
        """
        reloj = pygame.time.Clock()
        while True:
            for evento in pygame.event.get():
                if evento.type == pygame.QUIT:
                    return "salir"
                if evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE and self.tecla_escape:
                    return self.tecla_escape
                self.procesar_evento(evento)
                if evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1:
                    for b in self.botones():
                        if b.rectangulo.collidepoint(evento.pos):
                            resultado = self._ejecutar_seguro(b.accion)
                            if resultado:
                                return resultado
                            break
            resultado = self.actualizar()
            if resultado:
                return resultado
            self.dibujar(superficie)
            pygame.display.flip()
            reloj.tick(30)

    def _ejecutar_seguro(self, accion):
        """
        Descripción:
            Ejecuta la acción de un botón protegiendo la pantalla de los errores esperados.
            Si la acción lanza un ErrorApp, no se cierra el programa: el mensaje del error se
            guarda para mostrarlo en rojo en la parte inferior y la pantalla continúa.
        Entradas:
            accion (Callable): función asociada al botón.
        Salidas:
            Optional[str]: lo que devuelva la acción, o None si hubo un ErrorApp.
        """
        try:
            return accion()
        except ErrorApp as e:
            self.mensaje, self.color_mensaje = str(e), ERROR
            return None
        except (OSError, RuntimeError, ValueError) as e:  # CAMBIO ONLINE: errores HTTP/servidor visibles en la pantalla
            self.mensaje, self.color_mensaje = str(e), ERROR
            return None

    def exito(self, texto: str) -> None:
        """
        Descripción:
            Muestra un mensaje de confirmación en verde en la parte inferior de la pantalla.
        Entradas:
            texto (str): mensaje que se quiere mostrar.
        Salidas:
            Ninguna.
        """
        self.mensaje, self.color_mensaje = texto, EXITO

    # ----- Utilidades de dibujo -----
    def texto(self, superficie, s, pos, fuente=None, color=TEXTO) -> None:
        """
        Descripción:
            Escribe un texto en la superficie en la posición indicada. Si no se indica fuente
            usa la fuente pequeña.
        Entradas:
            superficie (pygame.Surface): superficie donde se escribe.
            s (str): texto a escribir.
            pos (tuple): posición (x, y) de la esquina superior izquierda del texto.
            fuente (pygame.font.Font): fuente a usar; opcional.
            color (tuple): color RGB del texto. Por defecto TEXTO.
        Salidas:
            Ninguna.
        """
        superficie.blit((fuente or self.fuente_chica).render(s, True, color), pos)

    def dibujar_botones(self, superficie) -> None:
        """
        Descripción:
            Dibuja todos los botones de la pantalla que tengan etiqueta: un rectángulo con
            esquinas redondeadas del color del botón y su texto centrado en oscuro. Los
            botones sin etiqueta se omiten porque la pantalla los dibuja a su manera.
        Entradas:
            superficie (pygame.Surface): superficie donde se dibuja.
        Salidas:
            Ninguna.
        """
        for b in self.botones():
            if b.etiqueta:
                pygame.draw.rect(superficie, b.color, b.rectangulo, border_radius=8)
                t = self.fuente.render(b.etiqueta, True, (10, 10, 20))
                superficie.blit(t, (b.rectangulo.centerx - t.get_width() // 2,
                                    b.rectangulo.centery - t.get_height() // 2))

    def dibujar_encabezado(self, superficie, titulo: str) -> None:
        """
        Descripción:
            Dibuja la parte común de todas las pantallas: pinta el fondo, escribe el título
            arriba a la izquierda, coloca la insignia del avatar arriba a la derecha y escribe
            el mensaje de aviso (si lo hay) en la parte inferior, con su color.
        Entradas:
            superficie (pygame.Surface): superficie donde se dibuja.
            titulo (str): título de la pantalla.
        Salidas:
            Ninguna.
        """
        superficie.fill(FONDO)
        self.texto(superficie, titulo, (60, 40), self.fuente)
        self.insignia.dibujar(superficie, (superficie.get_width() - 220, 15))
        self.texto(superficie, self.mensaje, (60, 470), color=self.color_mensaje)


# 6. PANTALLA DE AVATAR

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


# 7. PANTALLA DE SALA DE ESPERA

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
            principal.py muestra el error). Luego carga la partida y anota el momento de la
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



# 8. PANTALLA DE CONFIGURACIÓn

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


# 9. PANTALLA DE LA ARENA

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
        control_entrada (acciones.ControlEntrada): dispositivo de entrada local seleccionado.
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
        acciones.iniciar()
        self.control_entrada = acciones.ControlEntrada()
        self._ultimo_movimiento = -self.INTERVALO_MOVIMIENTO_MS

    INTERVALO_MOVIMIENTO_MS = 150

    def _alternar_control(self) -> None:
        if self.control_entrada.modo == acciones.MODO_TECLADO:
            self.control_entrada.seleccionar(acciones.MODO_GAMEPAD)
            self.exito(f"Gamepad seleccionado: {self.control_entrada.nombre_gamepad}")
        else:
            self.control_entrada.seleccionar(acciones.MODO_TECLADO)
            self.exito("Teclado seleccionado.")

    def botones(self) -> List[Boton]:
        if self._partida.estado_juego and self._partida.estado_juego.get("status") == "finished":
            return []
        etiqueta = ("Usar teclado" if self.control_entrada.modo == acciones.MODO_GAMEPAD
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
                              self.control_entrada.modo == acciones.MODO_GAMEPAD else
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

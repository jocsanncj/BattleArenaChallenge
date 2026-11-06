"""
Base común de la interfaz del cliente.

Las pantallas concretas viven en módulos separados dentro de ui/. Este módulo
reúne contexto, componentes, colores, audio y utilidades visuales compartidas.
Las reglas de juego pertenecen a shared/domain/ y los modelos a shared/data.py.
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


# shared.data: modelo de configuración usado por las pantallas.
from shared.data import ConfiguracionPartida

# dominio: servicios y errores que usan los componentes de la interfaz.
#
# Nota: tkinter (explorador de archivos) se importa dentro de elegir_archivo_imagen,
# porque solo se necesita al cargar un avatar propio.
from shared.domain import ErrorApp, ServicioAvatar, ServicioPartida


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
        frontend/account/online.py y se entrega a cada pantalla, así no crean sus propios
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
        frontend/account/online.py a qué pantalla ir.
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

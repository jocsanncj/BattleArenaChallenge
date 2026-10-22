"""
PUNTO DE ENTRADA: une las capas y controla el flujo entre pantallas

Este archivo es el que se ejecuta. Crea los servicios y el contexto, abre la
ventana y decide qué pantalla se muestra en cada momento según el resultado de la
anterior (una especie de mapa de navegación).

Uso:
    python principal.py [id_usuario] [nombre]
    python principal.py 1 Ana        y, en otra terminal:   python principal.py 2 Luis

Flujo de pantallas:
    Avatar -> Sala de espera (Configuración / Iniciar partida) -> Arena (ventana nueva).
    ESC en la arena regresa al inicio.

Estructura del archivo:
    1. Librerías
    2. Funciones
    3. Ejecución del programa
"""


# 1. LIBRERÍAS


# Librerías estándar de Python (vienen incluidas, no hay que instalarlas)

# sys: lee los argumentos de la línea de comandos (id y nombre del jugador) y permite
# desactivar la creación de la carpeta __pycache__.
import sys

# Evita que Python cree la carpeta __pycache__. Debe ejecutarse antes de importar los
# módulos propios del proyecto; por eso va entre los imports.
sys.dont_write_bytecode = True

# Librería externa (se instala con: pip install pygame)

# pygame: inicia y cierra el sistema gráfico y de audio, y crea la ventana del juego.
import pygame

# Módulos propios del proyecto

# datos: repositorios JSON con los que se guardan avatares y partida.
from datos import RepositorioAvataresJson, RepositorioPartidaJson

# interfaz: contexto y pantallas que se muestran al usuario.
from interfaz import Contexto, PantallaArena, PantallaAvatar, PantallaConfiguracion, PantallaSala

# logica: servicios con las reglas del juego y el error ErrorApp, que se captura aquí para
# mostrarle el mensaje al usuario.
from logica import ErrorApp, ServicioAvatar, ServicioPartida


# 2. FUNCIONES

def abrir_ventana() -> pygame.Surface:
    """
    Descripción:
        Crea la ventana principal del juego, de 800 x 520 píxeles y con el título 'Battle
        Arena'. Primero cierra el módulo de video de pygame y lo vuelve a iniciar, de modo
        que cualquier ventana anterior (por ejemplo, la de la arena) desaparezca y se cree
        una ventana limpia.
    Entradas:
        Ninguna.
    Salidas:
        pygame.Surface: superficie de la ventana donde se dibujan las pantallas.
    """
    pygame.display.quit()
    pygame.display.init()
    ventana = pygame.display.set_mode((800, 520))
    pygame.display.set_caption("Battle Arena")
    return ventana


def principal():
    """
    Descripción:
        Función principal del programa: arma todo y maneja la navegación entre pantallas.

        Pasos:
        1. Lee de la línea de comandos el id y el nombre del jugador. Si faltan, usa el id

        1 y el nombre 'jugador1' (o el id dado).
        2. Inicia pygame, crea los servicios con sus repositorios JSON, el contexto, y abre
           la ventana.
        3. Entra en un ciclo que repite hasta que el estado sea 'salir'. El estado indica
           la pantalla actual y se actualiza con el resultado de cada una:
        - 'avatar': al continuar pasa a 'sala'; cualquier otra salida termina el programa.
        - 'sala': 'configuracion' abre la configuración, 'arena' abre la arena, 'volver'
          regresa a 'avatar' (el jugador sale de la sala); cualquier otra salida termina.
        - 'configuracion': 'volver' regresa a 'sala'; cualquier otra salida termina.
        - 'arena': al terminar el jugador sale de la sala; con 'volver' se abre otra vez la
          ventana principal y se regresa a 'avatar'; cualquier otra salida termina.
        4. Si una pantalla lanza un ErrorApp (sala llena, configuración bloqueada porque
           la partida ya inició, etc.), se vuelve a la pantalla alternativa anterior y el
           mensaje del error se le muestra al usuario como aviso.
        5. Al terminar, ocurra lo que ocurra (bloque finally), el jugador libera su lugar
           en la sala y se cierra pygame.
    Entradas:
        Ninguna (los datos del jugador se leen de sys.argv).
    Salidas:
        Ninguna. Efecto: el programa se ejecuta hasta que el usuario sale.
    """
    id_usuario = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    nombre = sys.argv[2] if len(sys.argv) > 2 else f"jugador{id_usuario}"

    pygame.init()
    ctx = Contexto(ServicioAvatar(RepositorioAvataresJson()), ServicioPartida(RepositorioPartidaJson()),
                   id_usuario, nombre)
    ventana = abrir_ventana()
    estado, aviso = "avatar", ""
    alternativa = {"sala": "avatar", "configuracion": "sala", "arena": "sala"}

    try:
        while estado != "salir":
            mostrado, aviso = aviso, ""
            try:
                if estado == "avatar":
                    estado = "sala" if PantallaAvatar(ctx, mostrado).ejecutar(ventana) == "siguiente" else "salir"
                elif estado == "sala":
                    resultado = PantallaSala(ctx, mostrado).ejecutar(ventana)
                    if resultado == "volver":
                        ctx.partida.salir(id_usuario)
                    estado = {"configuracion": "configuracion", "arena": "arena", "volver": "avatar"}.get(resultado, "salir")
                elif estado == "configuracion":
                    estado = "sala" if PantallaConfiguracion(ctx).ejecutar(ventana) == "volver" else "salir"
                elif estado == "arena":
                    resultado = PantallaArena(ctx).ejecutar()
                    ctx.partida.salir(id_usuario)
                    if resultado == "volver":
                        ventana = abrir_ventana()
                    estado = "avatar" if resultado == "volver" else "salir"
            except ErrorApp as e:
                aviso, estado = str(e), alternativa[estado]
    finally:
        ctx.partida.salir(id_usuario)
        pygame.quit()


# 3. EJECUCIÓN DEL PROGRAMA

# Solo se ejecuta cuando este archivo se corre directamente, no cuando se importa.
if __name__ == "__main__":
    principal()

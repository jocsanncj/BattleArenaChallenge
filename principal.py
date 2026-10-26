"""
PUNTO DE ENTRADA: une las capas y controla el flujo entre pantallas

Este módulo conserva el flujo legado de pantallas y los servicios del juego.
La entrada recomendada ahora es main.py, que integra autenticación y juego en un
único ciclo de escenas. Ejecutar este archivo también delega en main.py.

Uso:
    python main.py
    Inicia sesión y selecciona "Jugar online". El servidor asigna el mismo estado a todos los clientes.

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

# CAMBIO ONLINE: los repositorios remotos guardan avatares y partida en el servidor.
from datos import RepositorioAvataresServidor, RepositorioPartidaServidor

# interfaz: contexto y pantallas que se muestran al usuario.
from interfaz import Contexto, PantallaArena, PantallaAvatar, PantallaConfiguracion, PantallaSala

# logica: servicios con las reglas del juego y el error ErrorApp, que se captura aquí para
# mostrarle el mensaje al usuario.
from logica import ErrorApp, ServicioAvatar, ServicioPartida
from SistemaUsuario import id_usuario_actual, usuario_actual


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
        1. Obtiene el ID estable y el nombre de la sesión Firebase activa.
        2. Inicia pygame, crea los servicios con repositorios HTTP del servidor, el contexto y
           abre la ventana.
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
           en la sala y se cierra pygame. Los repositorios son remotos y requieren una sesión Firebase activa.
    Entradas:
        Ninguna. Requiere una sesión Firebase iniciada desde main.py.
    Salidas:
        Ninguna. Efecto: el programa se ejecuta hasta que el usuario sale.
    """
    # CAMBIO ONLINE: la identidad viene de Firebase, no de argumentos locales que
    # podrían colisionar entre dos computadoras. main.py es la entrada recomendada.
    id_usuario = id_usuario_actual()
    nombre = usuario_actual() or f"jugador{id_usuario}"

    pygame.init()
    ctx = Contexto(ServicioAvatar(RepositorioAvataresServidor()), ServicioPartida(RepositorioPartidaServidor()),
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
                aviso, estado = str(e), alternativa.get(estado, "avatar")
            except (OSError, RuntimeError, ValueError) as e:  # CAMBIO ONLINE: errores de conexión al servidor
                aviso, estado = str(e), alternativa.get(estado, "avatar")
    finally:
        ctx.partida.salir(id_usuario)
        pygame.quit()


# 3. EJECUCIÓN DEL PROGRAMA

# CAMBIO ONLINE: la entrada recomendada es la interfaz con escenas y autenticación.
# Se conserva principal() para compatibilidad, pero ejecutar este archivo abre main.py.
if __name__ == "__main__":
    from main import main as iniciar_aplicacion
    iniciar_aplicacion()

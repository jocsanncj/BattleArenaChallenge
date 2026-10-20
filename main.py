# Importa Pygame para crear la fuente utilizada por las pantallas.
import pygame  # pyright: ignore[reportMissingImports]

# Importa el ciclo de vida de la ventana principal.
from Window import Window
# Importa la escena inicial con las opciones de bienvenida.
from Escenas import MainMenuScene


# Evita iniciar la interfaz si este módulo se importa desde otro archivo.
if __name__ == "__main__":
    # Crea la ventana de 900 por 600 píxeles con su título.
    app = Window(width=900, height=600, title="Battle Arena Challenge")
    # Crea la fuente que compartirán los controles y mensajes de la interfaz.
    fuente = pygame.font.SysFont("Segoe UI", 20)
    # Construye la escena inicial y la asigna como pantalla activa.
    app.set_scene(MainMenuScene(fuente))
    # Entra en el ciclo de eventos hasta que el jugador cierre la ventana.
    app.run()
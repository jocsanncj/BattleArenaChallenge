import pygame  # pyright: ignore[reportMissingImports]
from Window import Window
from Escenas import MainMenuScene
if __name__ == "__main__":
    # 1. Instanciar la ventana
    app = Window(width=800, height=500, title="Proyecto Modular Pygame")

    # 2. Crear fuentes y escenas
    fuente = pygame.font.SysFont("Segoe UI", 24)
    menu_principal = MainMenuScene(fuente)

    # 3. Asignar la escena e iniciar
    app.set_scene(menu_principal)
    app.run()
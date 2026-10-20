import pygame  # pyright: ignore[reportMissingImports]

from Window import Window
from Escenas import MainMenuScene


if __name__ == "__main__":
    app = Window(width=900, height=600, title="Battle Arena Challenge")
    fuente = pygame.font.SysFont("Segoe UI", 20)
    app.set_scene(MainMenuScene(fuente))
    app.run()
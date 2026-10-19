import sys
import pygame  # pyright: ignore[reportMissingImports]

class Window:
    def __init__(self, width=900, height=600, title="Battle Arena Challenge", fps=60):
        pygame.init()
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption(title)
        
        self.clock = pygame.time.Clock()
        self.fps = fps
        self.running = False
        
        # Gestión de escenas o pantallas
        self.current_scene = None
    def set_scene(self, scene):
        """Asigna o cambia la escena activa."""
        self.current_scene = scene
        if self.current_scene:
            self.current_scene.window = self  # Referencia para que la escena controle la ventana
    def run(self):
        """Inicia el bucle principal de la ventana."""
        self.running = True
        try:
            while self.running:
                mouse_pos = pygame.mouse.get_pos()
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                        break
                    if self.current_scene:
                        self.current_scene.handle_event(event)
                if not self.running:
                    break
                if self.current_scene:
                    self.current_scene.update(mouse_pos)
                self.screen.fill((24, 24, 27))
                if self.current_scene:
                    self.current_scene.draw(self.screen)
                pygame.display.flip()
                self.clock.tick(self.fps)
        finally:
            self.running = False
            pygame.quit()
    def quit(self):
        """Cierra la ventana de forma segura."""
        self.running = False
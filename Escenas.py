class BaseScene:
    """Clase base de la cual heredarán las pantallas de tu proyecto."""
    def __init__(self):
        self.window = None
    def handle_event(self, event):
        pass
    def update(self, mouse_pos):
        pass
    def draw(self, surface):
        pass

class MainMenuScene(BaseScene):
    def __init__(self, font):
        super().__init__()
        self.font = font
        # Importante: Aquí integrarías tus clases Button, TextInput, etc.
        self.title_surf = self.font.render("Bienvenido a battle arena challenge, elige una opcion para continuar", True, (244, 244, 245))
    def draw(self, surface):
        surface.blit(self.title_surf, (50, 50))
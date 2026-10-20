import pygame  # pyright: ignore[reportMissingImports]


class Boton:
    def __init__(self, x, y, width, height, text, font, callback):
        self.rect = pygame.Rect(x, y, width, height)
        self.callback = callback
        self.font = font
        self.text = text

    def handle_event(self, event):
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
            and self.callback
        ):
            self.callback()

    def draw(self, surface, mouse_pos):
        hovered = self.rect.collidepoint(mouse_pos)
        color = (59, 130, 246) if hovered else (37, 99, 235)
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        texto = self.font.render(self.text, True, (255, 255, 255))
        surface.blit(texto, texto.get_rect(center=self.rect.center))
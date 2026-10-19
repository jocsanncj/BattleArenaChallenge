import pygame  # pyright: ignore[reportMissingImports]
class Boton:
    def __init__(self,x,y,width,height,text,font,callback):
        self.rect = pygame.Rect(x,y,width,height)
        self.callback = callback
        self.font = font
        self.text = text
    def handle_event(self,event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.callback:
                    self.callback()
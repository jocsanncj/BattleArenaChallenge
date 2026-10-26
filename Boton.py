# Importa Pygame para dibujar y detectar interacciones con los botones.
import pygame  # pyright: ignore[reportMissingImports]


## @brief Control visual que ejecuta una acción al recibir un clic.
class Boton:
    ## @brief Crea un botón y guarda los datos necesarios para dibujarlo y activarlo.
    ## @param x Coordenada horizontal de la esquina superior izquierda.
    ## @param y Coordenada vertical de la esquina superior izquierda.
    ## @param width Ancho del área interactiva.
    ## @param height Alto del área interactiva.
    ## @param text Texto que se muestra dentro del botón.
    ## @param font Fuente de Pygame usada para dibujar el texto.
    ## @param callback Función que se ejecuta al hacer clic; puede ser None.
    def __init__(self, x, y, width, height, text, font, callback):
        # Define el rectángulo utilizado para dibujar y detectar clics.
        self.rect = pygame.Rect(x, y, width, height)
        # Conserva la acción asociada al clic.
        self.callback = callback
        # Conserva la fuente elegida por la escena.
        self.font = font
        # Conserva la etiqueta visible del control.
        self.text = text

    ## @brief Ejecuta la acción del botón cuando recibe un clic izquierdo dentro de él.
    ## @param event Evento de Pygame que se debe comprobar.
    ## @return None.
    def handle_event(self, event):
        # Comprueba que el evento sea un clic izquierdo.
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            # Comprueba que el clic ocurriera dentro del rectángulo.
            and self.rect.collidepoint(event.pos)
            # No intenta ejecutar una acción que no se haya configurado.
            and self.callback
        ):
            # Ejecuta la función que la escena asignó al botón.
            self.callback()

    ## @brief Dibuja el botón y cambia su color cuando el cursor está encima.
    ## @param surface Superficie de Pygame donde se dibuja el control.
    ## @param mouse_pos Posición actual del cursor en la ventana.
    ## @return None.
    def draw(self, surface, mouse_pos):
        # Detecta si el cursor está dentro del área del botón.
        hovered = self.rect.collidepoint(mouse_pos)
        # Usa un azul más claro para indicar que el botón está bajo el cursor.
        color = (59, 130, 246) if hovered else (37, 99, 235)
        # Dibuja el fondo con esquinas redondeadas.
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        # Convierte la etiqueta en una superficie de texto blanca.
        texto = self.font.render(self.text, True, (255, 255, 255))
        # Coloca el texto en el centro del rectángulo del botón.
        surface.blit(texto, texto.get_rect(center=self.rect.center))
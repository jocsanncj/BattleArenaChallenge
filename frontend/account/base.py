"""Contrato de escenas y controles editables compartidos por el menú."""

import pygame


# Colores compartidos por las pantallas de cuenta.
FONDO = (24, 24, 27)
TEXTO = (244, 244, 245)
TEXTO_SECUNDARIO = (161, 161, 170)
CAMPO = (39, 39, 42)
ERROR = (248, 113, 113)


class BaseScene:
    ## @brief Define la interfaz mínima que espera la ventana para una escena.
    ## Las escenas concretas pueden sobrescribir los métodos vacíos.
    def __init__(self):
        # Se asigna cuando Window.set_scene activa esta escena.
        self.window = None

    ## @brief Recibe eventos de Pygame; las clases hijas implementan acciones.
    ## @param event Evento de teclado, ratón o ventana.
    ## @return None.
    def handle_event(self, event):
        # Método intencionalmente vacío para ofrecer una interfaz común.
        pass

    ## @brief Actualiza el estado de la escena en cada fotograma.
    ## @param mouse_pos Posición actual del cursor.
    ## @return None.
    def update(self, mouse_pos):
        # Método base sin animaciones ni actualizaciones predeterminadas.
        pass

    ## @brief Dibuja la escena en la superficie proporcionada.
    ## @param surface Superficie de Pygame que recibirá el dibujo.
    ## @return None.
    def draw(self, surface):
        # Método base vacío; la escena concreta debe dibujar sus elementos.
        pass



class CampoTexto:
    ## @brief Crea un campo de texto editable para las pantallas de cuenta.
    ## @param etiqueta Texto explicativo situado encima del campo.
    ## @param y Posición vertical del rectángulo.
    ## @param oculto Si True, muestra asteriscos en lugar del texto.
    ## @param max_length Cantidad máxima de caracteres permitidos.
    def __init__(self, etiqueta, y, oculto=False, max_length=256):
        # Guarda la etiqueta y coloca el campo en el centro de la ventana.
        self.etiqueta = etiqueta
        self.rect = pygame.Rect(250, y, 400, 42)
        # Inicia el valor sin texto introducido.
        self.texto = ""
        # Conserva las reglas visuales del campo.
        self.oculto = oculto
        self.max_length = max_length
        self.activo = False

    ## @brief Actualiza el contenido o foco del campo según el evento recibido.
    ## @param event Evento de Pygame que se procesa.
    ## @return None.
    def handle_event(self, event):
        # Un clic izquierdo activa el campo seleccionado y desactiva los demás.
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.activo = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.activo:
            # Retroceso elimina el último carácter cuando el campo tiene foco.
            if event.key == pygame.K_BACKSPACE:
                self.texto = self.texto[:-1]
            # Enter termina la edición del campo.
            elif event.key == pygame.K_RETURN:
                self.activo = False
            # Añade solo caracteres imprimibles y no supera el límite configurado.
            elif event.unicode.isprintable() and len(self.texto) < self.max_length:
                self.texto += event.unicode

    ## @brief Dibuja etiqueta, borde, fondo y contenido visible del campo.
    ## @param surface Superficie de Pygame sobre la que se dibuja.
    ## @param font Fuente utilizada para el texto introducido.
    ## @param label_font Fuente utilizada para la etiqueta.
    ## @return None.
    def draw(self, surface, font, label_font):
        # Renderiza y coloca la etiqueta encima del rectángulo.
        label = label_font.render(self.etiqueta, True, TEXTO)
        surface.blit(label, (self.rect.left, self.rect.top - 25))
        # Resalta el borde azul cuando el control tiene foco.
        color = (96, 165, 250) if self.activo else (82, 82, 91)
        pygame.draw.rect(surface, CAMPO, self.rect, border_radius=5)
        pygame.draw.rect(surface, color, self.rect, 2, border_radius=5)
        # En campos sensibles se dibuja un asterisco por cada carácter.
        visible_text = "*" * len(self.texto) if self.oculto else self.texto
        rendered = font.render(visible_text, True, TEXTO)
        # Recorta el texto al área interior para que no sobresalga del campo.
        surface.set_clip(self.rect.inflate(-12, -8))
        surface.blit(rendered, (self.rect.x + 8, self.rect.y + 9))
        surface.set_clip(None)


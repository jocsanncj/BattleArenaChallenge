# Importación heredada que no participa en el ciclo actual de la ventana.
import sys
# Importa Pygame para crear la ventana, recibir eventos y dibujar cada fotograma.
import pygame  # pyright: ignore[reportMissingImports]


## @brief Administra la ventana Pygame y el ciclo de vida de las escenas.
class Window:
    ## @brief Inicializa Pygame y construye la ventana principal del juego.
    ## @param width Ancho de la ventana en píxeles.
    ## @param height Alto de la ventana en píxeles.
    ## @param title Texto que aparece en la barra de título.
    ## @param fps Límite de fotogramas por segundo.
    def __init__(self, width=900, height=600, title="Battle Arena Challenge", fps=60):
        # Inicializa los módulos internos de Pygame.
        pygame.init()
        # Guarda las dimensiones para que otras partes puedan consultarlas.
        self.width = width
        self.height = height
        # Crea la superficie visible en la que se renderizará el juego.
        self.screen = pygame.display.set_mode((self.width, self.height))
        # Establece el texto de la barra superior de la ventana.
        pygame.display.set_caption(title)
        
        # Crea el reloj que controla la velocidad del ciclo principal.
        self.clock = pygame.time.Clock()
        # Guarda el límite de FPS solicitado.
        self.fps = fps
        # El ciclo empieza detenido y se activa en run().
        self.running = False
        
        # La escena activa se asigna después de crear la ventana.
        self.current_scene = None

    ## @brief Asigna una escena y le proporciona acceso a esta ventana.
    ## @param scene Objeto de escena que implementa handle_event, update y draw.
    ## @return None.
    def set_scene(self, scene):
        # Conserva la escena que se actualizará y dibujará en cada fotograma.
        self.current_scene = scene
        if self.current_scene:
            # Permite que la escena consulte o controle la ventana propietaria.
            self.current_scene.window = self

    ## @brief Ejecuta el bucle de eventos, actualización y dibujo de Pygame.
    ## @return None.
    ## @throws KeyboardInterrupt La interrupción se propaga después de liberar Pygame.
    def run(self):
        # Marca la aplicación como activa antes de procesar fotogramas.
        self.running = True
        try:
            # Repite el ciclo hasta que se solicite salir.
            while self.running:
                # Lee la posición del cursor una vez por fotograma.
                mouse_pos = pygame.mouse.get_pos()
                # Procesa los eventos pendientes de teclado, ratón y ventana.
                for event in pygame.event.get():
                    # La cruz de cierre termina el bucle principal.
                    if event.type == pygame.QUIT:
                        self.running = False
                        break
                    # Delega los eventos restantes a la escena actual.
                    if self.current_scene:
                        self.current_scene.handle_event(event)
                # No dibuja otro fotograma si el usuario ya cerró la ventana.
                if not self.running:
                    break
                # Permite que la escena actual actualice su estado.
                if self.current_scene:
                    self.current_scene.update(mouse_pos)
                # Limpia el fotograma anterior con el color de fondo.
                self.screen.fill((24, 24, 27))
                # Dibuja el contenido de la escena activa.
                if self.current_scene:
                    self.current_scene.draw(self.screen)
                # Presenta en pantalla el fotograma recién dibujado.
                pygame.display.flip()
                # Espera lo necesario para respetar el límite de FPS.
                self.clock.tick(self.fps)
        finally:
            # Deja el estado apagado incluso si el bucle termina por una excepción.
            self.running = False
            # Libera los recursos inicializados por Pygame.
            pygame.quit()

    ## @brief Solicita que el bucle de run termine en su siguiente comprobación.
    ## @return None.
    def quit(self):
        # El bucle principal detectará este cambio y cerrará la ventana.
        self.running = False
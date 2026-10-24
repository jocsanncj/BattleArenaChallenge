import os
import sys

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"  # Oculta el mensaje de bienvenida

import pygame
print("El archivo se está ejecutando")

RUTA_SONIDO = "media\Efecto.mp3"

def main():
    pygame.init()  # Inicia pygame y el audio

    # Si la ruta es relativa, la buscamos junto a este archivo .py
    ruta = RUTA_SONIDO
    if not os.path.isabs(ruta):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ruta)

    # Cargamos el sonido; si falla, avisamos y salimos
    try:
        sonido = pygame.mixer.Sound(ruta)
    except (FileNotFoundError, pygame.error) as error:
        print(f"No se pudo cargar el sonido: {ruta}")
        print(f"Detalle: {error}")
        sys.exit(1)

    # Pygame necesita una ventana con foco para recibir el teclado
    pantalla = pygame.display.set_mode((360, 140))
    pygame.display.set_caption("Tecla E = sonido")
    fuente = pygame.font.Font(None, 32)
    texto = fuente.render("Presiona E  (ESC para salir)", True, (235, 235, 240))

    reloj = pygame.time.Clock()
    corriendo = True

    while corriendo:
        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                corriendo = False
            elif evento.type == pygame.KEYDOWN:
                if evento.key == pygame.K_ESCAPE:
                    corriendo = False
                elif evento.key == pygame.K_e:
                    sonido.play()  # Reproduce el sonido

        pantalla.fill((25, 25, 35))
        pantalla.blit(texto, texto.get_rect(center=(180, 70)))
        pygame.display.flip()
        reloj.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
from pathlib import Path
import os
import pygame

AJUSTE = Path.home() / ".battle_arena" / "musica.txt"
MEDIA = Path(__file__).resolve().parents[1] / "Media"


## @brief Lee la preferencia de música guardada para el usuario.
def preferencia():
    try:
        return AJUSTE.read_text().strip() != "0"
    except OSError:
        return True


class Musica:
    ## @brief Inicializa el estado de música con la preferencia persistida.
    def __init__(self):
        self.activa = preferencia()
        self.sonando = False
        self.aviso = ""

    ## @brief Inicia la pista en bucle si el audio está habilitado.
    def iniciar(self):
        if not self.activa or self.sonando:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pistas = [MEDIA / ("musica" + ext) for ext in (".ogg", ".mp3", ".wav")]
            pista = next((p for p in pistas if p.is_file()), MEDIA / "Orbital.wav")
            pygame.mixer.music.load(str(pista))
            pygame.mixer.music.set_volume(.42)
            pygame.mixer.music.play(-1)
            self.sonando = True
            self.aviso = ""
        except (pygame.error, OSError) as exc:
            self.aviso = f"Audio no disponible. {exc}"

    ## @brief Detiene la pista activa sin modificar la preferencia.
    def detener(self):
        if self.sonando:
            pygame.mixer.music.stop()
            self.sonando = False

    ## @brief Alterna la reproducción y persiste la preferencia de música.
    def alternar(self):
        self.activa = not self.activa
        self.aviso = ""
        if self.activa:
            self.iniciar()
        else:
            self.detener()
        try:
            AJUSTE.parent.mkdir(parents=True, exist_ok=True)
            temporal = AJUSTE.with_suffix(f".{os.getpid()}.tmp")
            temporal.write_text("1" if self.activa else "0")
            temporal.replace(AJUSTE)
        except OSError:
            self.aviso = "La preferencia de música solo se guardará durante esta sesión."


musica = Musica()


_efecto = None


def sonido_extraccion():
    """US-18: reproduce el efecto de extracción en un canal independiente."""
    global _efecto
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        if _efecto is None:
            _efecto = pygame.mixer.Sound(str(MEDIA / "Efecto.mp3"))
        _efecto.play()
    except (pygame.error, OSError):
        pass

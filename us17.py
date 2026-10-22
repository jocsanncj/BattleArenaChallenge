"""
US17: ventana de victoria independiente con avatar, puntuaciones, confeti y música de celebración.
Desde el programa existente: launch_victory_window(result), que devuelve el subproceso de la ventana independiente.
Ejecución independiente: python us17.py --result-file final_result.json
US10 proporciona result tras combinar la decisión de US16 con los datos de los jugadores; incluye status, winner_id, players y scores.
"""

from __future__ import annotations

import argparse
from array import array
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time

try:
    import pygame
except ImportError:
    pygame = None


WINDOW_SIZE = (860, 700)
TEXT = (238, 241, 252)
MUTED = (167, 158, 190)
TEAL = (78, 226, 205)
ORANGE = (255, 159, 98)
PURPLE = (179, 151, 255)
GOLD = (255, 216, 112)
_AVATAR_CACHE = {}


def _require_pygame() -> None:
    if pygame is None:
        raise RuntimeError("Falta pygame. Ejecuta primero: python -m pip install pygame==2.6.1")


def draw_avatar(surface, avatar_id: str, center: tuple, size: int = 18,
                avatar_path: str | None = None) -> None:
    """
    Dibuja dos robots distintos; size es el radio y se comparte entre US10 y la ventana de victoria.
    """
    _require_pygame()
    x, y = (int(value) for value in center)
    radius = max(8, int(size))
    # Requiere US06: los datos del jugador proporcionan avatar_path (ruta de la imagen del avatar); sin ruta se usa un marcador, pero la integración final debe enviar el avatar real.
    if avatar_path:
        key = (str(avatar_path), radius)
        if key not in _AVATAR_CACHE:
            try:
                image = pygame.image.load(str(avatar_path))
                width, height = image.get_size()
                scale = radius * 2 / max(width, height)
                _AVATAR_CACHE[key] = pygame.transform.smoothscale(
                    image, (max(1, int(width * scale)), max(1, int(height * scale))))
            except (OSError, ValueError, pygame.error):
                _AVATAR_CACHE[key] = None
        image = _AVATAR_CACHE[key]
        if image is not None:
            surface.blit(image, image.get_rect(center=(x, y)))
            return
    color = ORANGE if avatar_id == "orbit" else TEAL
    pygame.draw.ellipse(surface, (8, 12, 26),
                        (x - radius, y + radius * 0.65, radius * 2, radius * 0.65))
    if avatar_id == "orbit":
        pygame.draw.circle(surface, color, (x, y), radius)
        pygame.draw.ellipse(surface, (255, 209, 170),
                            (x - radius * 1.25, y - radius * 0.35, radius * 2.5, radius * 0.7),
                            width=max(2, radius // 8))
        pygame.draw.rect(surface, (34, 28, 46),
                         (x - radius * 0.66, y - radius * 0.36, radius * 1.32, radius * 0.72),
                         border_radius=max(3, radius // 4))
    else:
        pygame.draw.line(surface, color, (x, y - radius), (x, y - radius * 1.4),
                         width=max(2, radius // 8))
        pygame.draw.circle(surface, GOLD, (x, int(y - radius * 1.43)), max(2, radius // 7))
        pygame.draw.rect(surface, color,
                         (x - radius, y - radius * 0.85, radius * 2, radius * 1.7),
                         border_radius=max(4, radius // 3))
        pygame.draw.rect(surface, (11, 41, 47),
                         (x - radius * 0.7, y - radius * 0.43, radius * 1.4, radius * 0.8),
                         border_radius=max(3, radius // 5))
    for sign in (-1, 1):
        pygame.draw.circle(surface, (244, 253, 255),
                           (int(x + sign * radius * 0.32), int(y - radius * 0.06)),
                           max(2, radius // 7))


def make_celebration_pcm(sample_rate: int = 22050, channels: int = 2) -> bytes:
    """
    Sintetiza una melodía original de ocho segundos con acordes y bajo, sin descargar archivos de música.
    """
    if sample_rate <= 0 or channels not in {1, 2}:
        raise ValueError("La frecuencia de muestreo debe ser positiva y el número de canales debe ser 1 o 2.")
    notes = [72, 76, 79, 84, 79, 76, 74, 79,
             69, 72, 76, 81, 79, 76, 72, 69,
             65, 69, 72, 77, 76, 72, 69, 65,
             67, 71, 74, 79, 83, 79, 74, 71]
    roots = [48, 45, 41, 43]
    pcm = array("h")

    def frequency(note):
        return 440 * 2 ** ((note - 69) / 12)

    for index in range(sample_rate * 8):
        t = index / sample_rate
        local = t % 0.25
        step = min(int(t / 0.25), len(notes) - 1)
        envelope = min(local / 0.015, 1) * max(0, 1 - local / 0.25) ** 0.5
        hz = frequency(notes[step])
        lead = (math.sin(math.tau * hz * t)
                + 0.2 * math.sin(math.tau * hz * 2 * t)) * envelope
        root = roots[min(int(t / 2), 3)]
        chord = sum(math.sin(math.tau * frequency(root + interval) * t)
                    for interval in (12, 15 if root == 45 else 16, 19)) / 3
        bass = math.sin(math.tau * frequency(root) * t)
        beat = math.exp(-(t % 0.5) * 28) * math.sin(math.tau * 90 * t)
        fade = min(t / 0.025, (8 - t) / 0.025, 1)
        sample = int(max(-1, min(1, (lead * 0.32 + chord * 0.13 + bass * 0.14 + beat * 0.08) * fade)) * 32767)
        for _ in range(channels):
            pcm.append(sample)
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()


class _CelebrationMusic:
    def __init__(self):
        self.sound = None
        self.channel = None
        self.muted = False

    def start(self) -> str:
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            sample_rate, sample_format, channels = pygame.mixer.get_init()
            if sample_format != -16:
                return "Audio no disponible: salida PCM incompatible."
            self.sound = pygame.mixer.Sound(buffer=make_celebration_pcm(sample_rate, channels))
            self.sound.set_volume(0.40)
            self.channel = self.sound.play(loops=-1)
            if self.channel is None:
                return "Audio no disponible: no hay canales libres."
            return ""
        except Exception:
            return "Audio no disponible en este equipo. La celebración continúa."

    def toggle(self):
        self.muted = not self.muted
        if self.sound:
            self.sound.set_volume(0 if self.muted else 0.40)

    def stop(self):
        if self.channel:
            self.channel.stop()


def _validated_result(result: dict) -> dict:
    """
    Lee solo el resultado final del servidor; esta ventana no añade puntos ni calcula el ganador.
    """
    if not isinstance(result, dict) or result.get("status") != "finished":
        raise ValueError("La ventana de victoria requiere un resultado final de la partida con status='finished'.")
    players = result.get("players")
    if not isinstance(players, list) or len(players) != 2:
        raise ValueError("El resultado final debe incluir a dos jugadores.")
    scores = result.get("scores", {})
    if not isinstance(scores, dict):
        raise ValueError("scores debe ser un diccionario que asocie cada ID de jugador con su puntuación.")
    normalized = []
    for player in players:
        if not isinstance(player, dict) or not player.get("player_id"):
            raise ValueError("Falta player_id en los datos del jugador.")
        score = scores.get(player["player_id"], player.get("score", 0))
        if type(score) is not int or score < 0:
            raise ValueError("La puntuación del jugador debe ser un entero no negativo.")
        normalized.append(dict(player, score=score,
                               username=str(player.get("username") or "Jugador")))
    if result.get("winner_id") not in {p["player_id"] for p in normalized}:
        raise ValueError("winner_id debe corresponder a un jugador de esta partida.")
    return dict(result, players=normalized)


class VictoryView:
    """
    Dibuja el resultado final en la ventana o en una Surface de prueba.
    """

    def __init__(self):
        _require_pygame()
        self.fonts = {}
        rng = random.Random(17)
        self.confetti = [(rng.randrange(860), rng.randrange(700), rng.randrange(35, 110),
                          rng.choice([TEAL, ORANGE, PURPLE, GOLD]), rng.randrange(3, 7))
                         for _ in range(86)]

    def _text(self, surface, text, position, size=20, color=TEXT, bold=False,
              center=False, max_width=None):
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = pygame.font.SysFont("Segoe UI,DejaVu Sans,Arial", size, bold=bold)
        font = self.fonts[key]
        text = str(text)
        if max_width is not None and font.size(text)[0] > max_width:
            while text and font.size(text + "…")[0] > max_width:
                text = text[:-1]
            text += "…"
        rendered = font.render(text, True, color)
        rect = rendered.get_rect()
        if center:
            rect.center = tuple(int(value) for value in position)
        else:
            rect.topleft = tuple(int(value) for value in position)
        surface.blit(rendered, rect)

    def render(self, surface, result: dict, elapsed: float = 0,
               audio_notice: str = "", muted: bool = False):
        surface.fill((18, 15, 37))
        pygame.draw.circle(surface, (37, 29, 65), (430, 295), 234)
        pygame.draw.circle(surface, (48, 37, 77), (430, 295), 188, width=1)
        for x, y, speed, color, size in self.confetti:
            yy = int((y + speed * elapsed) % 730) - 20
            xx = int(x + math.sin(elapsed + y) * 10)
            # Reserva las zonas de nombres y puntuaciones para que el confeti no oculte los resultados.
            if 332 <= yy <= 426 or 451 <= yy <= 556:
                continue
            pygame.draw.rect(surface, color, (xx, yy, size, size + 4))
        self._text(surface, "BATTLE ARENA  /  RESULTADOS", (430, 33), 13, PURPLE, True, True)
        self._text(surface, "¡VICTORIA!", (430, 92), 56, GOLD, True, True)
        players = result["players"]
        winner = next(p for p in players if p["player_id"] == result["winner_id"])
        pygame.draw.circle(surface, (71, 56, 79), (430, 264), 91)
        pygame.draw.polygon(surface, GOLD, [(399, 183), (399, 159), (415, 170),
                                          (430, 148), (445, 170), (461, 159), (461, 183)])
        draw_avatar(surface, winner.get("avatar_id", "nova"), (430, 267), 57, winner.get("avatar_path"))
        self._text(surface, winner["username"], (430, 361), 36, TEXT, True, True, max_width=740)
        self._text(surface, "¡Felicidades! La arena tiene un nuevo campeón.", (430, 405),
                   19, MUTED, center=True)
        for index, player in enumerate(sorted(players, key=lambda p: p["score"], reverse=True)):
            x = 80 + index * 360
            is_winner = player["player_id"] == result["winner_id"]
            rect = (x, 451, 340, 105)
            pygame.draw.rect(surface, (30, 28, 54), rect, border_radius=16)
            pygame.draw.rect(surface, GOLD if is_winner else (71, 64, 95),
                             rect, width=1, border_radius=16)
            draw_avatar(surface, player.get("avatar_id", "nova"), (x + 40, 502), 20, player.get("avatar_path"))
            self._text(surface, player["username"], (x + 75, 466), 20, TEXT, True, max_width=173)
            self._text(surface, "CAMPEÓN" if is_winner else "RIVAL", (x + 75, 507), 11,
                       GOLD if is_winner else MUTED, True)
            score_color = ORANGE if player.get("avatar_id") == "orbit" else TEAL
            self._text(surface, player["score"], (x + 294, 486), 31, score_color,
                       True, True, max_width=76)
            self._text(surface, "PUNTOS", (x + 294, 524), 10, MUTED, True, True)
        self._text(surface, "Gracias por jugar. ¡Nos vemos en la próxima partida!", (430, 583),
                   14, TEAL, center=True)
        if audio_notice:
            self._text(surface, audio_notice, (430, 613), 12, ORANGE, center=True, max_width=800)
        else:
            self._text(surface, "M  ·  " + ("ACTIVAR MÚSICA" if muted else "SILENCIAR MÚSICA"),
                       (430, 613), 12, MUTED, center=True)
        self._text(surface, "ESC  ·  CERRAR VENTANA", (430, 660), 14, TEXT, center=True)


def show_victory(result: dict, screenshot: str | Path | None = None) -> None:
    """
    Abre una ventana del sistema en este proceso; US10 debe ejecutar este archivo en un subproceso.
    """
    _require_pygame()
    # Requiere US16: recibe el resultado final con el ganador ya confirmado.
    result = _validated_result(result)
    pygame.mixer.pre_init(22050, -16, 2, 512)
    pygame.init()
    pygame.display.set_caption("Battle Arena · ¡Victoria!")
    music = _CelebrationMusic()
    try:
        screen = pygame.display.set_mode(WINDOW_SIZE)
        view = VictoryView()
        view.render(screen, result)
        pygame.display.flip()
        audio_notice = "" if screenshot else music.start()
        clock = pygame.time.Clock()
        started = time.monotonic()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                    music.toggle()
            view.render(screen, result, time.monotonic() - started, audio_notice, music.muted)
            pygame.display.flip()
            if screenshot:
                target = Path(screenshot)
                target.parent.mkdir(parents=True, exist_ok=True)
                pygame.image.save(screen, str(target))
                break
            clock.tick(60)
    finally:
        music.stop()
        pygame.quit()


def launch_victory_window(result: dict) -> subprocess.Popen:
    """
    Inicia una ventana del sistema en un proceso independiente sin cerrar ni bloquear la arena existente de Pygame.
    """
    _require_pygame()
    # Requiere US16: recibe el resultado final con el ganador ya confirmado.
    confirmed = _validated_result(result)
    payload = json.dumps(confirmed, ensure_ascii=False)
    options = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                             "--result-json", payload], **options)


def main() -> int:
    parser = argparse.ArgumentParser(description="US17: ventana independiente de victoria")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--result-file", type=Path, help="Resultado final JSON confirmado por US16")
    source.add_argument("--result-json", help=argparse.SUPPRESS)
    parser.add_argument("--screenshot", type=Path, help="Guardar una captura de prueba y salir")
    args = parser.parse_args()
    try:
        result = json.loads(args.result_json if args.result_json is not None
                            else args.result_file.read_text(encoding="utf-8"))
        show_victory(result, args.screenshot)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"US17: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

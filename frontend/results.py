"""
US17: ventana de victoria independiente con avatar, puntuaciones, confeti y música de celebración.
Desde el programa existente: launch_victory_window(result), que devuelve el subproceso de la ventana independiente.
Ejecución independiente: python -m frontend.results --result-file final_result.json
US10 proporciona result tras combinar la decisión de US16 con los datos de los jugadores; incluye status, winner_id, players y scores.
"""

from __future__ import annotations

import argparse
import base64
from io import BytesIO
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
from shared.game.rules import podio_final

from shared.musica import make_celebration_pcm

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


## @brief Comprueba que Pygame esté disponible antes de abrir la ceremonia.
def _require_pygame() -> None:
    if pygame is None:
        raise RuntimeError("Falta pygame. Ejecuta primero: python -m pip install pygame==2.6.1")


def draw_avatar(surface, avatar_id: str, center: tuple, size: int = 18,
                avatar_path: str | None = None,
                avatar_png: str | None = None) -> None:
    """
    Dibuja el avatar elegido, usando el catálogo o los bytes PNG personalizados.
    """
    _require_pygame()
    from shared.domain.avatares import AVATARES_PREDETERMINADOS, ServicioAvatar
    x, y = (int(value) for value in center)
    radius = max(8, int(size))
    if avatar_png:
        key = (avatar_id, radius)
        if key not in _AVATAR_CACHE:
            try:
                image = pygame.image.load(
                    BytesIO(base64.b64decode(avatar_png, validate=True)),
                    "avatar.png",
                )
                width, height = image.get_size()
                scale = radius * 2 / max(width, height)
                _AVATAR_CACHE[key] = pygame.transform.smoothscale(
                    image,
                    (max(1, int(width * scale)), max(1, int(height * scale))),
                )
            except (ValueError, pygame.error):
                _AVATAR_CACHE[key] = None
        image = _AVATAR_CACHE[key]
        if image is not None:
            surface.blit(image, image.get_rect(center=(x, y)))
            return
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
    avatar = next(
        (avatar for avatar in AVATARES_PREDETERMINADOS if avatar.id == avatar_id),
        None,
    )
    if avatar is not None:
        from frontend.personajes import imagen
        image = imagen(avatar.id, radius * 2)
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


class _CelebrationMusic:
    ## @brief Prepara el estado de audio independiente de la ventana principal.
    def __init__(self):
        self.sound = None
        self.channel = None
        from frontend.audio import preferencia
        self.muted = not preferencia()
    ## @brief Inicia la música de celebración y devuelve cualquier aviso de audio.
    def start(self) -> str:
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            sample_rate, sample_format, channels = pygame.mixer.get_init()
            if sample_format != -16:
                return "Audio no disponible: salida PCM incompatible."
            self.sound = pygame.mixer.Sound(buffer=make_celebration_pcm(sample_rate, channels))
            self.sound.set_volume(0 if self.muted else 0.40)
            self.channel = self.sound.play(loops=-1)
            if self.channel is None:
                return "Audio no disponible: no hay canales libres."
            return ""
        except Exception:
            return "Audio no disponible en este equipo. La celebración continúa."
    ## @brief Alterna el silencio de la música de celebración.
    def toggle(self):
        self.muted = not self.muted
        if self.sound:
            self.sound.set_volume(0 if self.muted else 0.40)
    ## @brief Detiene el canal de audio al cerrar la ceremonia.
    def stop(self):
        if self.channel:
            self.channel.stop()


def _validated_result(result: dict) -> dict:
    """
    Lee solo el resultado final del servidor; esta ventana no añade puntos ni calcula el ganador.
    """
    if not isinstance(result, dict) or result.get("status") != "finished":
        raise ValueError("La ventana de victoria requiere un resultado final de la partida con status='finished'.")
    if result.get("results_persisted") is not True:
        raise ValueError("La ceremonia requiere resultados consolidados por el servidor.")
    players = result.get("players")
    if not isinstance(players, list) or not 2 <= len(players) <= 3:
        raise ValueError("El resultado final debe incluir entre dos y tres jugadores.")
    scores = result.get("scores", {})
    if not isinstance(scores, dict):
        raise ValueError("scores debe ser un diccionario que asocie cada ID de jugador con su puntuación.")
    normalized = []
    player_ids = set()
    for player in players:
        if (not isinstance(player, dict)
                or not isinstance(player.get("player_id"), str)
                or not player["player_id"].strip()):
            raise ValueError("Falta player_id en los datos del jugador.")
        if player["player_id"] in player_ids:
            raise ValueError("El resultado final repite un jugador.")
        player_ids.add(player["player_id"])
        score = scores.get(player["player_id"])
        if type(score) is not int or score < 0:
            raise ValueError("La puntuación del jugador debe ser un entero no negativo.")
        if player.get("score") != score:
            raise ValueError("Los puntajes de jugador y resultado final no coinciden.")
        new_record = player.get("new_record", False)
        personal_record = player.get("personal_record", score)
        if type(new_record) is not bool or type(personal_record) is not int:
            raise ValueError("Los datos del récord personal no son válidos.")
        if personal_record < score or (new_record and personal_record != score):
            raise ValueError("El récord personal no puede ser menor que el puntaje de la partida.")
        avatar_png = player.get("avatar_png")
        if avatar_png is not None and (
            not isinstance(avatar_png, str) or len(avatar_png) > 2_000_000
        ):
            raise ValueError("La imagen del avatar no tiene un formato válido.")
        avatar_id = player.get("avatar_id", "")
        if not isinstance(avatar_id, str):
            raise ValueError("El identificador del avatar no es válido.")
        normalized.append(dict(player, score=score,
                            username=str(player.get("username") or "Jugador"),
                            new_record=new_record,
                            personal_record=personal_record))
    if set(scores) != player_ids:
        raise ValueError("Los puntajes no coinciden con la lista de participantes.")
    winner_id = result.get("winner_id")
    top_score = max(player["score"] for player in normalized)
    if (not isinstance(winner_id, str)
            or winner_id not in player_ids
            or next(p["score"] for p in normalized if p["player_id"] == winner_id) != top_score
            or sum(p["score"] == top_score for p in normalized) != 1):
        raise ValueError("winner_id debe ser el único jugador con el puntaje más alto.")
    duration = result.get("duration_seconds", result.get("elapsed_seconds"))
    if (isinstance(duration, bool) or not isinstance(duration, (int, float))
            or not math.isfinite(duration) or duration < 0):
        raise ValueError("La duración final de la partida no es válida.")
    # Con el ganador y los puntajes ya validados, podio_final asigna los puestos con la regla compartida.
    # El escritorio y la pantalla móvil pueden así mostrar el mismo orden cuando dos participantes tienen igual puntaje.
    return dict(result, players=podio_final(normalized), duration_seconds=int(round(duration)))


class VictoryView:
    """
    Dibuja el resultado final en la ventana o en una Surface de prueba.
    """
    ## @brief Prepara fuentes y partículas reproducibles para la ceremonia.
    def __init__(self):
        _require_pygame()
        self.fonts = {}
        rng = random.Random(17)
        self.confetti = [(rng.randrange(860), rng.randrange(700), rng.randrange(35, 110),
                        rng.choice([TEAL, ORANGE, PURPLE, GOLD]), rng.randrange(3, 7))
                        for _ in range(86)]

    ## @brief Renderiza texto ajustado y alineado en la superficie de victoria.
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

    ## @brief US-17 y US-26: dibuja ganador, podio, récords y celebración.
    def render(self, surface, result: dict, elapsed: float = 0,
            audio_notice: str = "", muted: bool = False):
        surface.fill((18, 15, 37))
        pygame.draw.circle(surface, (37, 29, 65), (430, 295), 234)
        pygame.draw.circle(surface, (48, 37, 77), (430, 295), 188, width=1)
        for x, y, speed, color, size in self.confetti:
            yy = int((y + speed * elapsed) % 730) - 20
            xx = int(x + math.sin(elapsed + y) * 10)
            # Reserva las zonas de nombres y puntuaciones para que el confeti no oculte los resultados.
            if 315 <= yy <= 588:
                continue
            pygame.draw.rect(surface, color, (xx, yy, size, size + 4))
        self._text(surface, "BATTLE ARENA  /  RESULTADOS", (430, 33), 13, PURPLE, True, True)
        self._text(surface, "¡VICTORIA!", (430, 92), 56, GOLD, True, True)
        players = result["players"]
        winner = next(p for p in players if p["player_id"] == result["winner_id"])
        pygame.draw.circle(surface, (71, 56, 79), (430, 205), 73)
        pygame.draw.polygon(surface, GOLD, [(405, 151), (405, 133), (418, 143),
                                        (430, 126), (442, 143), (455, 133), (455, 151)])
        draw_avatar(
            surface,
            winner.get("avatar_id", ""),
            (430, 210),
            46,
            winner.get("avatar_path"),
            winner.get("avatar_png"),
        )
        self._text(surface, winner["username"], (430, 296), 32, TEXT, True, True, max_width=740)
        self._text(
            surface,
            f"Puntaje final: {winner['score']} puntos",
            (430, 331),
            18,
            MUTED,
            center=True,
        )
        duration = result["duration_seconds"]
        self._text(
            surface,
            f"Duración de la partida: {duration // 60:02d}:{duration % 60:02d}",
            (430, 369),
            17,
            TEAL,
            True,
            True,
        )
        card_width, card_gap = 250, 20
        first_x = (WINDOW_SIZE[0] - (len(players) * card_width + (len(players) - 1) * card_gap)) // 2
        for index, player in enumerate(players):
            x = first_x + index * (card_width + card_gap)
            is_winner = player["player_id"] == result["winner_id"]
            rect = (x, 408, card_width, 174)
            pygame.draw.rect(surface, (30, 28, 54), rect, border_radius=16)
            pygame.draw.rect(
                surface,
                GOLD if is_winner else (71, 64, 95),
                rect,
                width=2 if is_winner else 1,
                border_radius=16,
            )
            draw_avatar(
                surface,
                player.get("avatar_id", ""),
                (x + 38, 447),
                24,
                player.get("avatar_path"),
                player.get("avatar_png"),
            )
            self._text(
                surface,
                f"{player['position']}. LUGAR",
                (x + 74, 427),
                12,
                GOLD if is_winner else PURPLE,
                True,
            )
            self._text(
                surface,
                player["username"],
                (x + 74, 447),
                18,
                TEXT,
                True,
                max_width=card_width - 86,
            )
            score_color = ORANGE if player.get("avatar_id") == "orbit" else TEAL
            self._text(
                surface,
                f"{player['score']} puntos",
                (x + 16, 487),
                20,
                score_color,
                True,
            )
            record_text = (
                f"¡Nuevo récord! {player['personal_record']}"
                if player["new_record"]
                else f"Récord personal: {player['personal_record']}"
            )
            self._text(
                surface,
                record_text,
                (x + 16, 529),
                14,
                GOLD if player["new_record"] else MUTED,
                player["new_record"],
                max_width=card_width - 32,
            )
        self._text(surface, "Gracias por jugar. ¡Nos vemos en la próxima partida!", (430, 612),
                14, TEAL, center=True)
        if audio_notice:
            self._text(surface, audio_notice, (430, 640), 12, ORANGE, center=True, max_width=800)
        else:
            self._text(surface, "M  ·  " + ("ACTIVAR MÚSICA" if muted else "SILENCIAR MÚSICA"),
                    (430, 640), 12, MUTED, center=True)
        self._text(surface, "ESC  ·  CERRAR VENTANA", (430, 675), 14, TEXT, center=True)


## @brief US-17 y US-26: muestra la ceremonia de victoria en una ventana Pygame.
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


## @brief US-17 y US-26: lanza la ceremonia en un proceso aislado.
def launch_victory_window(result: dict) -> subprocess.Popen:
    """
    Inicia una ventana del sistema en un proceso independiente sin cerrar ni bloquear la arena existente de Pygame.
    """
    _require_pygame()
    # Requiere US16: recibe el resultado final con el ganador ya confirmado.
    confirmed = _validated_result(result)
    payload = json.dumps(confirmed, ensure_ascii=False)
    result_path = None
    options = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix="battle-arena-result-",
            delete=False,
        ) as result_file:
            result_file.write(payload)
            result_path = Path(result_file.name)
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "frontend.results",
                "--result-file",
                str(result_path),
                "--delete-result-file",
            ],
            cwd=Path(__file__).resolve().parents[1],
            **options,
        )
    except (OSError, ValueError):
        if result_path is not None:
            result_path.unlink(missing_ok=True)
        raise


## @brief Valida argumentos y ejecuta la ventana de resultados.
def main() -> int:
    parser = argparse.ArgumentParser(description="US17: ventana independiente de victoria")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--result-file", type=Path, help="Resultado final JSON confirmado por US16")
    source.add_argument("--result-json", help=argparse.SUPPRESS)
    parser.add_argument("--delete-result-file", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--screenshot", type=Path, help="Guardar una captura de prueba y salir")
    args = parser.parse_args()
    try:
        result = json.loads(args.result_json if args.result_json is not None
                            else args.result_file.read_text(encoding="utf-8"))
        show_victory(result, args.screenshot)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"US17: {exc}", file=sys.stderr)
        return 1
    finally:
        if args.delete_result_file and args.result_file is not None:
            args.result_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

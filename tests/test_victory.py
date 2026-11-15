import base64
import json
import os
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from frontend.results import (
    VictoryView,
    _validated_result,
    launch_victory_window,
)


def _result(scores):
    players = [
        {
            "player_id": player_id,
            "username": username,
            "avatar_id": f"avatar_{index + 1}",
            "score": score,
            "new_record": index == 0,
            "personal_record": score if index == 0 else max(score, 9),
        }
        for index, (player_id, username, score) in enumerate(scores)
    ]
    return {
        "status": "finished",
        "results_persisted": True,
        "winner_id": max(players, key=lambda player: player["score"])["player_id"],
        "players": players,
        "scores": {player["player_id"]: player["score"] for player in players},
        "elapsed_seconds": 125,
    }


class VictoryCeremonyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.font.init()

    def test_validates_two_or_three_players_and_assigns_podium_places(self):
        two_players = _validated_result(
            _result([("one", "Uno", 5), ("two", "Dos", 2)])
        )
        three_players = _validated_result(
            _result([("one", "Uno", 5), ("two", "Dos", 2), ("three", "Tres", 1)])
        )
        self.assertEqual(
            [(player["position"], player["username"]) for player in two_players["players"]],
            [(1, "Uno"), (2, "Dos")],
        )
        self.assertEqual(
            [(player["position"], player["username"]) for player in three_players["players"]],
            [(1, "Uno"), (2, "Dos"), (3, "Tres")],
        )
        self.assertEqual(three_players["duration_seconds"], 125)

    def test_refuses_to_show_results_before_server_persistence(self):
        result = _result([("one", "Uno", 5), ("two", "Dos", 2)])
        result["results_persisted"] = False
        with self.assertRaisesRegex(ValueError, "consolidados"):
            _validated_result(result)

    def test_launcher_passes_final_data_through_a_temporary_file(self):
        result = _validated_result(
            _result([("one", "Uno", 5), ("two", "Dos", 2)])
        )
        with patch("frontend.results.subprocess.Popen") as process:
            launch_victory_window(result)
        command = process.call_args.args[0]
        result_path = Path(command[4])
        try:
            saved = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertTrue(saved["results_persisted"])
            self.assertEqual(len(saved["players"]), 2)
            self.assertEqual(saved["duration_seconds"], 125)
            self.assertIn("--delete-result-file", command)
            self.assertEqual(
                process.call_args.kwargs["cwd"],
                Path(__file__).resolve().parents[1],
            )
        finally:
            result_path.unlink(missing_ok=True)

    def test_renders_podium_for_two_and_three_players(self):
        view = VictoryView()
        for scores in (
            [("one", "Uno", 5), ("two", "Dos", 2)],
            [("one", "Uno", 5), ("two", "Dos", 2), ("three", "Tres", 1)],
        ):
            result = _validated_result(_result(scores))
            surface = pygame.Surface((860, 700))
            view.render(surface, result)
            self.assertEqual(surface.get_size(), (860, 700))

    def test_renders_custom_avatar_image_in_the_ceremony(self):
        image = pygame.Surface((24, 24), pygame.SRCALPHA)
        image.fill((220, 30, 50, 255))
        buffer = BytesIO()
        pygame.image.save(image, buffer, "avatar.png")
        result = _validated_result(
            _result([("one", "Uno", 5), ("two", "Dos", 2)])
        )
        result["players"][0]["avatar_png"] = base64.b64encode(
            buffer.getvalue()
        ).decode("ascii")
        VictoryView().render(pygame.Surface((860, 700)), result)


if __name__ == "__main__":
    unittest.main()

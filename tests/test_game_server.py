import hashlib
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from server import app as servidor
from backend.repository import SQLiteRepository
from shared.data import RepositorioPartidaJson
from shared.domain import ServicioPartida


class GameServerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_repo = servidor.repo
        self.old_file = servidor._GAME_FILE
        self.old_arena = servidor._GAME_ARENA
        self.old_users = servidor._GAME_USERS
        self.old_player_ids = servidor._GAME_PLAYER_IDS
        self.old_move_times = servidor._MOVE_TIMES
        self.old_firebase_uids = servidor._GAME_FIREBASE_UIDS.copy()
        servidor.repo = SQLiteRepository(Path(self.temp.name) / "test.db")
        servidor._GAME_FILE = Path(self.temp.name) / "game.json"
        servidor._GAME_ARENA = None
        servidor._GAME_USERS = {}
        servidor._GAME_PLAYER_IDS = {}
        servidor._MOVE_TIMES = {}
        servidor._GAME_FIREBASE_UIDS.clear()
        self.identities = {
            "token-one": {"uid": "user-one", "email": "one@example.test", "email_verified": True},
            "token-two": {"uid": "user-two", "email": "two@example.test", "email_verified": True},
        }
        servidor.repo.crear("user-one", "JugadorUno", "one@example.test")
        servidor.repo.crear("user-two", "JugadorDos", "two@example.test")
        self.auth_patch = patch.object(
            servidor.auth,
            "verify_id_token",
            side_effect=lambda token, **_kwargs: self.identities[token],
        )
        self.auth_patch.start()
        self.firebase_app_patch = patch.object(servidor, "_firebase_app", return_value=None)
        self.firebase_app_patch.start()
        servidor.app.config.update(TESTING=True)
        self.client_one = servidor.app.test_client()
        self.client_two = servidor.app.test_client()

    def tearDown(self):
        self.auth_patch.stop()
        self.firebase_app_patch.stop()
        servidor.repo = self.old_repo
        servidor._GAME_FILE = self.old_file
        servidor._GAME_ARENA = self.old_arena
        servidor._GAME_USERS = self.old_users
        servidor._GAME_PLAYER_IDS = self.old_player_ids
        servidor._MOVE_TIMES = self.old_move_times
        servidor._GAME_FIREBASE_UIDS.clear()
        servidor._GAME_FIREBASE_UIDS.update(self.old_firebase_uids)
        self.temp.cleanup()

    @staticmethod
    def _headers(token):
        return {"Authorization": f"Bearer {token}"}

    def test_server_owns_join_movement_score_and_winner(self):
        self.client_one.put(
            "/api/game/avatar",
            json={"tipo": "predeterminado", "valor": "avatar_1"},
            headers=self._headers("token-one"),
        )
        self.client_two.put(
            "/api/game/avatar",
            json={"tipo": "predeterminado", "valor": "avatar_2"},
            headers=self._headers("token-two"),
        )
        self.assertEqual(self.client_one.post(
            "/api/game/join", headers=self._headers("token-one")
        ).status_code, 200)
        config = {
            "modo_fin": "puntos",
            "minutos_fin": 1,
            "puntos_fin": 2,
            "segundos_congelacion": 3,
        }
        self.assertEqual(self.client_one.put(
            "/api/game/config", json=config, headers=self._headers("token-one")
        ).status_code, 200)
        self.assertEqual(self.client_two.post(
            "/api/game/join", headers=self._headers("token-two")
        ).status_code, 200)
        self.assertEqual(self.client_one.post(
            "/api/game/start", headers=self._headers("token-one")
        ).status_code, 200)

        self.assertEqual(self.client_one.post(
            "/api/game/move", json={"direction": "right"},
            headers=self._headers("token-one"),
        ).json["state"]["players"][0]["score"], 1)
        time.sleep(0.13)
        result = self.client_one.post(
            "/api/game/move", json={"direction": "right"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["state"]["status"], "finished")

        shared = self.client_two.get(
            "/api/game/state", headers=self._headers("token-two")
        ).json["game"]
        self.assertEqual(shared["status"], "finished")
        expected_player_id = str(int.from_bytes(hashlib.sha256(b"user-one").digest()[:4], "big") & 0x7fffffff)
        self.assertEqual(shared["winner_id"], expected_player_id)
        self.assertEqual(shared["scores"][shared["winner_id"]], 2)
        self.assertEqual(len(shared["players"]), 2)
        expected_user_id = int.from_bytes(hashlib.sha256(b"user-one").digest()[:4], "big") & 0x7fffffff
        self.assertEqual(shared["players"][0]["user_id"], expected_user_id)

    def test_finished_match_is_saved_once_and_returned_in_ranking_and_profile(self):
        config = {
            "modo_fin": "puntos",
            "minutos_fin": 1,
            "puntos_fin": 1,
            "segundos_congelacion": 3,
        }
        for client, token, avatar in (
            (self.client_one, "token-one", "avatar_1"),
            (self.client_two, "token-two", "avatar_2"),
        ):
            self.assertEqual(
                client.put(
                    "/api/game/avatar",
                    json={"tipo": "predeterminado", "valor": avatar},
                    headers=self._headers(token),
                ).status_code,
                200,
            )
        for client, token in (
            (self.client_one, "token-one"),
            (self.client_two, "token-two"),
        ):
            self.assertEqual(
                client.post("/api/game/join", headers=self._headers(token)).status_code,
                200,
            )
        self.assertEqual(
            self.client_one.put(
                "/api/game/config",
                json=config,
                headers=self._headers("token-one"),
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client_one.post(
                "/api/game/start", headers=self._headers("token-one")
            ).status_code,
            200,
        )

        final = self.client_one.post(
            "/api/game/move",
            json={"direction": "right"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(final.status_code, 200)
        self.assertEqual(final.json["state"]["status"], "finished")

        repeated = self.client_two.get(
            "/api/game/state", headers=self._headers("token-two")
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json["game"]["status"], "finished")

        ranking = self.client_one.get("/api/ranking")
        self.assertEqual(ranking.status_code, 200)
        self.assertEqual(
            ranking.json["ranking"],
            [{"position": 1, "name": "JugadorUno", "points": 1, "wins": 1},
             {"position": 2, "name": "JugadorDos", "points": 0, "wins": 0}],
        )
        profile = self.client_one.get(
            "/api/profile", headers=self._headers("token-one")
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json["user"]["statistics"]["matches_played"], 1)
        self.assertEqual(profile.json["user"]["statistics"]["points_accumulated"], 1)
        self.assertEqual(profile.json["user"]["match_history"][0]["result"], "victoria")

        with servidor.repo._con() as con:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM partidas").fetchone()[0],
                2,
            )

    def test_clients_cannot_replace_the_authoritative_game_state(self):
        self.client_one.post("/api/game/join", headers=self._headers("token-one"))
        self.assertEqual(self.client_one.put(
            "/api/game/state", json={"jugadores": [], "configuracion": {}},
            headers=self._headers("token-one"),
        ).status_code, 405)

    def test_invalid_move_is_rejected(self):
        response = self.client_one.post(
            "/api/game/move", json={"direction": "teleport"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(response.status_code, 400)

    def test_json_repository_keeps_its_existing_local_start_flow(self):
        partida = ServicioPartida(
            RepositorioPartidaJson(str(Path(self.temp.name) / "local-game.json"))
        )
        partida.unirse(101, "Uno")
        partida.unirse(202, "Dos")
        partida.iniciar()
        self.assertEqual(partida.obtener_partida().estado, "jugando")


if __name__ == "__main__":
    unittest.main()

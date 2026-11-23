import hashlib
from contextlib import closing
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from server import app as servidor
from backend.repository import SQLiteRepository
from frontend import personajes
from shared.data import Jugador, RepositorioPartidaJson
from shared.domain import ServicioPartida


class GameServerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        cache = patch.object(servidor, "_RESULTADOS_RECIENTES", {})
        cache.start()
        self.addCleanup(cache.stop)
        self.old_repo = servidor.repo
        self.old_file = servidor._GAME_FILE
        self.old_arena = servidor._GAME_ARENA
        self.old_users = servidor._GAME_USERS
        self.old_player_ids = servidor._GAME_PLAYER_IDS
        self.old_move_times = servidor._MOVE_TIMES
        self.old_reactor = servidor._REACTOR
        self.old_firebase_uids = servidor._GAME_FIREBASE_UIDS.copy()
        servidor.repo = SQLiteRepository(Path(self.temp.name) / "test.db")
        servidor._GAME_FILE = Path(self.temp.name) / "game.json"
        servidor._GAME_ARENA = None
        servidor._GAME_USERS = {}
        servidor._GAME_PLAYER_IDS = {}
        servidor._MOVE_TIMES = {}
        servidor._REACTOR = {"available_at": 0.0, "active": None, "events": set()}
        servidor._GAME_FIREBASE_UIDS.clear()
        self.identities = {
            "token-one": {"uid": "user-one", "email": "one@example.test", "email_verified": True},
            "token-two": {"uid": "user-two", "email": "two@example.test", "email_verified": True},
            "token-three": {"uid": "user-three", "email": "three@example.test", "email_verified": True},
            "token-four": {"uid": "user-four", "email": "four@example.test", "email_verified": True},
        }
        servidor.repo.crear("user-one", "JugadorUno", "one@example.test")
        servidor.repo.crear("user-two", "JugadorDos", "two@example.test")
        servidor.repo.crear("user-three", "JugadorTres", "three@example.test")
        servidor.repo.crear("user-four", "JugadorCuatro", "four@example.test")
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
        self.client_three = servidor.app.test_client()
        self.client_four = servidor.app.test_client()

    def tearDown(self):
        self.auth_patch.stop()
        self.firebase_app_patch.stop()
        servidor.repo = self.old_repo
        servidor._GAME_FILE = self.old_file
        servidor._GAME_ARENA = self.old_arena
        servidor._GAME_USERS = self.old_users
        servidor._GAME_PLAYER_IDS = self.old_player_ids
        servidor._MOVE_TIMES = self.old_move_times
        servidor._REACTOR = self.old_reactor
        servidor._GAME_FIREBASE_UIDS.clear()
        servidor._GAME_FIREBASE_UIDS.update(self.old_firebase_uids)
        self.temp.cleanup()

    @staticmethod
    def _headers(token):
        return {"Authorization": f"Bearer {token}"}

    def test_mobile_catalog_serves_desktop_portraits_and_sprites(self):
        from flask import template_rendered

        contexts = []
        def capture(_app, template, context, **extra):
            contexts.append(context)

        with template_rendered.connected_to(capture, servidor.app):
            self.assertEqual(self.client_one.get("/movil").status_code, 200)
        catalog = contexts[0]["avatares"]
        self.assertEqual({a["id"]: a["nombre"] for a in catalog}, personajes.NOMBRES)
        self.assertEqual(contexts[0]["escenarios"], [mapa.nombre for mapa in servidor.MAPAS])
        for avatar in catalog:
            for field, folder in (("retrato", "retratos"), ("personaje", "personajes")):
                with self.subTest(avatar=avatar["id"], asset=field):
                    with self.client_one.get(avatar[field]) as response:
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.mimetype, "image/png")
                        self.assertEqual(response.data, (personajes.MEDIA / folder / (avatar["id"] + ".png")).read_bytes())
        self.assertEqual(self.client_one.get("/movil/avatares/retratos/desconocido.png").status_code, 404)

    def test_mobile_lobby_avatar_ids_match_arena_and_keep_desktop_player_format(self):
        one, two = self._headers("token-one"), self._headers("token-two")
        self.client_one.post("/api/game/join", headers=one)
        self.client_two.post("/api/game/join", headers=two)
        initial = self.client_one.get("/api/game/state", headers=one).json
        players = [Jugador(**row) for row in initial["partida"]["jugadores"]]
        first, second = (str(player.id_usuario) for player in players)
        self.assertEqual(str(initial["jugador_actual_id"]), first)
        self.assertEqual(initial["avatares_sala"], {first: "avatar_1", second: "avatar_1"})

        custom = {"tipo": "personalizado", "valor": "contenido-png-del-jugador"}
        self.client_one.put("/api/game/avatar", headers=one, json={"tipo": "predeterminado", "valor": "avatar_3"})
        self.client_two.put("/api/game/avatar", headers=two, json=custom)
        self.assertEqual(self.client_one.post("/api/game/start", headers=one).status_code, 200)
        response = self.client_two.get("/api/game/state", headers=two)
        state = response.json
        self.assertEqual(str(state["jugador_actual_id"]), second)
        self.assertEqual(state["avatares_sala"], {first: "avatar_3", second: "personalizado-" + second})
        self.assertEqual(state["avatares_sala"], {
            str(p["user_id"]): p["avatar_id"] for p in state["game"]["players"]
        })
        self.assertNotIn(custom["valor"], response.get_data(as_text=True))
        self.assertEqual(self.client_one.get("/api/game/avatar", query_string={"id": second}, headers=one).json["avatar"], custom)

    def test_profile_includes_the_saved_avatar_selection(self):
        headers = self._headers("token-one")
        elegido = {"tipo": "predeterminado", "valor": "avatar_3"}
        self.assertEqual(
            self.client_one.put("/api/game/avatar", json=elegido, headers=headers).status_code,
            200,
        )
        perfil = self.client_one.get("/api/profile", headers=headers).json["user"]
        self.assertEqual(perfil["avatar_selection"], elegido)
        self.assertEqual(perfil["avatar"], "avatar_3")

        personalizado = {"tipo": "personalizado", "valor": "contenido-png-del-jugador"}
        self.assertEqual(
            self.client_one.put(
                "/api/game/avatar", json=personalizado, headers=headers
            ).status_code,
            200,
        )
        perfil = self.client_one.get("/api/profile", headers=headers).json["user"]
        self.assertEqual(perfil["avatar_selection"], personalizado)
        self.assertEqual(perfil["avatar"], "Personalizado")

    def test_google_crea_perfiles_distintos_y_conserva_el_nombre_al_reingresar(self):
        for uid in ("google-uno", "google-dos"):
            with self.subTest(uid=uid):
                claims = {
                    "uid": uid, "email": f"{uid}@example.test", "email_verified": True,
                    "name": "A@lex", "firebase": {"sign_in_provider": "google.com"},
                }
                self.identities[uid] = claims
                headers = self._headers(uid)
                respuesta = self.client_one.post("/api/profile", json={}, headers=headers)
                nombre = "Alex-" + hashlib.sha256(uid.encode()).hexdigest()[:12]
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.json["user"]["name"], nombre)
                claims["name"] = "Otro nombre"
                repetida = self.client_one.post("/api/profile", json={}, headers=headers)
                self.assertEqual(repetida.json["user"]["name"], nombre)

    def test_solo_google_verificado_puede_crear_un_perfil_sin_indicar_nombre(self):
        claims = {
            "uid": "nueva-cuenta", "email": "nuevo@example.test",
            "firebase": {"sign_in_provider": "google.com"}, "email_verified": False,
        }
        self.identities["nueva-cuenta"] = claims
        headers = self._headers("nueva-cuenta")
        self.assertEqual(self.client_one.post("/api/profile", json={}, headers=headers).status_code, 403)
        claims.update(email_verified=True, firebase={"sign_in_provider": "password"})
        self.assertEqual(self.client_one.post("/api/profile", json={}, headers=headers).status_code, 403)
        self.assertEqual(self.client_one.get("/api/profile", headers=headers).status_code, 404)
        registrada = self.client_one.post("/api/profile", json={"name": "Jugador"}, headers=headers)
        self.assertEqual(registrada.json["user"]["name"], "Jugador")
        claims["firebase"] = {"sign_in_provider": "google.com"}
        vinculada = self.client_one.post("/api/profile", json={}, headers=headers)
        self.assertEqual(vinculada.json["user"]["name"], "Jugador")

    def _preparar_partida_reactor(self, target_score=20, tokens=("token-one", "token-two")):
        clients = (self.client_one, self.client_two, self.client_three)
        for index, (client, token) in enumerate(zip(clients, tokens), start=1):
            self.assertEqual(
                client.put(
                    "/api/game/avatar",
                    json={"tipo": "predeterminado", "valor": f"avatar_{index}"},
                    headers=self._headers(token),
                ).status_code,
                200,
            )
            self.assertEqual(
                client.post("/api/game/join", headers=self._headers(token)).status_code,
                200,
            )

        config = {
            "modo_fin": "puntos",
            "minutos_fin": 1,
            "puntos_fin": target_score,
            "segundos_congelacion": 3,
        }
        self.assertEqual(
            self.client_one.put(
                "/api/game/config",
                json=config,
                headers=self._headers(tokens[0]),
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client_one.post(
                "/api/game/start", headers=self._headers(tokens[0])
            ).status_code,
            200,
        )

    def _poner_junto_al_reactor(self, token):
        player_id = servidor._player_id(self.identities[token])
        jugador = servidor._GAME_ARENA._players[player_id]
        posiciones = {
            "token-one": (8.0, 6.0),
            "token-two": (12.0, 6.0),
            "token-three": (8.0, 8.0),
        }
        jugador.x, jugador.y = posiciones[token]
        return player_id

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

        for trampa in servidor._GAME_OBSTACULOS.trampas:
            if (trampa.x, trampa.y) == (2, 1):
                trampa.activa = False
        movement = self.client_one.post(
            "/api/game/move", json={"direction": "right"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(movement.status_code, 200)
        self.assertTrue(movement.json["ok"])
        self.assertEqual(movement.json["state"]["players"][0]["score"], 0)

        winner_id = self._poner_junto_al_reactor("token-one")
        first = self.client_one.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "extract-1"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(first.status_code, 200)
        duplicate = self.client_one.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "extract-1"},
            headers=self._headers("token-one"),
        )
        self.assertTrue(duplicate.json["duplicate"])

        servidor._REACTOR["active"]["started_at"] -= 1.6
        after_first_extraction = self.client_two.get(
            "/api/game/state", headers=self._headers("token-two")
        ).json["game"]
        self.assertEqual(after_first_extraction["scores"][winner_id], 1)
        self.assertEqual(after_first_extraction["reactor"]["status"], "recargando")

        cooldown = self.client_two.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "extract-too-soon"},
            headers=self._headers("token-two"),
        )
        self.assertEqual(cooldown.status_code, 400)

        servidor._REACTOR["available_at"] = time.monotonic() - 0.1
        second = self.client_one.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "extract-2"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(second.status_code, 200)
        servidor._REACTOR["active"]["started_at"] -= 1.6
        result = self.client_one.get(
            "/api/game/state", headers=self._headers("token-one")
        ).json["game"]
        self.assertEqual(result["status"], "finished")
        self.assertTrue(result["results_persisted"])

        shared = self.client_two.get(
            "/api/game/state", headers=self._headers("token-two")
        ).json["game"]
        self.assertEqual(shared["status"], "finished")
        self.assertEqual(shared["winner_id"], winner_id)
        self.assertEqual(shared["scores"][shared["winner_id"]], 2)
        self.assertEqual(len(shared["players"]), 2)
        expected_user_id = int.from_bytes(hashlib.sha256(b"user-one").digest()[:4], "big") & 0x7fffffff
        self.assertEqual(shared["players"][0]["user_id"], expected_user_id)

    def test_trap_on_movement_tile_prevents_reactor_extraction(self):
        self._preparar_partida_reactor()
        trampa = servidor._GAME_OBSTACULOS.trampas[0]
        trampa.x, trampa.y = 2, 1
        movement = self.client_one.post(
            "/api/game/move", json={"direction": "right"},
            headers=self._headers("token-one"),
        )
        self.assertTrue(movement.json["ok"])
        self.assertEqual(movement.json["state"]["players"][0]["estado_temporal"], "inmovilizado")

        self._poner_junto_al_reactor("token-one")
        response = self.client_one.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "trapped"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("inmovilizado", response.json["error"])

    def test_reactor_rejects_out_of_zone_busy_and_cooldown_interactions(self):
        self._preparar_partida_reactor()
        too_far = self.client_one.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "too-far"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(too_far.status_code, 400)

        player_one = self._poner_junto_al_reactor("token-one")
        player_two = self._poner_junto_al_reactor("token-two")
        first = self.client_one.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "first"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(first.status_code, 200)

        busy = self.client_two.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "second"},
            headers=self._headers("token-two"),
        )
        self.assertEqual(busy.status_code, 400)
        self.assertIn("Otro jugador", busy.json["error"])

        servidor._REACTOR["active"]["started_at"] -= 1.6
        state = self.client_two.get(
            "/api/game/state", headers=self._headers("token-two")
        ).json["game"]
        self.assertEqual(state["scores"][player_one], 1)
        self.assertEqual(state["scores"][player_two], 0)

        cooldown = self.client_two.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "third"},
            headers=self._headers("token-two"),
        )
        self.assertEqual(cooldown.status_code, 400)
        self.assertIn("recargando", cooldown.json["error"])

    def test_release_cancels_before_1_5_seconds_but_scores_afterwards(self):
        self._preparar_partida_reactor()
        player_id = self._poner_junto_al_reactor("token-one")

        started = self.client_one.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "cancel"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(started.status_code, 200)
        stopped = self.client_one.post(
            "/api/game/reactor",
            json={"action": "stop", "event_id": "cancel"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(stopped.json["state"]["scores"][player_id], 0)

        servidor._REACTOR["available_at"] = time.monotonic() - 0.1
        started = self.client_one.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "complete"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(started.status_code, 200)
        servidor._REACTOR["active"]["started_at"] -= 1.6

        stopped = self.client_one.post(
            "/api/game/reactor",
            json={"action": "stop", "event_id": "complete"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(stopped.json["state"]["scores"][player_id], 1)

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
        self._poner_junto_al_reactor("token-one")
        started = self.client_one.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "persist-result"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(started.status_code, 200)
        servidor._REACTOR["active"]["started_at"] -= 1.6
        final = self.client_one.get(
            "/api/game/state", headers=self._headers("token-one")
        )
        self.assertEqual(final.status_code, 200)
        self.assertEqual(final.json["game"]["status"], "finished")

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

        with closing(servidor.repo._con()) as con:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM partidas").fetchone()[0],
                2,
            )

    def test_finished_players_leave_independently_and_the_room_becomes_available(self):
        self._preparar_partida_reactor(target_score=1)
        uno, dos = self._headers("token-one"), self._headers("token-two")
        ganador = servidor._player_id(self.identities["token-one"])
        servidor._GAME_ARENA.scoreboard.award_extraction(ganador)
        juego = self.client_one.get("/api/game/state", headers=uno).json["game"]
        partida = {"partida": juego["match_id"]}
        self.assertEqual(self.client_one.post("/api/game/leave", query_string=partida, headers=uno).status_code, 200)
        final = self.client_two.get("/api/game/state", headers=dos).json["game"]
        self.assertEqual(final["scores"], juego["scores"])
        self.assertEqual({j["player_id"] for j in final["players"] if not j["connected"]}, {ganador})
        self.assertEqual(self.client_two.post("/api/game/leave", query_string=partida, headers=dos).status_code, 200)
        sala = self.client_one.get("/api/game/state", headers=uno).json
        self.assertIsNone(sala["game"])
        self.assertEqual(sala["partida"]["jugadores"], [])
        self.assertNotIn("resultado_anterior", sala)

    def test_late_participant_can_get_previous_podium_after_next_lobby_opens(self):
        self._preparar_partida_reactor(target_score=1, tokens=("token-one", "token-three", "token-two"))
        uno, dos, ajeno = (self._headers(t) for t in ("token-one", "token-two", "token-four"))
        anterior = servidor._GAME_ARENA.match_id
        servidor._GAME_ARENA.scoreboard.award_extraction(servidor._player_id(self.identities["token-one"]))
        # El escritorio vuelve a unirse antes de que el móvil haya recibido el último sondeo.
        self.assertEqual(self.client_one.post("/api/game/join", headers=uno).status_code, 200)
        query = {"resultado_de": anterior}
        sala = self.client_two.get("/api/game/state", query_string=query, headers=dos).json
        self.assertIsNone(sala["game"])
        podio = sala["resultado_anterior"]
        self.assertEqual(podio["match_id"], anterior)
        self.assertTrue(podio["results_persisted"])
        self.assertEqual([(j["position"], j["username"], j["score"]) for j in podio["players"]],
                         [(1, "JugadorUno", 1), (2, "JugadorDos", 0), (3, "JugadorTres", 0)])
        self.assertEqual(podio["winner_id"], podio["players"][0]["player_id"])
        self.assertEqual(podio["players"][0]["personal_record"], 1)
        self.assertTrue(podio["players"][0]["new_record"])
        self.assertNotIn("resultado_anterior", self.client_four.get("/api/game/state", query_string=query, headers=ajeno).json)
        self.assertEqual(self.client_four.get("/api/game/state", query_string=query).status_code, 401)
        self.assertEqual(self.client_two.post("/api/game/join", headers=dos).status_code, 200)
        self.assertEqual(self.client_one.post("/api/game/start", headers=uno).status_code, 200)
        self.assertEqual(self.client_two.post("/api/game/leave", query_string={"partida": anterior}, headers=dos).status_code, 200)
        nueva = self.client_two.get("/api/game/state", query_string=query, headers=dos).json
        self.assertNotEqual(nueva["game"]["match_id"], anterior)
        self.assertTrue(all(j["connected"] for j in nueva["game"]["players"]))
        self.assertEqual(nueva["resultado_anterior"], podio)

    def test_three_players_receive_consolidated_podium_data_and_personal_records(self):
        clients = (
            (self.client_one, "token-one", "avatar_1"),
            (self.client_two, "token-two", "avatar_2"),
            (self.client_three, "token-three", "avatar_3"),
        )
        for client, token, avatar in clients:
            self.assertEqual(
                client.put(
                    "/api/game/avatar",
                    json={"tipo": "predeterminado", "valor": avatar},
                    headers=self._headers(token),
                ).status_code,
                200,
            )
            self.assertEqual(
                client.post("/api/game/join", headers=self._headers(token)).status_code,
                200,
            )
        self.assertEqual(
            self.client_four.post(
                "/api/game/join", headers=self._headers("token-four")
            ).status_code,
            400,
        )

        config = {
            "modo_fin": "puntos",
            "minutos_fin": 1,
            "puntos_fin": 1,
            "segundos_congelacion": 3,
        }
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
        self._poner_junto_al_reactor("token-one")
        response = self.client_one.post(
            "/api/game/reactor",
            json={"action": "start", "event_id": "three-player-result"},
            headers=self._headers("token-one"),
        )
        self.assertEqual(response.status_code, 200)
        servidor._REACTOR["active"]["started_at"] -= 1.6
        result = self.client_two.get(
            "/api/game/state", headers=self._headers("token-two")
        ).json["game"]
        self.assertEqual(result["status"], "finished")
        self.assertTrue(result["results_persisted"])
        self.assertEqual(len(result["players"]), 3)
        self.assertEqual(
            result["duration_seconds"],
            int(result["elapsed_seconds"]),
        )
        records = {
            player["username"]: (
                player["score"],
                player["new_record"],
                player["personal_record"],
            )
            for player in result["players"]
        }
        self.assertEqual(
            records,
            {
                "JugadorUno": (1, True, 1),
                "JugadorDos": (0, False, 0),
                "JugadorTres": (0, False, 0),
            },
        )
        for client, token, _avatar in clients:
            shared = client.get(
                "/api/game/state", headers=self._headers(token)
            ).json["game"]
            self.assertEqual(shared["match_id"], result["match_id"])
            self.assertEqual(shared["scores"], result["scores"])
            self.assertEqual(shared["players"], result["players"])
            self.assertEqual(
                shared["reactor"]["status"],
                result["reactor"]["status"],
            )

        profile = self.client_three.get(
            "/api/profile", headers=self._headers("token-three")
        ).json["user"]
        self.assertEqual(
            profile["match_history"][0]["opponent"],
            "JugadorDos, JugadorUno",
        )
        self.assertFalse(profile["match_history"][0]["new_record"])

        with closing(servidor.repo._con()) as con:
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM partidas WHERE match_id = ?",
                    (result["match_id"],),
                ).fetchone()[0],
                3,
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
    def test_only_room_creator_can_change_configuration(self):
        self.assertEqual(
            self.client_one.post(
                "/api/game/join",
                headers=self._headers("token-one"),
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client_two.post(
                "/api/game/join",
                headers=self._headers("token-two"),
            ).status_code,
            200,
        )

        config_creador = {
            "modo_fin": "tiempo",
            "minutos_fin": 4,
            "puntos_fin": 20,
            "segundos_congelacion": 3,
        }
        respuesta_creador = self.client_one.put(
            "/api/game/config",
            json=config_creador,
            headers=self._headers("token-one"),
        )
        self.assertEqual(respuesta_creador.status_code, 200)

        config_no_autorizada = {
            "modo_fin": "tiempo",
            "minutos_fin": 10,
            "puntos_fin": 20,
            "segundos_congelacion": 3,
        }
        respuesta_otro = self.client_two.put(
            "/api/game/config",
            json=config_no_autorizada,
            headers=self._headers("token-two"),
        )
        self.assertEqual(respuesta_otro.status_code, 403)

        estado = self.client_two.get(
            "/api/game/state",
            headers=self._headers("token-two"),
        )
        self.assertEqual(
            estado.json["partida"]["configuracion"]["minutos_fin"],
            4,
        )


if __name__ == "__main__":
    unittest.main()

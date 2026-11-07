import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.repository import SQLiteRepository


class SQLiteRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "game.db"
        self.repo = SQLiteRepository(self.db_path)
        self.repo.crear("uid-one", "JugadorUno", "one@example.test")
        self.repo.crear("uid-two", "JugadorDos", "two@example.test")

    def tearDown(self):
        self.temp.cleanup()

    def test_saves_match_once_and_updates_ranking_and_profiles(self):
        participants = [
            {"uid": "uid-one", "score": 8, "result": "victoria"},
            {"uid": "uid-two", "score": 5, "result": "derrota"},
        ]
        self.assertTrue(self.repo.registrar_resultado_partida(
            "match-one", participants, "2026-11-07T10:00:00+00:00", 120
        ))
        self.assertFalse(self.repo.registrar_resultado_partida(
            "match-one", participants, "2026-11-07T10:00:00+00:00", 120
        ))

        ranking = self.repo.obtener_ranking()
        self.assertEqual(
            ranking,
            [
                {"position": 1, "name": "JugadorUno", "points": 8, "wins": 1},
                {"position": 2, "name": "JugadorDos", "points": 5, "wins": 0},
            ],
        )
        profile = self.repo.obtener("uid-one", True).to_dict()
        self.assertEqual(profile["record"], 8)
        self.assertEqual(profile["ranking"], 1)
        self.assertEqual(profile["statistics"]["points_accumulated"], 8)
        self.assertEqual(profile["match_history"][0]["opponent"], "JugadorDos")
        self.assertEqual(profile["match_history"][0]["duration_seconds"], 120)

    def test_ranking_ties_use_victories_then_username(self):
        matches = [
            ("m1", [
                {"uid": "uid-one", "score": 10, "result": "victoria"},
                {"uid": "uid-two", "score": 10, "result": "derrota"},
            ]),
            ("m2", [
                {"uid": "uid-one", "score": 2, "result": "victoria"},
                {"uid": "uid-two", "score": 2, "result": "derrota"},
            ]),
        ]
        for match_id, participants in matches:
            self.repo.registrar_resultado_partida(match_id, participants)
        self.assertEqual(
            [row["name"] for row in self.repo.obtener_ranking()],
            ["JugadorUno", "JugadorDos"],
        )

    def test_migrates_existing_partidas_table_without_losing_rows(self):
        legacy_path = Path(self.temp.name) / "legacy.db"
        with sqlite3.connect(legacy_path) as con:
            con.executescript(
                """
                CREATE TABLE jugadores (
                    uid TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    correo TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    avatar TEXT,
                    record INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE partidas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT NOT NULL REFERENCES jugadores(uid),
                    fecha TEXT NOT NULL,
                    puntaje INTEGER NOT NULL,
                    resultado TEXT NOT NULL
                );
                CREATE TABLE logros (
                    uid TEXT NOT NULL REFERENCES jugadores(uid),
                    titulo TEXT NOT NULL,
                    PRIMARY KEY (uid, titulo)
                );
                INSERT INTO jugadores VALUES
                    ('uid-old', 'JugadorAntiguo', 'old@example.test', NULL, 7);
                INSERT INTO partidas (uid, fecha, puntaje, resultado) VALUES
                    ('uid-old', '2026-11-06T10:00:00+00:00', 7, 'victoria');
                """
            )

        migrated = SQLiteRepository(legacy_path)
        profile = migrated.obtener("uid-old", True).to_dict()
        self.assertEqual(profile["record"], 7)
        self.assertEqual(profile["match_history"][0]["score"], 7)
        self.assertIsNone(profile["match_history"][0]["match_id"])
        self.assertEqual(profile["match_history"][0]["duration_seconds"], 0)
        self.assertEqual(
            migrated.obtener_ranking(),
            [{"position": 1, "name": "JugadorAntiguo", "points": 7, "wins": 1}],
        )


if __name__ == "__main__":
    unittest.main()

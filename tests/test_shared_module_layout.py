from enum import Enum
from pathlib import Path
import unittest

from shared import data
from shared.domain import (
    ARENA_PREDETERMINADA,
    AVATARES_PREDETERMINADOS,
    CASILLAS_TRANSITABLES,
    AvatarPredeterminado,
    Casilla,
    ErrorApp,
    MapaArena,
    ServicioAvatar,
    ServicioPartida,
)
from shared.game.arena import MultiplayerArena
from frontend.repositories import RepositorioPartidaServidor


class DomainModuleLayoutTests(unittest.TestCase):
    def test_data_contracts_are_grouped_in_the_shared_data_module(self):
        names = (
            "ConfiguracionPartida",
            "EleccionAvatar",
            "Jugador",
            "Partida",
            "RepositorioAvatares",
            "RepositorioPartida",
            "RepositorioPartidaOnline",
        )

        for name in names:
            with self.subTest(name=name):
                self.assertTrue(hasattr(data, name))

    def test_domain_and_game_modules_are_available_from_shared_package(self):
        self.assertTrue(issubclass(Casilla, Enum))
        self.assertIsInstance(ARENA_PREDETERMINADA, MapaArena)
        self.assertIsInstance(AVATARES_PREDETERMINADOS[0], AvatarPredeterminado)
        self.assertTrue(CASILLAS_TRANSITABLES)
        self.assertTrue(issubclass(ErrorApp, Exception))
        self.assertTrue(callable(ServicioAvatar))
        self.assertTrue(callable(ServicioPartida))
        self.assertTrue(callable(MultiplayerArena))

    def test_server_repository_implements_the_online_repository_contract(self):
        self.assertIsInstance(
            RepositorioPartidaServidor(),
            data.RepositorioPartidaOnline,
        )

    def test_local_json_files_keep_the_project_root_as_their_default_location(self):
        project_root = Path(__file__).resolve().parents[1]
        repositories = (
            data.RepositorioAvataresJson(),
            data.RepositorioPartidaJson(),
        )

        for repository in repositories:
            with self.subTest(repository=type(repository).__name__):
                self.assertEqual(Path(repository._archivo._ruta).parent, project_root)


if __name__ == "__main__":
    unittest.main()

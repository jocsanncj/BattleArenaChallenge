import sqlite3
from contextlib import closing
from backend.jugador import Jugador

class RepositoryError(RuntimeError): ...
class UserNotFound(RepositoryError): ...
class DuplicateUsername(RepositoryError): ...
class DuplicateEmail(RepositoryError): ...

ESQUEMA = """
CREATE TABLE IF NOT EXISTS jugadores (
    uid TEXT PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE COLLATE NOCASE,
    correo TEXT NOT NULL UNIQUE COLLATE NOCASE,
    avatar TEXT,
    record INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS partidas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL REFERENCES jugadores(uid),
    fecha TEXT NOT NULL,
    puntaje INTEGER NOT NULL,
    resultado TEXT NOT NULL CHECK (resultado IN ('victoria','derrota','empate'))
);
CREATE TABLE IF NOT EXISTS logros (
    uid TEXT NOT NULL REFERENCES jugadores(uid),
    titulo TEXT NOT NULL,
    PRIMARY KEY (uid, titulo)
);
"""

class SQLiteRepository:
    def __init__(self, ruta):
        self.ruta = ruta
        with closing(self._con()) as con:
            con.executescript(ESQUEMA)
    def _con(self):
        con = sqlite3.connect(self.ruta)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con
    def nombre_disponible(self, nombre):
        with closing(self._con()) as con:
            return con.execute("SELECT 1 FROM jugadores WHERE nombre = ?",
                            (nombre,)).fetchone() is None
    def correo_de(self, nombre):  # para login por usuario
        with closing(self._con()) as con:
            f = con.execute("SELECT correo FROM jugadores WHERE nombre = ?",
                            (nombre,)).fetchone()
            return f["correo"] if f else None
    def crear(self, uid, nombre, correo):
        try:
            with closing(self._con()) as con, con:
                con.execute(
                    "INSERT INTO jugadores (uid, nombre, correo) VALUES (?,?,?) "
                    "ON CONFLICT(uid) DO UPDATE SET correo = excluded.correo",
                    (uid, nombre, correo))
        except sqlite3.IntegrityError as e:
            if "nombre" in str(e):
                raise DuplicateUsername("Ese nombre de usuario ya está en uso.") from e
            raise DuplicateEmail("Ese correo ya está registrado.") from e
    def obtener(self, uid, correo_verificado):
        with closing(self._con()) as con:
            j = con.execute("SELECT * FROM jugadores WHERE uid = ?", (uid,)).fetchone()
            if j is None:
                raise UserNotFound("No existe el perfil del jugador.")
            partidas = [dict(p) for p in con.execute(
                "SELECT fecha, puntaje, resultado FROM partidas "
                "WHERE uid = ? ORDER BY fecha DESC", (uid,))]
            logros = [r["titulo"] for r in con.execute(
                "SELECT titulo FROM logros WHERE uid = ?", (uid,))]
            ranking = (con.execute("SELECT COUNT(*) + 1 FROM jugadores WHERE record > ?",
                                (j["record"],)).fetchone()[0] if j["record"] else None)
        return Jugador(uid, j["nombre"], j["correo"], correo_verificado,
                    j["avatar"], j["record"], ranking, partidas, logros)
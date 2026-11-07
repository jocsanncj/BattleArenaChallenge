from datetime import datetime, timezone
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
    resultado TEXT NOT NULL CHECK (resultado IN ('victoria','derrota','empate')),
    match_id TEXT,
    duracion_segundos INTEGER NOT NULL DEFAULT 0,
    UNIQUE (match_id, uid)
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
            columnas = {
                fila["name"] for fila in con.execute("PRAGMA table_info(partidas)")
            }
            if "match_id" not in columnas:
                con.execute("ALTER TABLE partidas ADD COLUMN match_id TEXT")
            if "duracion_segundos" not in columnas:
                con.execute(
                    "ALTER TABLE partidas "
                    "ADD COLUMN duracion_segundos INTEGER NOT NULL DEFAULT 0"
                )
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_partidas_match_uid "
                "ON partidas(match_id, uid) WHERE match_id IS NOT NULL"
            )
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
    def registrar_resultado_partida(
        self,
        match_id,
        participantes,
        fecha=None,
        duracion_segundos=0,
    ):
        """Guarda el resultado final una sola vez y actualiza los récords personales.
        Cada participante es un diccionario con ``uid``, ``score`` y ``result``.
        Devuelve False si esta partida ya había sido registrada.
        """
        if not isinstance(match_id, str) or not match_id.strip():
            raise ValueError("La partida necesita un identificador válido.")
        match_id = match_id.strip()
        if not isinstance(participantes, list) or len(participantes) != 2:
            raise ValueError("El resultado debe incluir exactamente dos participantes.")
        if type(duracion_segundos) is not int or duracion_segundos < 0:
            raise ValueError("La duración debe ser un entero no negativo.")
        if fecha is None:
            fecha = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not isinstance(fecha, str) or not fecha.strip():
            raise ValueError("La fecha de la partida no es válida.")
        filas = []
        for participante in participantes:
            if not isinstance(participante, dict):
                raise ValueError("Los datos de cada participante no son válidos.")
            uid = participante.get("uid")
            puntaje = participante.get("score")
            resultado = participante.get("result")
            if not isinstance(uid, str) or not uid:
                raise ValueError("Cada participante debe tener un UID válido.")
            if type(puntaje) is not int or puntaje < 0:
                raise ValueError("Cada puntaje debe ser un entero no negativo.")
            if resultado not in {"victoria", "derrota", "empate"}:
                raise ValueError("El resultado de cada participante no es válido.")
            filas.append((uid, puntaje, resultado))
        uids = [fila[0] for fila in filas]
        if len(set(uids)) != len(uids):
            raise ValueError("La partida no puede incluir dos veces al mismo jugador.")
        resultados = sorted(fila[2] for fila in filas)
        if resultados not in (["derrota", "victoria"], ["empate", "empate"]):
            raise ValueError("Los resultados de ambos participantes no coinciden.")
        try:
            with closing(self._con()) as con, con:
                con.execute("BEGIN IMMEDIATE")
                registrados = con.execute(
                    "SELECT uid FROM partidas WHERE match_id = ?",
                    (match_id,),
                ).fetchall()
                if registrados:
                    uids_registrados = {fila["uid"] for fila in registrados}
                    if uids_registrados != set(uids):
                        raise RepositoryError(
                            "La partida ya existe con participantes diferentes."
                        )
                    return False
                existentes = {
                    fila["uid"]
                    for fila in con.execute(
                        "SELECT uid FROM jugadores WHERE uid IN (?, ?)",
                        uids,
                    )
                }
                if existentes != set(uids):
                    raise UserNotFound(
                        "No se puede guardar la partida: falta el perfil de un jugador."
                    )
                con.executemany(
                    "INSERT INTO partidas "
                    "(uid, fecha, puntaje, resultado, match_id, duracion_segundos) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (uid, fecha, puntaje, resultado, match_id, duracion_segundos)
                        for uid, puntaje, resultado in filas
                    ],
                )
                con.executemany(
                    "UPDATE jugadores SET record = MAX(record, ?) WHERE uid = ?",
                    [(puntaje, uid) for uid, puntaje, _ in filas],
                )
        except sqlite3.IntegrityError as error:
            raise RepositoryError(
                "No se pudo guardar el resultado de la partida."
            ) from error
        return True
    def _consultar_ranking(self):
        with closing(self._con()) as con:
            filas = con.execute(
                """
                SELECT j.uid, j.nombre,
                       SUM(p.puntaje) AS puntos,
                       SUM(CASE WHEN p.resultado = 'victoria' THEN 1 ELSE 0 END) AS victorias
                FROM jugadores AS j
                JOIN partidas AS p ON p.uid = j.uid
                GROUP BY j.uid, j.nombre
                ORDER BY puntos DESC, victorias DESC, j.nombre COLLATE NOCASE ASC
                """
            ).fetchall()
        return [
            {
                "position": posicion,
                "name": fila["nombre"],
                "points": fila["puntos"],
                "wins": fila["victorias"],
                "uid": fila["uid"],
            }
            for posicion, fila in enumerate(filas, start=1)
        ]
    def obtener_ranking(self):
        """Devuelve el ranking por puntos acumulados, victorias y nombre."""
        return [
            {clave: valor for clave, valor in fila.items() if clave != "uid"}
            for fila in self._consultar_ranking()
        ]
    def obtener(self, uid, correo_verificado):
        with closing(self._con()) as con:
            j = con.execute("SELECT * FROM jugadores WHERE uid = ?", (uid,)).fetchone()
            if j is None:
                raise UserNotFound("No existe el perfil del jugador.")
            partidas = [dict(p) for p in con.execute(
                """
                SELECT p.fecha AS played_at, p.puntaje AS score,
                        p.resultado AS result, p.match_id,
                        p.duracion_segundos AS duration_seconds,
                        (
                            SELECT o.nombre
                            FROM partidas AS op
                            JOIN jugadores AS o ON o.uid = op.uid
                            WHERE op.match_id = p.match_id AND op.uid != p.uid
                            LIMIT 1
                        ) AS opponent
                FROM partidas AS p
                WHERE p.uid = ?
                ORDER BY p.fecha DESC, p.id DESC
                """,
                (uid,),
            )]
            logros = [r["titulo"] for r in con.execute(
                "SELECT titulo FROM logros WHERE uid = ?", (uid,))]
            ranking = next(
                (
                    fila["position"]
                    for fila in self._consultar_ranking()
                    if fila["uid"] == uid
                ),
                None,
            )
        return Jugador(uid, j["nombre"], j["correo"], correo_verificado,
                    j["avatar"], j["record"], ranking, partidas, logros)
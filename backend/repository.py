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
    nuevo_record INTEGER NOT NULL DEFAULT 0,
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
            if "nuevo_record" not in columnas:
                con.execute(
                    "ALTER TABLE partidas "
                    "ADD COLUMN nuevo_record INTEGER NOT NULL DEFAULT 0"
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
        if not isinstance(participantes, list) or not 2 <= len(participantes) <= 3:
            raise ValueError("El resultado debe incluir entre dos y tres participantes.")
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
        resultados = [fila[2] for fila in filas]
        hay_un_ganador = (
            resultados.count("victoria") == 1
            and resultados.count("derrota") == len(filas) - 1
        )
        todos_empataron = all(resultado == "empate" for resultado in resultados)
        if not (hay_un_ganador or todos_empataron):
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
                placeholders = ", ".join("?" for _ in uids)
                existentes = {
                    fila["uid"]
                    for fila in con.execute(
                        f"SELECT uid FROM jugadores WHERE uid IN ({placeholders})",
                        uids,
                    )
                }
                if existentes != set(uids):
                    raise UserNotFound(
                        "No se puede guardar la partida: falta el perfil de un jugador."
                    )
                records_actuales = {
                    fila["uid"]: fila["record"]
                    for fila in con.execute(
                        f"SELECT uid, record FROM jugadores WHERE uid IN ({placeholders})",
                        uids,
                    )
                }
                con.executemany(
                    "INSERT INTO partidas "
                    "(uid, fecha, puntaje, resultado, match_id, duracion_segundos, nuevo_record) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            uid,
                            fecha,
                            puntaje,
                            resultado,
                            match_id,
                            duracion_segundos,
                            int(puntaje > records_actuales[uid]),
                        )
                        for uid, puntaje, resultado in filas
                    ],
                )
                con.executemany(
                    "UPDATE jugadores SET record = MAX(record, ?) WHERE uid = ?",
                    [(puntaje, uid) for uid, puntaje, _ in filas],
                )
                for uid, _, _ in filas: #Logros del juego
                    estadisticas = con.execute(
                        """
                        SELECT COUNT(*) AS partidas,
                            COALESCE(SUM(puntaje), 0) AS puntos,
                            SUM(CASE WHEN resultado = 'victoria'
                                THEN 1 ELSE 0 END) AS victorias
                        FROM partidas
                        WHERE uid = ?
                        """,
                        (uid,),
                    ).fetchone()
                    logros = []
                    if estadisticas["partidas"] >= 1:
                        logros.append("Primera partida")
                    if estadisticas["victorias"] >= 1:
                        logros.append("Primera victoria")
                    if estadisticas["partidas"] >= 10:
                        logros.append("Competidor")
                    if estadisticas["puntos"] >= 100:
                        logros.append("Acumulador de energía")
                    con.executemany(
                        """
                        INSERT INTO logros (uid, titulo) VALUES (?, ?)
                        ON CONFLICT(uid, titulo) DO NOTHING
                        """,
                        [(uid, titulo) for titulo in logros],
                    )
        except sqlite3.IntegrityError as error:
            raise RepositoryError(
                "No se pudo guardar el resultado de la partida."
            ) from error
        return True

    def obtener_marcas_partida(self, match_id):
        """Devuelve el récord personal consolidado para cada participante de una partida."""
        with closing(self._con()) as con:
            filas = con.execute(
                """
                SELECT p.uid, p.nuevo_record, j.record
                FROM partidas AS p
                JOIN jugadores AS j ON j.uid = p.uid
                WHERE p.match_id = ?
                """,
                (match_id,),
            ).fetchall()
        return {
            fila["uid"]: {
                "new_record": bool(fila["nuevo_record"]),
                "personal_record": fila["record"],
            }
            for fila in filas
        }

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
                        p.nuevo_record AS new_record,
                        (
                            SELECT group_concat(opponent.nombre, ', ')
                            FROM (
                                SELECT o.nombre
                                FROM partidas AS op
                                JOIN jugadores AS o ON o.uid = op.uid
                                WHERE op.match_id = p.match_id AND op.uid != p.uid
                                ORDER BY o.nombre COLLATE NOCASE
                            ) AS opponent
                        ) AS opponent
                FROM partidas AS p
                WHERE p.uid = ?
                ORDER BY p.fecha DESC, p.id DESC
                """,
                (uid,),
            )]
            for partida in partidas:
                partida["new_record"] = bool(partida["new_record"])
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
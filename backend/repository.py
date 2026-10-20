import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from backend.models import PlayerProfile


class RepositoryError(RuntimeError):
    pass


class DuplicateUsername(RepositoryError):
    pass


class DuplicateEmail(RepositoryError):
    pass


class UserNotFound(RepositoryError):
    pass


class SQLiteRepository:
    def __init__(self, data_directory: Path, legacy_users_file: Path | None = None):
        self.data_directory = data_directory
        self.legacy_users_file = legacy_users_file

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        self.data_directory.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.data_directory / "usuarios.sqlite3", timeout=10
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS usuarios (
                    nombre TEXT PRIMARY KEY COLLATE NOCASE,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    salt TEXT NOT NULL,
                    hash_password TEXT NOT NULL,
                    verificado INTEGER NOT NULL DEFAULT 0,
                    record INTEGER NOT NULL DEFAULT 0,
                    avatar TEXT
                );
                CREATE TABLE IF NOT EXISTS logros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre_usuario TEXT NOT NULL REFERENCES usuarios(nombre)
                        ON DELETE CASCADE,
                    titulo TEXT NOT NULL,
                    UNIQUE(nombre_usuario, titulo)
                );
                CREATE TABLE IF NOT EXISTS historial_partidas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre_usuario TEXT NOT NULL REFERENCES usuarios(nombre)
                        ON DELETE CASCADE,
                    oponente TEXT NOT NULL,
                    resultado TEXT NOT NULL CHECK (
                        resultado IN ('victoria', 'derrota', 'empate')
                    ),
                    puntuacion INTEGER NOT NULL DEFAULT 0,
                    fecha TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS enlaces (
                    hash_token TEXT PRIMARY KEY,
                    nombre_usuario TEXT NOT NULL REFERENCES usuarios(nombre)
                        ON DELETE CASCADE,
                    proposito TEXT NOT NULL CHECK (
                        proposito IN ('verificacion', 'recuperacion')
                    ),
                    expira_en TEXT NOT NULL
                );
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(usuarios)")
            }
            if "avatar" not in columns:
                connection.execute("ALTER TABLE usuarios ADD COLUMN avatar TEXT")
            if self.legacy_users_file is not None:
                self._import_legacy_users(connection)

    def _import_legacy_users(self, connection: sqlite3.Connection) -> None:
        try:
            with self.legacy_users_file.open("r", encoding="utf-8") as legacy_file:
                data = json.load(legacy_file)
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError) as error:
            raise RepositoryError(
                f"No se pudo leer el archivo de usuarios anterior: {error}"
            ) from error

        if not isinstance(data, dict) or not isinstance(data.get("usuarios"), dict):
            raise RepositoryError("DatosUser.json tiene un formato inválido.")

        for name, user in data["usuarios"].items():
            if not isinstance(name, str) or not isinstance(user, dict):
                continue
            email = user.get("email")
            salt = user.get("salt")
            password_hash = user.get("hash_password")
            if not all(
                isinstance(value, str) and value
                for value in (email, salt, password_hash)
            ):
                continue
            try:
                bytes.fromhex(salt)
                bytes.fromhex(password_hash)
            except ValueError:
                continue
            record = user.get("record", 0)
            if not isinstance(record, int) or isinstance(record, bool):
                record = 0
            connection.execute(
                """
                INSERT OR IGNORE INTO usuarios
                    (nombre, email, salt, hash_password, verificado, record)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    email,
                    salt,
                    password_hash,
                    int(user.get("verificado") is True),
                    record,
                ),
            )

    def create_user(
        self, name: str, email: str, salt: str, password_hash: str
    ) -> None:
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO usuarios (nombre, email, salt, hash_password)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, email, salt, password_hash),
                )
        except sqlite3.IntegrityError as error:
            message = str(error).casefold()
            if "usuarios.nombre" in message:
                raise DuplicateUsername("Ese nombre de usuario ya está registrado.") from error
            if "usuarios.email" in message:
                raise DuplicateEmail("Ese correo ya está asociado a otra cuenta.") from error
            raise RepositoryError("No se pudo guardar la cuenta.") from error
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo guardar la cuenta.") from error

    def find_user(self, identifier: str) -> sqlite3.Row | None:
        try:
            with self._connection() as connection:
                return connection.execute(
                    """
                    SELECT * FROM usuarios
                    WHERE nombre = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
                    """,
                    (identifier.strip(), identifier.strip()),
                ).fetchone()
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo consultar la cuenta.") from error

    def get_profile(self, name: str) -> PlayerProfile:
        try:
            with self._connection() as connection:
                user = connection.execute(
                    """
                    SELECT nombre, email, verificado, avatar, record
                    FROM usuarios WHERE nombre = ?
                    """,
                    (name,),
                ).fetchone()
                if user is None:
                    raise UserNotFound("No se encontró el perfil solicitado.")

                statistics = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS matches_played,
                        SUM(CASE WHEN resultado = 'victoria' THEN 1 ELSE 0 END) AS wins,
                        SUM(CASE WHEN resultado = 'derrota' THEN 1 ELSE 0 END) AS losses,
                        SUM(CASE WHEN resultado = 'empate' THEN 1 ELSE 0 END) AS draws
                    FROM historial_partidas WHERE nombre_usuario = ?
                    """,
                    (name,),
                ).fetchone()
                achievements = connection.execute(
                    "SELECT titulo FROM logros WHERE nombre_usuario = ? ORDER BY titulo",
                    (name,),
                ).fetchall()
                history = connection.execute(
                    """
                    SELECT oponente, resultado, puntuacion, fecha
                    FROM historial_partidas
                    WHERE nombre_usuario = ?
                    ORDER BY fecha DESC, id DESC
                    """,
                    (name,),
                ).fetchall()
                ranking = connection.execute(
                    """
                    SELECT COUNT(*) + 1 AS posicion FROM usuarios
                    WHERE record > ? AND record > 0
                    """,
                    (user["record"],),
                ).fetchone()["posicion"]

            matches_played = statistics["matches_played"] or 0
            return PlayerProfile(
                name=user["nombre"],
                email=user["email"],
                email_verified=bool(user["verificado"]),
                avatar=user["avatar"],
                record=user["record"],
                matches_played=matches_played,
                wins=statistics["wins"] or 0,
                losses=statistics["losses"] or 0,
                draws=statistics["draws"] or 0,
                ranking=ranking if user["record"] > 0 else None,
                achievements=tuple(row["titulo"] for row in achievements),
                match_history=tuple(
                    {
                        "opponent": row["oponente"],
                        "result": row["resultado"],
                        "score": row["puntuacion"],
                        "played_at": row["fecha"],
                    }
                    for row in history
                ),
            )
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo consultar el perfil.") from error

    def mark_email_verified(self, name: str) -> None:
        try:
            with self._connection() as connection:
                result = connection.execute(
                    "UPDATE usuarios SET verificado = 1 WHERE nombre = ?", (name,)
                )
                if result.rowcount != 1:
                    raise UserNotFound("No se encontró la cuenta.")
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo activar la cuenta.") from error

    def save_email_link(
        self, token_hash: str, name: str, purpose: str, expires_at: datetime
    ) -> None:
        try:
            with self._connection() as connection:
                connection.execute(
                    "DELETE FROM enlaces WHERE nombre_usuario = ? AND proposito = ?",
                    (name, purpose),
                )
                connection.execute(
                    """
                    INSERT INTO enlaces (hash_token, nombre_usuario, proposito, expira_en)
                    VALUES (?, ?, ?, ?)
                    """,
                    (token_hash, name, purpose, expires_at.isoformat()),
                )
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo crear el enlace solicitado.") from error

    def email_link_is_valid(self, token_hash: str, purpose: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connection() as connection:
                link = connection.execute(
                    """
                    SELECT 1 FROM enlaces
                    WHERE hash_token = ? AND proposito = ? AND expira_en > ?
                    """,
                    (token_hash, purpose, now),
                ).fetchone()
                connection.execute(
                    "DELETE FROM enlaces WHERE expira_en <= ?", (now,)
                )
            return link is not None
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo validar el enlace.") from error

    def consume_email_link(self, token_hash: str, purpose: str) -> str | None:
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                link = connection.execute(
                    """
                    SELECT nombre_usuario FROM enlaces
                    WHERE hash_token = ? AND proposito = ? AND expira_en > ?
                    """,
                    (token_hash, purpose, now),
                ).fetchone()
                if link is None:
                    connection.execute(
                        "DELETE FROM enlaces WHERE expira_en <= ?", (now,)
                    )
                    return None
                connection.execute(
                    "DELETE FROM enlaces WHERE hash_token = ?", (token_hash,)
                )
                return link["nombre_usuario"]
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo consumir el enlace.") from error

    def verify_email_link(self, token_hash: str) -> str | None:
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                link = connection.execute(
                    """
                    SELECT nombre_usuario FROM enlaces
                    WHERE hash_token = ? AND proposito = 'verificacion'
                        AND expira_en > ?
                    """,
                    (token_hash, now),
                ).fetchone()
                if link is None:
                    connection.execute(
                        "DELETE FROM enlaces WHERE expira_en <= ?", (now,)
                    )
                    return None
                connection.execute(
                    "UPDATE usuarios SET verificado = 1 WHERE nombre = ?",
                    (link["nombre_usuario"],),
                )
                connection.execute(
                    "DELETE FROM enlaces WHERE nombre_usuario = ?",
                    (link["nombre_usuario"],),
                )
                return link["nombre_usuario"]
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo verificar el correo.") from error

    def reset_password(
        self, token_hash: str, salt: str, password_hash: str
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                link = connection.execute(
                    """
                    SELECT nombre_usuario FROM enlaces
                    WHERE hash_token = ? AND proposito = 'recuperacion'
                        AND expira_en > ?
                    """,
                    (token_hash, now),
                ).fetchone()
                if link is None:
                    connection.execute(
                        "DELETE FROM enlaces WHERE expira_en <= ?", (now,)
                    )
                    return False
                connection.execute(
                    """
                    UPDATE usuarios SET salt = ?, hash_password = ?
                    WHERE nombre = ?
                    """,
                    (salt, password_hash, link["nombre_usuario"]),
                )
                connection.execute(
                    "DELETE FROM enlaces WHERE hash_token = ?", (token_hash,)
                )
                connection.execute(
                    """
                    DELETE FROM enlaces WHERE nombre_usuario = ?
                        AND proposito = 'recuperacion'
                    """,
                    (link["nombre_usuario"],),
                )
                return True
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo actualizar la contraseña.") from error

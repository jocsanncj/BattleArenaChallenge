import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from backend.models import PlayerProfile


class RepositoryError(RuntimeError):
    ## @brief Error genérico de persistencia que puede exponer la capa de aplicación.
    pass


class DuplicateUsername(RepositoryError):
    ## @brief Indica que ya existe una cuenta con ese nombre.
    pass


class DuplicateEmail(RepositoryError):
    ## @brief Indica que ya existe una cuenta con ese correo.
    pass


class UserNotFound(RepositoryError):
    ## @brief Indica que la cuenta solicitada no existe en SQLite.
    pass


## @brief Encapsula el esquema SQLite y las consultas de cuenta e historial.
class SQLiteRepository:
    ## @brief Configura la carpeta SQLite y el archivo legado opcional.
    ## @param data_directory Carpeta persistente donde se crea la base de datos.
    ## @param legacy_users_file Archivo JSON antiguo que se puede importar.
    def __init__(self, data_directory: Path, legacy_users_file: Path | None = None):
        # Guarda la ubicación destino de la base de datos.
        self.data_directory = data_directory
        # Guarda la ruta del JSON antiguo o None si la migración se desactiva.
        self.legacy_users_file = legacy_users_file

    @contextmanager
    ## @brief Abre una conexión SQLite y garantiza su cierre al terminar.
    ## @return Administrador de contexto que entrega una conexión configurada.
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        # Crea la carpeta de datos la primera vez que se necesita.
        self.data_directory.mkdir(parents=True, exist_ok=True)
        # Abre el archivo de base de datos con espera ante bloqueos breves.
        connection = sqlite3.connect(
            self.data_directory / "usuarios.sqlite3", timeout=10
        )
        # Permite acceder a columnas por nombre además de posición.
        connection.row_factory = sqlite3.Row
        # Activa las restricciones de claves foráneas de SQLite.
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            # Confirma transacciones si el bloque finaliza sin excepción.
            with connection:
                yield connection
        finally:
            # Cierra el descriptor aunque se haya producido un error.
            connection.close()

    ## @brief Crea las tablas y columnas necesarias para el sistema de cuentas.
    ## @return None.
    ## @throws RepositoryError Si no se puede inicializar o importar SQLite.
    def initialize(self) -> None:
        # Mantiene el esquema y la importación en una conexión controlada.
        with self._connection() as connection:
            # Crea cada tabla solo si todavía no existe.
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
            # Consulta la versión actual de la tabla para admitir bases antiguas.
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(usuarios)")
            }
            # Añade avatar a una base antigua sin recrear los datos existentes.
            if "avatar" not in columns:
                connection.execute("ALTER TABLE usuarios ADD COLUMN avatar TEXT")
            # Importa cuentas JSON si se configuró una fuente legada.
            if self.legacy_users_file is not None:
                self._import_legacy_users(connection)

    ## @brief Importa cuentas válidas del JSON antiguo sin sobrescribir SQLite.
    ## @param connection Conexión abierta dentro de initialize().
    ## @return None.
    ## @throws RepositoryError Si el archivo existe pero no se puede leer o parsear.
    def _import_legacy_users(self, connection: sqlite3.Connection) -> None:
        try:
            # Lee el archivo y convierte su JSON a estructuras Python.
            with self.legacy_users_file.open("r", encoding="utf-8") as legacy_file:
                data = json.load(legacy_file)
        except FileNotFoundError:
            # La ausencia del archivo es válida: no hay datos que migrar.
            return
        except (OSError, json.JSONDecodeError) as error:
            raise RepositoryError(
                f"No se pudo leer el archivo de usuarios anterior: {error}"
            ) from error

        # Verifica la estructura principal antes de recorrer las cuentas.
        if not isinstance(data, dict) or not isinstance(data.get("usuarios"), dict):
            raise RepositoryError("DatosUser.json tiene un formato inválido.")

        # Revisa cada entrada individual y salta datos que no sean objetos.
        for name, user in data["usuarios"].items():
            if not isinstance(name, str) or not isinstance(user, dict):
                continue
            # Extrae los campos necesarios para autenticar una cuenta migrada.
            email = user.get("email")
            salt = user.get("salt")
            password_hash = user.get("hash_password")
            if not all(
                isinstance(value, str) and value
                for value in (email, salt, password_hash)
            ):
                continue
            # Verifica que la sal y el hash tengan representación hexadecimal.
            try:
                bytes.fromhex(salt)
                bytes.fromhex(password_hash)
            except ValueError:
                continue
            # Conserva un récord entero; los datos mal tipados se ponen en cero.
            record = user.get("record", 0)
            if not isinstance(record, int) or isinstance(record, bool):
                record = 0
            # INSERT OR IGNORE evita reemplazar cuentas ya importadas o creadas.
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

    ## @brief Inserta una cuenta nueva sin guardar la contraseña en claro.
    ## @param name Nombre único de usuario.
    ## @param email Dirección única de correo.
    ## @param salt Sal hexadecimal asociada a la contraseña.
    ## @param password_hash Hash hexadecimal de la contraseña.
    ## @return None.
    ## @throws DuplicateUsername o DuplicateEmail Si falla una restricción única.
    ## @throws RepositoryError Para otros errores SQLite.
    def create_user(
        self, name: str, email: str, salt: str, password_hash: str
    ) -> None:
        # Ejecuta el INSERT como una transacción y deja defaults al esquema.
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO usuarios (nombre, email, salt, hash_password)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, email, salt, password_hash),
                )
        # Traduce colisiones de índices únicos a errores de dominio específicos.
        except sqlite3.IntegrityError as error:
            message = str(error).casefold()
            if "usuarios.nombre" in message:
                raise DuplicateUsername("Ese nombre de usuario ya está registrado.") from error
            if "usuarios.email" in message:
                raise DuplicateEmail("Ese correo ya está asociado a otra cuenta.") from error
            raise RepositoryError("No se pudo guardar la cuenta.") from error
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo guardar la cuenta.") from error

    ## @brief Busca una cuenta por nombre o correo sin distinguir mayúsculas.
    ## @param identifier Nombre de usuario o correo.
    ## @return Fila SQLite encontrada o None si no existe.
    ## @throws RepositoryError Si falla la consulta.
    def find_user(self, identifier: str) -> sqlite3.Row | None:
        # Convierte errores de base de datos al error público del repositorio.
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

    ## @brief Consulta identidad, estadísticas, logros, ranking e historial.
    ## @param name Nombre de la cuenta cuyo perfil se necesita.
    ## @return Modelo PlayerProfile compuesto desde las tablas relacionadas.
    ## @throws UserNotFound Si no se encuentra el usuario.
    ## @throws RepositoryError Si falla alguna consulta SQLite.
    def get_profile(self, name: str) -> PlayerProfile:
        try:
            # Recupera los campos principales de la cuenta.
            with self._connection() as connection:
                user = connection.execute(
                    """
                    SELECT nombre, email, verificado, avatar, record
                    FROM usuarios WHERE nombre = ?
                    """,
                    (name,),
                ).fetchone()
                # No se puede construir un perfil sin una cuenta existente.
                if user is None:
                    raise UserNotFound("No se encontró el perfil solicitado.")

                # Calcula el total y cada resultado directamente en SQL.
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
                # Carga logros ordenados para presentar resultados consistentes.
                achievements = connection.execute(
                    "SELECT titulo FROM logros WHERE nombre_usuario = ? ORDER BY titulo",
                    (name,),
                ).fetchall()
                # Ordena primero las partidas más recientes.
                history = connection.execute(
                    """
                    SELECT oponente, resultado, puntuacion, fecha
                    FROM historial_partidas
                    WHERE nombre_usuario = ?
                    ORDER BY fecha DESC, id DESC
                    """,
                    (name,),
                ).fetchall()
                # Cuenta récords superiores para calcular la posición ordinal.
                ranking = connection.execute(
                    """
                    SELECT COUNT(*) + 1 AS posicion FROM usuarios
                    WHERE record > ? AND record > 0
                    """,
                    (user["record"],),
                ).fetchone()["posicion"]

            # SQLite devuelve NULL para sumas vacías; se sustituyen por ceros.
            matches_played = statistics["matches_played"] or 0
            # Convierte filas y contadores en el modelo estable de la aplicación.
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
        # Mantiene los errores de persistencia bajo una excepción del repositorio.
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo consultar el perfil.") from error

    ## @brief Marca directamente la cuenta como verificada.
    ## @param name Nombre exacto de la cuenta.
    ## @return None.
    ## @throws UserNotFound Si el UPDATE no afecta ninguna cuenta.
    ## @throws RepositoryError Si SQLite rechaza la operación.
    def mark_email_verified(self, name: str) -> None:
        # Actualiza el indicador de verificación en una transacción.
        try:
            with self._connection() as connection:
                result = connection.execute(
                    "UPDATE usuarios SET verificado = 1 WHERE nombre = ?", (name,)
                )
                if result.rowcount != 1:
                    raise UserNotFound("No se encontró la cuenta.")
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo activar la cuenta.") from error

    ## @brief Reemplaza el enlace previo del mismo usuario y propósito.
    ## @param token_hash Hash del token secreto.
    ## @param name Nombre de la cuenta destinataria.
    ## @param purpose Propósito del enlace.
    ## @param expires_at Fecha y hora UTC de expiración.
    ## @return None.
    ## @throws RepositoryError Si no puede persistir el enlace.
    def save_email_link(
        self, token_hash: str, name: str, purpose: str, expires_at: datetime
    ) -> None:
        # Borra cualquier enlace anterior equivalente antes de insertar el nuevo.
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

    ## @brief Comprueba existencia y vigencia de un enlace sin consumirlo.
    ## @param token_hash Hash hexadecimal del token recibido.
    ## @param purpose Propósito esperado para este enlace.
    ## @return True si el enlace existe y no ha expirado.
    ## @throws RepositoryError Si falla SQLite.
    def email_link_is_valid(self, token_hash: str, purpose: str) -> bool:
        # Usa UTC para que las fechas comparadas tengan la misma referencia.
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
                # Limpia enlaces vencidos después de realizar la comprobación.
                connection.execute(
                    "DELETE FROM enlaces WHERE expira_en <= ?", (now,)
                )
            return link is not None
        except sqlite3.Error as error:
            raise RepositoryError("No se pudo validar el enlace.") from error

    ## @brief Consume un enlace genérico de un solo uso dentro de una transacción.
    ## @param token_hash Hash del token presentado.
    ## @param purpose Propósito que debe coincidir.
    ## @return Nombre asociado o None si el enlace no es válido.
    ## @throws RepositoryError Si falla la transacción.
    def consume_email_link(self, token_hash: str, purpose: str) -> str | None:
        # Calcula la hora de referencia y abre una transacción de escritura.
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connection() as connection:
                # Bloquea escrituras concurrentes para consumir una sola vez.
                connection.execute("BEGIN IMMEDIATE")
                link = connection.execute(
                    """
                    SELECT nombre_usuario FROM enlaces
                    WHERE hash_token = ? AND proposito = ? AND expira_en > ?
                    """,
                    (token_hash, purpose, now),
                ).fetchone()
                # Limpia enlaces vencidos y devuelve ausencia si no hay coincidencia.
                if link is None:
                    # Elimina el token encontrado para impedir una segunda utilización.
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

    ## @brief Activa la cuenta y consume su enlace de verificación atómicamente.
    ## @param token_hash Hash del token de verificación.
    ## @return Nombre de la cuenta activada o None si no era válido.
    ## @throws RepositoryError Si falla la operación SQLite.
    def verify_email_link(self, token_hash: str) -> str | None:
        # Usa una transacción de escritura para evitar verificaciones duplicadas.
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connection() as connection:
                # Bloquea otras escrituras hasta finalizar la activación.
                connection.execute("BEGIN IMMEDIATE")
                link = connection.execute(
                    """
                    SELECT nombre_usuario FROM enlaces
                    WHERE hash_token = ? AND proposito = 'verificacion'
                        AND expira_en > ?
                    """,
                    (token_hash, now),
                ).fetchone()
                # Borra expirados y no modifica cuentas si el token es inválido.
                if link is None:
                    # Cambia el estado de verificación para el usuario del token.
                    connection.execute(
                        "DELETE FROM enlaces WHERE expira_en <= ?", (now,)
                    )
                    return None
                # Invalida enlaces de esa cuenta al completar la verificación.
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

    ## @brief Actualiza la contraseña y consume los enlaces de recuperación.
    ## @param token_hash Hash del enlace presentado.
    ## @param salt Nueva sal hexadecimal.
    ## @param password_hash Nuevo hash hexadecimal de contraseña.
    ## @return True si se actualizó la contraseña; False para token inválido.
    ## @throws RepositoryError Si falla la transacción SQLite.
    def reset_password(
        self, token_hash: str, salt: str, password_hash: str
    ) -> bool:
        # Fija la hora UTC para comprobar la fecha de vencimiento del token.
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connection() as connection:
                # Garantiza que un enlace no se use en dos recuperaciones paralelas.
                connection.execute("BEGIN IMMEDIATE")
                link = connection.execute(
                    """
                    SELECT nombre_usuario FROM enlaces
                    WHERE hash_token = ? AND proposito = 'recuperacion'
                        AND expira_en > ?
                    """,
                    (token_hash, now),
                ).fetchone()
                # Devuelve False sin modificar cuenta si el token no está vigente.
                if link is None:
                    # Reemplaza simultáneamente la sal y el hash guardados.
                    connection.execute(
                        "DELETE FROM enlaces WHERE expira_en <= ?", (now,)
                    )
                    return False
                # Consume el token utilizado en esta recuperación.
                connection.execute(
                    """
                    UPDATE usuarios SET salt = ?, hash_password = ?
                    WHERE nombre = ?
                    """,
                    (salt, password_hash, link["nombre_usuario"]),
                )
                # Invalida otros enlaces antiguos de recuperación para la cuenta.
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

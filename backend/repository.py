"""Persistencia JSON de perfiles de juego y datos de cuentas heredadas."""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict, cast

from backend.models import PlayerProfile


class UserRecord(TypedDict, total=False):
    """Campos persistidos para una cuenta de usuario."""

    email: str
    salt: str
    hash_password: str
    verificado: bool
    record: int
    avatar: str | None


class FirebaseProfileRecord(TypedDict):
    """Datos de juego asociados a una identidad autenticada por Firebase."""

    name: str
    email: str
    email_verified: bool
    record: int
    avatar: str | None


class EmailLinkRecord(TypedDict):
    """Datos asociados a un token de verificación o recuperación."""

    nombre_usuario: str
    proposito: str
    expira_en: str


class MatchRecord(TypedDict):
    """Datos de una partida que puede mostrarse en el perfil."""

    opponent: str
    result: str
    score: int
    played_at: str


class JSONStore(TypedDict):
    """Estructura raíz guardada en usuarios.json."""

    usuarios: dict[str, UserRecord]
    logros: dict[str, list[str]]
    historial_partidas: dict[str, list[MatchRecord]]
    enlaces: dict[str, EmailLinkRecord]
    firebase_profiles: dict[str, FirebaseProfileRecord]


class RepositoryError(RuntimeError):
    """Error al leer o escribir los datos JSON."""


class DuplicateUsername(RepositoryError):
    """El nombre de usuario ya existe, sin distinguir mayúsculas."""


class DuplicateEmail(RepositoryError):
    """El correo ya está asociado a otra cuenta."""


class UserNotFound(RepositoryError):
    """No se encontró la cuenta solicitada."""


def _empty_store() -> JSONStore:
    """Crea las colecciones iniciales del archivo de datos."""
    return {
        "usuarios": {},
        "logros": {},
        "historial_partidas": {},
        "enlaces": {},
        "firebase_profiles": {},
    }


class JSONRepository:
    """Guarda perfiles Firebase y conserva datos JSON anteriores del proyecto."""

    def __init__(
        self, data_directory: Path, legacy_users_file: Path | None = None
    ) -> None:
        """Define la ubicación de datos y una fuente JSON legada opcional."""
        self.data_directory = data_directory
        self.file_path = data_directory / "usuarios.json"
        self.legacy_users_file = legacy_users_file
        self._lock = threading.RLock()

    def initialize(self) -> None:
        """Crea el archivo de datos o importa el JSON legado una sola vez."""
        with self._lock:
            try:
                self.data_directory.mkdir(parents=True, exist_ok=True)
                if self.file_path.exists():
                    self._read_store()
                    return

                store = _empty_store()
                if (
                    self.legacy_users_file is not None
                    and self.legacy_users_file.resolve() != self.file_path.resolve()
                ):
                    self._import_legacy_users(store)
                self._write_store(store)
            except OSError as error:
                raise RepositoryError(
                    f"No se pudo inicializar el archivo JSON: {error}"
                ) from error

    def _read_store(self) -> JSONStore:
        """Lee y valida las colecciones principales del archivo JSON."""
        try:
            with self.file_path.open("r", encoding="utf-8") as data_file:
                raw_store = json.load(data_file)
        except (OSError, json.JSONDecodeError) as error:
            raise RepositoryError(
                f"No se pudo leer el archivo de datos {self.file_path}: {error}"
            ) from error

        if not isinstance(raw_store, dict):
            raise RepositoryError("El archivo de datos JSON tiene formato inválido.")

        required_sections = ("usuarios", "logros", "historial_partidas", "enlaces")
        if any(not isinstance(raw_store.get(section), dict) for section in required_sections):
            raise RepositoryError(
                "El archivo de datos debe contener usuarios, logros, "
                "historial_partidas y enlaces."
            )
        firebase_profiles = raw_store.setdefault("firebase_profiles", {})
        if not isinstance(firebase_profiles, dict):
            raise RepositoryError("La sección firebase_profiles debe ser un objeto.")
        return cast(JSONStore, raw_store)

    def _write_store(self, store: JSONStore) -> None:
        """Escribe todo el JSON en un temporal y lo reemplaza atómicamente."""
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.data_directory,
                prefix=".usuarios-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                json.dump(store, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.file_path)
        except (OSError, TypeError, ValueError) as error:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
            raise RepositoryError(
                f"No se pudieron guardar los datos JSON: {error}"
            ) from error

    def _import_legacy_users(self, store: JSONStore) -> None:
        """Copia cuentas válidas del formato antiguo sin sobrescribir cuentas."""
        assert self.legacy_users_file is not None
        try:
            with self.legacy_users_file.open("r", encoding="utf-8") as legacy_file:
                legacy_data = json.load(legacy_file)
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError) as error:
            raise RepositoryError(
                f"No se pudo leer el archivo de usuarios anterior: {error}"
            ) from error

        if not isinstance(legacy_data, dict) or not isinstance(
            legacy_data.get("usuarios"), dict
        ):
            raise RepositoryError("DatosUser.json tiene un formato inválido.")

        legacy_users = legacy_data["usuarios"]
        for name, legacy_user in legacy_users.items():
            if not isinstance(name, str) or not isinstance(legacy_user, dict):
                continue
            email = legacy_user.get("email")
            salt = legacy_user.get("salt")
            password_hash = legacy_user.get("hash_password")
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

            existing_names = {key.casefold() for key in store["usuarios"]}
            existing_emails = {
                user.get("email", "").casefold()
                for user in store["usuarios"].values()
            }
            if name.casefold() in existing_names or email.casefold() in existing_emails:
                continue

            record = legacy_user.get("record", 0)
            if not isinstance(record, int) or isinstance(record, bool):
                record = 0
            store["usuarios"][name] = {
                "email": email,
                "salt": salt,
                "hash_password": password_hash,
                "verificado": legacy_user.get("verificado") is True,
                "record": record,
                "avatar": None,
            }

    @staticmethod
    def _find_name(users: dict[str, UserRecord], name: str) -> str | None:
        """Busca y devuelve la clave de usuario ignorando mayúsculas."""
        folded_name = name.casefold()
        return next(
            (stored_name for stored_name in users if stored_name.casefold() == folded_name),
            None,
        )

    def create_user(
        self, name: str, email: str, salt: str, password_hash: str
    ) -> None:
        """Crea una cuenta si su nombre y correo aún no se han registrado."""
        with self._lock:
            store = self._read_store()
            if self._find_name(store["usuarios"], name) is not None:
                raise DuplicateUsername("Ese nombre de usuario ya está registrado.")
            if any(
                user.get("email", "").casefold() == email.casefold()
                for user in store["usuarios"].values()
            ):
                raise DuplicateEmail("Ese correo ya está asociado a otra cuenta.")

            store["usuarios"][name] = {
                "email": email,
                "salt": salt,
                "hash_password": password_hash,
                "verificado": False,
                "record": 0,
                "avatar": None,
            }
            store["logros"][name] = []
            store["historial_partidas"][name] = []
            self._write_store(store)

    def find_user(self, identifier: str) -> UserRecord | None:
        """Busca una cuenta por nombre de usuario o dirección de correo."""
        with self._lock:
            store = self._read_store()
            folded_identifier = identifier.strip().casefold()
            for name, user in store["usuarios"].items():
                if (
                    name.casefold() == folded_identifier
                    or user.get("email", "").casefold() == folded_identifier
                ):
                    return user | {"nombre": name}
            return None

    def get_profile(self, name: str) -> PlayerProfile:
        """Construye el perfil a partir de la cuenta, logros e historial."""
        with self._lock:
            store = self._read_store()
            stored_name = self._find_name(store["usuarios"], name)
            if stored_name is None:
                raise UserNotFound("No se encontró el perfil solicitado.")

            user = store["usuarios"][stored_name]
            history = store["historial_partidas"].get(stored_name, [])
            achievements = store["logros"].get(stored_name, [])
            matches_played = len(history)
            wins = sum(match.get("result") == "victoria" for match in history)
            losses = sum(match.get("result") == "derrota" for match in history)
            draws = sum(match.get("result") == "empate" for match in history)
            record = user.get("record", 0)
            higher_records = sum(
                other.get("record", 0) > record and other.get("record", 0) > 0
                for other in store["usuarios"].values()
            )
            sorted_history = sorted(
                history, key=lambda match: (match.get("played_at", ""),), reverse=True
            )

            return PlayerProfile(
                name=stored_name,
                email=user.get("email", ""),
                email_verified=user.get("verificado", False),
                avatar=user.get("avatar"),
                record=record,
                matches_played=matches_played,
                wins=wins,
                losses=losses,
                draws=draws,
                ranking=higher_records + 1 if record > 0 else None,
                achievements=tuple(sorted(achievements)),
                match_history=tuple(dict(match) for match in sorted_history),
            )

    ## @brief Crea o actualiza un perfil de juego usando un UID verificado.
    ## @param uid Identificador único validado en el token Firebase.
    ## @param name Nombre público del jugador.
    ## @param email Correo incluido en el token firmado.
    ## @param email_verified Estado de verificación informado por Firebase.
    ## @return None.
    def upsert_firebase_profile(
        self, uid: str, name: str, email: str, email_verified: bool
    ) -> None:
        """Crea o actualiza datos de juego vinculados al UID validado por Firebase."""
        if not uid.strip() or not name.strip() or not email.strip():
            raise RepositoryError("Firebase devolvió datos incompletos de perfil.")

        with self._lock:
            store = self._read_store()
            existing = store["firebase_profiles"].get(uid)
            record = existing.get("record", 0) if existing else 0
            avatar = existing.get("avatar") if existing else None
            store["firebase_profiles"][uid] = {
                "name": name.strip(),
                "email": email.strip(),
                "email_verified": email_verified,
                "record": record,
                "avatar": avatar,
            }
            self._write_store(store)

    ## @brief Construye el perfil de juego asociado a una identidad Firebase.
    ## @param uid Identificador único validado en el token Firebase.
    ## @return Perfil con datos personales y estadísticas.
    ## @throws UserNotFound Si todavía no existe un perfil para ese UID.
    def get_firebase_profile(self, uid: str) -> PlayerProfile:
        """Devuelve el perfil de juego correspondiente a un UID de Firebase."""
        with self._lock:
            store = self._read_store()
            user = store["firebase_profiles"].get(uid)
            if user is None:
                raise UserNotFound("No se encontró el perfil del jugador.")

            history = store["historial_partidas"].get(uid, [])
            achievements = store["logros"].get(uid, [])
            matches_played = len(history)
            wins = sum(match.get("result") == "victoria" for match in history)
            losses = sum(match.get("result") == "derrota" for match in history)
            draws = sum(match.get("result") == "empate" for match in history)
            record = user.get("record", 0)
            higher_records = sum(
                other.get("record", 0) > record and other.get("record", 0) > 0
                for other in store["firebase_profiles"].values()
            )
            sorted_history = sorted(
                history, key=lambda match: match.get("played_at", ""), reverse=True
            )

            return PlayerProfile(
                name=user["name"],
                email=user["email"],
                email_verified=user["email_verified"],
                avatar=user.get("avatar"),
                record=record,
                matches_played=matches_played,
                wins=wins,
                losses=losses,
                draws=draws,
                ranking=higher_records + 1 if record > 0 else None,
                achievements=tuple(sorted(achievements)),
                match_history=tuple(dict(match) for match in sorted_history),
            )

    def mark_email_verified(self, name: str) -> None:
        """Marca como verificada una cuenta que exista."""
        with self._lock:
            store = self._read_store()
            stored_name = self._find_name(store["usuarios"], name)
            if stored_name is None:
                raise UserNotFound("No se encontró la cuenta.")
            store["usuarios"][stored_name]["verificado"] = True
            self._write_store(store)

    def save_email_link(
        self, token_hash: str, name: str, purpose: str, expires_at: datetime
    ) -> None:
        """Guarda un nuevo enlace y reemplaza el previo del mismo propósito."""
        with self._lock:
            store = self._read_store()
            stored_name = self._find_name(store["usuarios"], name)
            if stored_name is None:
                raise UserNotFound("No se encontró la cuenta.")
            store["enlaces"] = {
                existing_hash: link
                for existing_hash, link in store["enlaces"].items()
                if not (
                    link.get("nombre_usuario") == stored_name
                    and link.get("proposito") == purpose
                )
            }
            store["enlaces"][token_hash] = {
                "nombre_usuario": stored_name,
                "proposito": purpose,
                "expira_en": expires_at.isoformat(),
            }
            self._write_store(store)

    def email_link_is_valid(self, token_hash: str, purpose: str) -> bool:
        """Comprueba que un enlace exista, corresponda al propósito y no expire."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            store = self._read_store()
            link = store["enlaces"].get(token_hash)
            valid = bool(
                link
                and link.get("proposito") == purpose
                and link.get("expira_en", "") > now
            )
            remaining_links = {
                key: value
                for key, value in store["enlaces"].items()
                if value.get("expira_en", "") > now
            }
            if len(remaining_links) != len(store["enlaces"]):
                store["enlaces"] = remaining_links
                self._write_store(store)
            return valid

    def consume_email_link(self, token_hash: str, purpose: str) -> str | None:
        """Consume un enlace válido y devuelve el usuario asociado."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            store = self._read_store()
            link = store["enlaces"].get(token_hash)
            if (
                link is None
                or link.get("proposito") != purpose
                or link.get("expira_en", "") <= now
            ):
                store["enlaces"] = {
                    key: value
                    for key, value in store["enlaces"].items()
                    if value.get("expira_en", "") > now
                }
                self._write_store(store)
                return None
            del store["enlaces"][token_hash]
            self._write_store(store)
            return link["nombre_usuario"]

    def verify_email_link(self, token_hash: str) -> str | None:
        """Activa la cuenta y consume sus enlaces tras verificar el correo."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            store = self._read_store()
            link = store["enlaces"].get(token_hash)
            if (
                link is None
                or link.get("proposito") != "verificacion"
                or link.get("expira_en", "") <= now
            ):
                store["enlaces"] = {
                    key: value
                    for key, value in store["enlaces"].items()
                    if value.get("expira_en", "") > now
                }
                self._write_store(store)
                return None

            name = link["nombre_usuario"]
            user = store["usuarios"].get(name)
            if user is None:
                raise RepositoryError("El enlace apunta a una cuenta inexistente.")
            user["verificado"] = True
            store["enlaces"] = {
                key: value
                for key, value in store["enlaces"].items()
                if value.get("nombre_usuario") != name
            }
            self._write_store(store)
            return name

    def reset_password(
        self, token_hash: str, salt: str, password_hash: str
    ) -> bool:
        """Actualiza la contraseña y consume enlaces de recuperación activos."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            store = self._read_store()
            link = store["enlaces"].get(token_hash)
            if (
                link is None
                or link.get("proposito") != "recuperacion"
                or link.get("expira_en", "") <= now
            ):
                store["enlaces"] = {
                    key: value
                    for key, value in store["enlaces"].items()
                    if value.get("expira_en", "") > now
                }
                self._write_store(store)
                return False

            name = link["nombre_usuario"]
            user = store["usuarios"].get(name)
            if user is None:
                raise RepositoryError("El enlace apunta a una cuenta inexistente.")
            user["salt"] = salt
            user["hash_password"] = password_hash
            store["enlaces"] = {
                key: value
                for key, value in store["enlaces"].items()
                if not (
                    value.get("nombre_usuario") == name
                    and value.get("proposito") == "recuperacion"
                )
            }
            self._write_store(store)
            return True


__all__ = [
    "DuplicateEmail",
    "DuplicateUsername",
    "JSONRepository",
    "RepositoryError",
    "UserNotFound",
]

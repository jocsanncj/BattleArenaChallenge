import hashlib
import hmac
import os
import re
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode

from backend.models import RegistrationResult
from backend.repository import SQLiteRepository, UserNotFound


MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256
VERIFICATION_LINK_LIFETIME = timedelta(hours=24)
RECOVERY_LINK_LIFETIME = timedelta(minutes=20)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_PATTERN = re.compile(r"^.{8,256}$", re.DOTALL)


class InvalidInput(ValueError):
    pass


class InvalidCredentials(PermissionError):
    pass


class EmailNotVerified(PermissionError):
    pass


class InvalidEmailLink(ValueError):
    pass


class EmailService:
    def __init__(self, public_base_url: str | None = None):
        self.sender = os.getenv("GMAIL_ADDRESS", "").strip()
        self.password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "465"))
        self.public_base_url = (
            public_base_url or os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
        ).rstrip("/")

    def _send(self, recipient: str, subject: str, body: str) -> None:
        if not self.sender or not self.password:
            raise RuntimeError(
                "El servidor no tiene GMAIL_ADDRESS y GMAIL_APP_PASSWORD configurados."
            )
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP_SSL(
                self.smtp_host, self.smtp_port, timeout=20
            ) as smtp:
                smtp.login(self.sender, self.password)
                smtp.send_message(message)
        except smtplib.SMTPAuthenticationError as error:
            raise RuntimeError(
                "Gmail rechazó las credenciales. Revisa GMAIL_ADDRESS y "
                "GMAIL_APP_PASSWORD."
            ) from error
        except smtplib.SMTPRecipientsRefused as error:
            raise RuntimeError("El servidor de correo rechazó el destinatario.") from error
        except (smtplib.SMTPException, OSError, TimeoutError) as error:
            raise RuntimeError(
                f"No se pudo enviar el correo ({type(error).__name__})."
            ) from error

    def send_link(self, recipient: str, name: str, token: str, purpose: str) -> None:
        if purpose == "verificacion":
            link = f"{self.public_base_url}/verify-email?{urlencode({'token': token})}"
            subject = "Verifica tu correo - Battle Arena Challenge"
            message = (
                f"Hola {name},\n\n"
                "Para verificar tu correo y activar tu cuenta, abre este enlace:\n"
                f"{link}\n\n"
                "El enlace vence en 24 horas y solo puede usarse una vez."
            )
        else:
            link = f"{self.public_base_url}/reset-password?{urlencode({'token': token})}"
            subject = "Recupera tu contraseña - Battle Arena Challenge"
            message = (
                f"Hola {name},\n\n"
                "Para crear una contraseña nueva, abre este enlace:\n"
                f"{link}\n\n"
                "El enlace vence en 20 minutos y solo puede usarse una vez. "
                "Si no solicitaste la recuperación, ignora este mensaje."
            )
        self._send(recipient, subject, message)


class AccountService:
    def __init__(self, repository: SQLiteRepository, email_service: EmailService):
        self.repository = repository
        self.email_service = email_service

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, 600_000
        ).hex()

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def validate_password(password: str) -> None:
        if not PASSWORD_PATTERN.fullmatch(password):
            raise InvalidInput(
                f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} "
                f"y {MAX_PASSWORD_LENGTH} caracteres."
            )

    def register(
        self,
        name: str,
        email: str,
        password: str,
        confirmation: str,
    ) -> RegistrationResult:
        name = name.strip()
        email = email.strip()
        if not name or not email or not password or not confirmation:
            raise InvalidInput("Todos los campos son obligatorios.")
        if len(name) > 40:
            raise InvalidInput("El nombre de usuario no puede exceder 40 caracteres.")
        if not EMAIL_PATTERN.fullmatch(email):
            raise InvalidInput("Escribe un correo electrónico válido.")
        self.validate_password(password)
        if password != confirmation:
            raise InvalidInput("Las contraseñas no coinciden.")

        salt = secrets.token_bytes(16)
        self.repository.create_user(
            name,
            email,
            salt.hex(),
            self._password_hash(password, salt),
        )
        profile = self.repository.get_profile(name)
        verification_sent = False
        email_error = ""
        try:
            self.send_email_link(name, "verificacion")
            verification_sent = True
        except RuntimeError as error:
            email_error = str(error)
        return RegistrationResult(profile, verification_sent, email_error)

    def authenticate(self, identifier: str, password: str):
        if not identifier.strip() or not password:
            raise InvalidInput("Escribe tu usuario o correo y tu contraseña.")
        user = self.repository.find_user(identifier)
        if user is None:
            raise InvalidCredentials("Usuario/correo o contraseña incorrectos.")
        try:
            salt = bytes.fromhex(user["salt"])
        except ValueError as error:
            raise RuntimeError("La cuenta contiene credenciales inválidas.") from error
        candidate_hash = self._password_hash(password, salt)
        if not hmac.compare_digest(candidate_hash, user["hash_password"]):
            raise InvalidCredentials("Usuario/correo o contraseña incorrectos.")
        if not user["verificado"]:
            raise EmailNotVerified(
                "El correo aún no está verificado. Revisa tu correo o solicita "
                "un nuevo enlace."
            )
        return self.repository.get_profile(user["nombre"])

    def get_profile(self, name: str):
        return self.repository.get_profile(name)

    def send_email_link(self, identifier: str, purpose: str) -> None:
        if purpose not in ("verificacion", "recuperacion"):
            raise InvalidInput("El tipo de enlace solicitado no es válido.")
        user = self.repository.find_user(identifier)
        if user is None:
            if purpose == "recuperacion":
                return
            raise UserNotFound("No se encontró la cuenta.")
        if purpose == "verificacion" and user["verificado"]:
            return

        token = secrets.token_urlsafe(32)
        lifetime = (
            VERIFICATION_LINK_LIFETIME
            if purpose == "verificacion"
            else RECOVERY_LINK_LIFETIME
        )
        self.repository.save_email_link(
            self._token_hash(token),
            user["nombre"],
            purpose,
            datetime.now(timezone.utc) + lifetime,
        )
        self.email_service.send_link(user["email"], user["nombre"], token, purpose)

    def verify_email(self, token: str) -> None:
        name = self.repository.verify_email_link(self._token_hash(token))
        if name is None:
            raise InvalidEmailLink(
                "El enlace de verificación no es válido, venció o ya fue usado."
            )

    def recovery_link_is_valid(self, token: str) -> bool:
        return self.repository.email_link_is_valid(
            self._token_hash(token), "recuperacion"
        )

    def reset_password(
        self, token: str, password: str, confirmation: str
    ) -> None:
        self.validate_password(password)
        if password != confirmation:
            raise InvalidInput("Las contraseñas no coinciden.")
        salt = secrets.token_bytes(16)
        updated = self.repository.reset_password(
            self._token_hash(token),
            salt.hex(),
            self._password_hash(password, salt),
        )
        if not updated:
            raise InvalidEmailLink(
                "El enlace de recuperación no es válido, venció o ya fue usado."
            )

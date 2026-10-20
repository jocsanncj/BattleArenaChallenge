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


# Límites compartidos por la validación de registro y recuperación.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256
# Define cuánto tiempo se puede utilizar cada clase de enlace de correo.
VERIFICATION_LINK_LIFETIME = timedelta(hours=24)
RECOVERY_LINK_LIFETIME = timedelta(minutes=20)
# Expresiones regulares para campos que reciben texto externo.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_PATTERN = re.compile(r"^.{8,256}$", re.DOTALL)


class InvalidInput(ValueError):
    ## @brief Error de validación de datos enviados por el cliente.
    pass


class InvalidCredentials(PermissionError):
    ## @brief Error que indica que la combinación de usuario y contraseña no es válida.
    pass


class EmailNotVerified(PermissionError):
    ## @brief Error que impide autenticar una cuenta aún no verificada.
    pass


class InvalidEmailLink(ValueError):
    ## @brief Error para enlaces inválidos, expirados o consumidos previamente.
    pass


## @brief Genera mensajes de activación y recuperación y los envía por SMTP.
class EmailService:
    ## @brief Lee la configuración del proveedor SMTP desde el entorno.
    ## @param public_base_url URL pública opcional para construir los enlaces.
    def __init__(self, public_base_url: str | None = None):
        # Guarda las credenciales SMTP sin espacios exteriores.
        self.sender = os.getenv("GMAIL_ADDRESS", "").strip()
        self.password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
        # Permite usar otro servidor o puerto SMTP mediante configuración.
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "465"))
        # Normaliza la URL quitando una barra final para concatenar rutas.
        self.public_base_url = (
            public_base_url or os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
        ).rstrip("/")

    ## @brief Envía un mensaje de texto usando SMTP sobre TLS.
    ## @param recipient Dirección que recibirá el correo.
    ## @param subject Asunto visible del correo.
    ## @param body Contenido en texto plano.
    ## @return None.
    ## @throws RuntimeError Si faltan credenciales o SMTP rechaza el envío.
    def _send(self, recipient: str, subject: str, body: str) -> None:
        # Falla explícitamente si el servidor no está configurado para correo.
        if not self.sender or not self.password:
            raise RuntimeError(
                "El servidor no tiene GMAIL_ADDRESS y GMAIL_APP_PASSWORD configurados."
            )
        # Construye el mensaje con remitente, destinatario, asunto y cuerpo.
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        # Abre la conexión TLS y autentica antes de mandar el mensaje.
        try:
            with smtplib.SMTP_SSL(
                self.smtp_host, self.smtp_port, timeout=20
            ) as smtp:
                smtp.login(self.sender, self.password)
                smtp.send_message(message)
        # Convierte errores técnicos en mensajes útiles para la interfaz.
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

    ## @brief Construye y envía un enlace de verificación o recuperación.
    ## @param recipient Correo del destinatario.
    ## @param name Nombre usado para saludar al jugador.
    ## @param token Token de un solo uso incluido en la URL.
    ## @param purpose Propósito: verificacion o recuperacion.
    ## @return None.
    def send_link(self, recipient: str, name: str, token: str, purpose: str) -> None:
        # Selecciona texto, ruta y plazo adecuados al propósito del enlace.
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
        # Centraliza la transmisión SMTP en el helper que gestiona errores.
        self._send(recipient, subject, message)


## @brief Implementa validación, autenticación y flujos de cuenta.
class AccountService:
    ## @brief Conecta las reglas de cuenta con repositorio y correo.
    ## @param repository Persistencia SQLite de usuarios y enlaces.
    ## @param email_service Servicio responsable de los mensajes.
    def __init__(self, repository: SQLiteRepository, email_service: EmailService):
        # Guarda las dependencias que usará la lógica de aplicación.
        self.repository = repository
        self.email_service = email_service

    @staticmethod
    ## @brief Deriva un hash de contraseña mediante PBKDF2-HMAC-SHA256.
    ## @param password Contraseña original que no se almacena.
    ## @param salt Sal aleatoria asociada a la cuenta.
    ## @return Hash hexadecimal derivado con 600 000 iteraciones.
    def _password_hash(password: str, salt: bytes) -> str:
        # Devuelve el hash en hexadecimal para almacenarlo en SQLite.
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, 600_000
        ).hex()

    @staticmethod
    ## @brief Calcula el hash SHA-256 de un token antes de guardarlo.
    ## @param token Token aleatorio enviado al usuario.
    ## @return Representación hexadecimal del hash del token.
    def _token_hash(token: str) -> str:
        # Nunca conserva el token original en la base de datos.
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    ## @brief Comprueba que la contraseña respete los límites definidos.
    ## @param password Texto de contraseña recibido.
    ## @return None si cumple las reglas.
    ## @throws InvalidInput Si tiene menos de 8 o más de 256 caracteres.
    def validate_password(password: str) -> None:
        # Rechaza contraseñas fuera del patrón requerido.
        if not PASSWORD_PATTERN.fullmatch(password):
            raise InvalidInput(
                f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} "
                f"y {MAX_PASSWORD_LENGTH} caracteres."
            )

    ## @brief Valida, guarda y solicita correo de verificación de una cuenta.
    ## @param name Nombre de usuario elegido.
    ## @param email Correo que se asociará a la cuenta.
    ## @param password Contraseña nueva.
    ## @param confirmation Repetición de la contraseña.
    ## @return Perfil creado y resultado del envío de verificación.
    ## @throws InvalidInput Si los campos o las contraseñas no son válidos.
    def register(
        self,
        name: str,
        email: str,
        password: str,
        confirmation: str,
    ) -> RegistrationResult:
        # Quita espacios exteriores antes de aplicar reglas y persistir.
        name = name.strip()
        email = email.strip()
        # Impide crear cuentas con valores vacíos.
        if not name or not email or not password or not confirmation:
            raise InvalidInput("Todos los campos son obligatorios.")
        if len(name) > 40:
            raise InvalidInput("El nombre de usuario no puede exceder 40 caracteres.")
        if not EMAIL_PATTERN.fullmatch(email):
            raise InvalidInput("Escribe un correo electrónico válido.")
        self.validate_password(password)
        if password != confirmation:
            raise InvalidInput("Las contraseñas no coinciden.")

        # Genera una sal nueva y aleatoria para esta contraseña.
        salt = secrets.token_bytes(16)
        self.repository.create_user(
            name,
            email,
            salt.hex(),
            self._password_hash(password, salt),
        )
        # Recupera el perfil inicial generado por el repositorio.
        profile = self.repository.get_profile(name)
        verification_sent = False
        email_error = ""
        # La cuenta queda guardada aunque el proveedor de correo falle.
        try:
            self.send_email_link(name, "verificacion")
            verification_sent = True
        except RuntimeError as error:
            email_error = str(error)
        return RegistrationResult(profile, verification_sent, email_error)

    ## @brief Valida credenciales y devuelve el perfil si el correo está verificado.
    ## @param identifier Nombre de usuario o dirección de correo.
    ## @param password Contraseña proporcionada.
    ## @return Perfil autenticado.
    ## @throws InvalidInput Si los campos requeridos están vacíos.
    ## @throws InvalidCredentials Si no hay coincidencia de credenciales.
    ## @throws EmailNotVerified Si la cuenta aún no fue activada.
    def authenticate(self, identifier: str, password: str):
        # No consulta la base de datos para entradas vacías.
        if not identifier.strip() or not password:
            raise InvalidInput("Escribe tu usuario o correo y tu contraseña.")
        # Busca por nombre o correo; ambos identificadores son únicos.
        user = self.repository.find_user(identifier)
        if user is None:
            raise InvalidCredentials("Usuario/correo o contraseña incorrectos.")
        # Convierte la sal hexadecimal al formato binario requerido por PBKDF2.
        try:
            salt = bytes.fromhex(user["salt"])
        except ValueError as error:
            raise RuntimeError("La cuenta contiene credenciales inválidas.") from error
        # Recalcula el hash y lo compara en tiempo constante.
        candidate_hash = self._password_hash(password, salt)
        if not hmac.compare_digest(candidate_hash, user["hash_password"]):
            raise InvalidCredentials("Usuario/correo o contraseña incorrectos.")
        # Exige verificación antes de conceder una sesión al cliente.
        if not user["verificado"]:
            raise EmailNotVerified(
                "El correo aún no está verificado. Revisa tu correo o solicita "
                "un nuevo enlace."
            )
        return self.repository.get_profile(user["nombre"])

    ## @brief Delega al repositorio la lectura del perfil histórico.
    ## @param name Nombre de la cuenta buscada.
    ## @return Perfil del jugador.
    def get_profile(self, name: str):
        # El repositorio forma estadísticas e historial desde SQLite.
        return self.repository.get_profile(name)

    ## @brief Crea y envía un enlace de un solo uso para el propósito indicado.
    ## @param identifier Nombre o correo asociado a la cuenta.
    ## @param purpose Tipo de enlace permitido.
    ## @return None.
    ## @throws InvalidInput Si el propósito no es conocido.
    ## @throws UserNotFound Si falta una cuenta al reenviar verificación.
    def send_email_link(self, identifier: str, purpose: str) -> None:
        # Limita los usos admitidos a verificación y recuperación.
        if purpose not in ("verificacion", "recuperacion"):
            raise InvalidInput("El tipo de enlace solicitado no es válido.")
        # Localiza la cuenta antes de generar un token.
        user = self.repository.find_user(identifier)
        if user is None:
            if purpose == "recuperacion":
                return
            raise UserNotFound("No se encontró la cuenta.")
        if purpose == "verificacion" and user["verificado"]:
            return

        # Genera un secreto aleatorio que el enlace entregará al destinatario.
        token = secrets.token_urlsafe(32)
        lifetime = (
            VERIFICATION_LINK_LIFETIME
            if purpose == "verificacion"
            else RECOVERY_LINK_LIFETIME
        )
        # Guarda solamente el hash y fecha de expiración antes del envío.
        self.repository.save_email_link(
            self._token_hash(token),
            user["nombre"],
            purpose,
            datetime.now(timezone.utc) + lifetime,
        )
        # Envía el token original al usuario por el canal de correo.
        self.email_service.send_link(user["email"], user["nombre"], token, purpose)

    ## @brief Activa el correo consumiendo su enlace de verificación.
    ## @param token Token original recibido en el enlace.
    ## @return None.
    ## @throws InvalidEmailLink Si venció, es inválido o ya fue utilizado.
    def verify_email(self, token: str) -> None:
        # El repositorio verifica y consume el hash en una única operación.
        name = self.repository.verify_email_link(self._token_hash(token))
        if name is None:
            raise InvalidEmailLink(
                "El enlace de verificación no es válido, venció o ya fue usado."
            )

    ## @brief Comprueba si un enlace de recuperación aún puede usarse.
    ## @param token Token original del enlace.
    ## @return True mientras exista un enlace válido sin expirar.
    def recovery_link_is_valid(self, token: str) -> bool:
        # Nunca envía ni persiste el token en claro en la base de datos.
        return self.repository.email_link_is_valid(
            self._token_hash(token), "recuperacion"
        )

    ## @brief Valida y guarda una contraseña nueva usando un enlace vigente.
    ## @param token Token de recuperación recibido por correo.
    ## @param password Nueva contraseña.
    ## @param confirmation Repetición de la contraseña nueva.
    ## @return None.
    ## @throws InvalidInput Si la contraseña no cumple reglas o no coincide.
    ## @throws InvalidEmailLink Si el token no existe, venció o ya se usó.
    def reset_password(
        self, token: str, password: str, confirmation: str
    ) -> None:
        # Reutiliza las reglas de longitud aplicadas durante el registro.
        self.validate_password(password)
        if password != confirmation:
            raise InvalidInput("Las contraseñas no coinciden.")
        # Crea una sal distinta para que el nuevo hash no reutilice la anterior.
        salt = secrets.token_bytes(16)
        updated = self.repository.reset_password(
            self._token_hash(token),
            salt.hex(),
            self._password_hash(password, salt),
        )
        # El repositorio devuelve False si el enlace no se pudo consumir.
        if not updated:
            raise InvalidEmailLink(
                "El enlace de recuperación no es válido, venció o ya fue usado."
            )

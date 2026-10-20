import pygame  # pyright: ignore[reportMissingImports]

from Boton import Boton
from SistemaUsuario import (
    CorreoPendiente,
    autenticar_usuario,
    cerrar_sesion,
    obtener_usuario,
    reenviar_verificacion,
    registrar_usuario,
    solicitar_recuperacion,
)


FONDO = (24, 24, 27)
TEXTO = (244, 244, 245)
TEXTO_SECUNDARIO = (161, 161, 170)
CAMPO = (39, 39, 42)
ERROR = (248, 113, 113)


class BaseScene:
    def __init__(self):
        self.window = None

    def handle_event(self, event):
        pass

    def update(self, mouse_pos):
        pass

    def draw(self, surface):
        pass


class CampoTexto:
    def __init__(self, etiqueta, y, oculto=False, max_length=256):
        self.etiqueta = etiqueta
        self.rect = pygame.Rect(250, y, 400, 42)
        self.texto = ""
        self.oculto = oculto
        self.max_length = max_length
        self.activo = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.activo = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.activo:
            if event.key == pygame.K_BACKSPACE:
                self.texto = self.texto[:-1]
            elif event.key == pygame.K_RETURN:
                self.activo = False
            elif event.unicode.isprintable() and len(self.texto) < self.max_length:
                self.texto += event.unicode

    def draw(self, surface, font, label_font):
        label = label_font.render(self.etiqueta, True, TEXTO)
        surface.blit(label, (self.rect.left, self.rect.top - 25))
        color = (96, 165, 250) if self.activo else (82, 82, 91)
        pygame.draw.rect(surface, CAMPO, self.rect, border_radius=5)
        pygame.draw.rect(surface, color, self.rect, 2, border_radius=5)
        visible_text = "*" * len(self.texto) if self.oculto else self.texto
        rendered = font.render(visible_text, True, TEXTO)
        surface.set_clip(self.rect.inflate(-12, -8))
        surface.blit(rendered, (self.rect.x + 8, self.rect.y + 9))
        surface.set_clip(None)


class MainMenuScene(BaseScene):
    def __init__(self, font):
        super().__init__()
        self.font = font
        self.title_font = pygame.font.SysFont("Segoe UI", 32, bold=True)
        self.small_font = pygame.font.SysFont("Segoe UI", 17)
        self.detail_font = pygame.font.SysFont("Segoe UI", 15)
        self.page = "welcome"
        self.fields = []
        self.buttons = []
        self.status = ""
        self.user_name = ""
        self.current_user = {}
        self.failed_attempts = 0
        self.last_login_identifier = ""
        self.profile_scroll = 0
        self._configure_page()

    def _button(self, x, y, width, text, callback):
        self.buttons.append(Boton(x, y, width, 46, text, self.font, callback))

    def _set_page(self, page):
        self.page = page
        self.status = ""
        self._configure_page()

    def _configure_page(self):
        self.fields = []
        self.buttons = []
        if self.page == "welcome":
            self._button(250, 260, 190, "Iniciar sesión", lambda: self._set_page("login"))
            self._button(460, 260, 190, "Crear cuenta", lambda: self._set_page("register"))
        elif self.page == "register":
            self.fields = [
                CampoTexto("Nombre de usuario", 145, max_length=40),
                CampoTexto("Correo electrónico", 215, max_length=254),
                CampoTexto("Contraseña (mínimo 8 caracteres)", 285, oculto=True),
                CampoTexto("Confirmar contraseña", 355, oculto=True),
            ]
            self._button(250, 455, 190, "Crear cuenta", self._registrar)
            self._button(460, 455, 190, "Volver", lambda: self._set_page("welcome"))
        elif self.page == "verify_pending":
            self._button(250, 365, 190, "Reenviar enlace", self._reenviar_verificacion)
            self._button(460, 365, 190, "Volver al inicio", lambda: self._set_page("welcome"))
        elif self.page == "email_error":
            self._button(250, 370, 190, "Reintentar envío", self._reenviar_verificacion)
            self._button(460, 370, 190, "Volver al inicio", lambda: self._set_page("welcome"))
        elif self.page == "login":
            self.fields = [
                CampoTexto("Usuario o correo electrónico", 210, max_length=254),
                CampoTexto("Contraseña", 285, oculto=True),
            ]
            self._button(250, 375, 190, "Entrar", self._iniciar_sesion)
            self._button(460, 375, 190, "Recuperar contraseña", self._abrir_recuperacion)
            self._button(355, 445, 190, "Volver", lambda: self._set_page("welcome"))
        elif self.page == "email_pending":
            self._button(250, 365, 190, "Reenviar enlace", self._reenviar_verificacion)
            self._button(460, 365, 190, "Volver al inicio", lambda: self._set_page("login"))
        elif self.page == "recovery_request":
            self.fields = [
                CampoTexto("Usuario o correo electrónico", 255, max_length=254)
            ]
            self._button(250, 345, 190, "Enviar enlace", self._solicitar_recuperacion)
            self._button(460, 345, 190, "Volver", lambda: self._set_page("login"))
        elif self.page == "recovery_sent":
            self._button(355, 390, 190, "Volver al inicio", lambda: self._set_page("login"))
        elif self.page == "menu":
            self._button(250, 270, 400, "Ver perfil", self._abrir_perfil)
            self._button(355, 355, 190, "Cerrar sesión", self._cerrar_sesion)
        elif self.page == "profile":
            self._button(355, 535, 190, "Volver al menú", lambda: self._set_page("menu"))

    def _mostrar_menu(self, nombre):
        self.user_name = nombre
        self._set_page("menu")

    def _registrar(self):
        nombre, correo, password, confirmation = (
            field.texto for field in self.fields
        )
        try:
            response = registrar_usuario(nombre, password, confirmation, correo)
        except (OSError, RuntimeError, ValueError) as error:
            self.status = str(error)
            return

        self.user_name = nombre.strip()
        if response.get("verification_sent") is True:
            message = (
                "Cuenta creada. Abre el enlace que enviamos a tu correo para "
                "activar la cuenta; después vuelve e inicia sesión."
            )
            self._set_page("verify_pending")
            self.status = message
        else:
            message = (
                "La cuenta se creó, pero el correo sigue sin verificar. "
                "No podrás iniciar sesión hasta activarlo. "
                + str(
                    response.get(
                        "email_error",
                        "No se pudo enviar el enlace de verificación.",
                    )
                )
            )
            self._set_page("email_error")
            self.status = message

    def _iniciar_sesion(self):
        identificador, password = (field.texto for field in self.fields)
        self.last_login_identifier = identificador.strip()
        try:
            profile = autenticar_usuario(identificador, password)
        except CorreoPendiente as error:
            self.user_name = identificador.strip()
            self._set_page("email_pending")
            self.status = str(error)
            return
        except (OSError, RuntimeError, ValueError) as error:
            self.status = str(error)
            return

        if profile is None:
            self.failed_attempts += 1
            if self.failed_attempts >= 3:
                self.failed_attempts = 0
                self._set_page("recovery_request")
                self.fields[0].texto = self.last_login_identifier
                self.status = "Fallaste tres veces. Puedes solicitar un enlace para recuperar tu contraseña."
            else:
                self.status = (
                    f"Usuario/correo o contraseña incorrectos. "
                    f"Intento {self.failed_attempts}/3."
                )
            return

        self.failed_attempts = 0
        self.current_user = profile
        self._mostrar_menu(str(profile["name"]))

    def _abrir_recuperacion(self):
        identifier = self.fields[0].texto.strip()
        self._set_page("recovery_request")
        self.fields[0].texto = identifier

    def _solicitar_recuperacion(self):
        identifier = self.fields[0].texto.strip()
        try:
            solicitar_recuperacion(identifier)
        except (OSError, RuntimeError, ValueError) as error:
            self.status = str(error)
            return
        self._set_page("recovery_sent")
        self.status = (
            "Si la cuenta existe, recibirás un enlace por correo. "
            "Ábrelo para definir una contraseña nueva."
        )

    def _reenviar_verificacion(self):
        try:
            reenviar_verificacion(self.user_name or self.last_login_identifier)
        except (OSError, RuntimeError, ValueError) as error:
            self.status = str(error)
            return
        self._set_page("verify_pending")
        self.status = (
            "Si la cuenta existe y aún no está verificada, se enviará un enlace. "
            "Revisa también la carpeta de spam."
        )

    def _abrir_perfil(self):
        try:
            self.current_user = obtener_usuario()
        except (OSError, RuntimeError, ValueError) as error:
            self.status = str(error)
            return
        self.profile_scroll = 0
        self._set_page("profile")

    def _cerrar_sesion(self):
        cerrar_sesion()
        self.current_user = {}
        self.user_name = ""
        self.failed_attempts = 0
        self._set_page("welcome")

    def _profile_lines(self):
        statistics = self.current_user.get("statistics", {})
        if not isinstance(statistics, dict):
            statistics = {}
        achievements = self.current_user.get("achievements", [])
        if not isinstance(achievements, list):
            achievements = []
        history = self.current_user.get("match_history", [])
        if not isinstance(history, list):
            history = []
        ranking = self.current_user.get("ranking")
        lines = [
            "Estadísticas históricas",
            f"Partidas: {statistics.get('matches_played', 0)}  |  "
            f"Victorias: {statistics.get('wins', 0)}  |  "
            f"Derrotas: {statistics.get('losses', 0)}  |  "
            f"Empates: {statistics.get('draws', 0)}",
            f"Ranking: {ranking if ranking is not None else 'Sin clasificación'}",
            "",
            "Logros",
        ]
        if achievements:
            lines.extend(f"• {achievement}" for achievement in achievements)
        else:
            lines.append("Aún no hay logros.")
        lines.extend(("", "Historial de partidas"))
        if history:
            for match in history:
                if not isinstance(match, dict):
                    continue
                lines.append(
                    f"{match.get('played_at', 'Fecha desconocida')} — "
                    f"{match.get('opponent', 'Oponente')} — "
                    f"{match.get('result', 'Sin resultado')} — "
                    f"Puntuación: {match.get('score', 0)}"
                )
        else:
            lines.append("Aún no hay partidas registradas.")
        return lines

    def handle_event(self, event):
        for field in self.fields:
            field.handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button in list(self.buttons):
                button.handle_event(event)
        if self.page == "profile" and event.type == pygame.MOUSEWHEEL:
            max_scroll = max(0, len(self._profile_lines()) - 14)
            self.profile_scroll = max(
                0, min(max_scroll, self.profile_scroll - event.y)
            )
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            if self.page == "register":
                self._registrar()
            elif self.page == "login":
                self._iniciar_sesion()
            elif self.page == "recovery_request":
                self._solicitar_recuperacion()

    def update(self, mouse_pos):
        return

    def _draw_centered(self, surface, text, y, font=None, color=TEXTO):
        rendered = (font or self.title_font).render(text, True, color)
        surface.blit(rendered, rendered.get_rect(center=(surface.get_width() // 2, y)))

    def _draw_message(self, surface, text, y, font, color, max_width=820):
        lines = []
        current_line = ""
        for word in text.split():
            candidate = f"{current_line} {word}".strip()
            if current_line and font.size(candidate)[0] > max_width:
                lines.append(current_line)
                current_line = word
            else:
                current_line = candidate
        if current_line:
            lines.append(current_line)
        line_height = font.get_linesize()
        first_y = y - (len(lines) - 1) * line_height // 2
        for index, line in enumerate(lines):
            self._draw_centered(
                surface, line, first_y + index * line_height, font, color
            )

    def _draw_profile(self, surface):
        verified = self.current_user.get("verificado") is True
        avatar = self.current_user.get("avatar")
        record = self.current_user.get("record", 0)
        self._draw_centered(surface, "Perfil del jugador", 70)
        self._draw_centered(
            surface, f"Nombre: {self.current_user.get('name', self.user_name)}",
            115, self.font
        )
        self._draw_centered(
            surface, f"Avatar: {avatar if avatar else 'null (sin avatar asignado)'}",
            145, self.font
        )
        self._draw_centered(
            surface, f"Correo: {'Verificado' if verified else 'Pendiente'}",
            175, self.font
        )
        self._draw_centered(
            surface, f"Puntuación máxima: {record}", 205, self.font
        )

        viewport = pygame.Rect(80, 230, 740, 285)
        surface.set_clip(viewport)
        for index, line in enumerate(self._profile_lines()[self.profile_scroll:]):
            color = TEXTO if line and not (
                line.startswith("Estadísticas")
                or line == "Logros"
                or line == "Historial de partidas"
            ) else TEXTO_SECUNDARIO
            rendered = self.detail_font.render(line, True, color)
            surface.blit(rendered, (viewport.x + 12, viewport.y + 8 + index * 20))
        surface.set_clip(None)

    def _draw_avatar_placeholder(self, surface, name, center_y):
        center = (surface.get_width() // 2, center_y)
        pygame.draw.circle(surface, (59, 130, 246), center, 32)
        initials = "".join(part[0] for part in name.split() if part)[:2].upper()
        rendered = self.title_font.render(initials, True, TEXTO)
        surface.blit(rendered, rendered.get_rect(center=center))

    def draw(self, surface):
        surface.fill(FONDO)
        if self.page == "welcome":
            self._draw_centered(surface, "Battle Arena Challenge", 165)
            self._draw_centered(
                surface, "Inicia sesión o crea una cuenta.", 215,
                self.font, TEXTO_SECUNDARIO
            )
        elif self.page == "register":
            self._draw_centered(surface, "Crear cuenta", 85)
        elif self.page == "verify_pending":
            self._draw_centered(surface, "Verifica tu correo", 210)
            self._draw_message(
                surface,
                "La cuenta aún no está activa. Abre el enlace enviado por correo "
                "y luego inicia sesión.",
                275, self.small_font, TEXTO_SECUNDARIO,
            )
        elif self.page == "email_error":
            self._draw_centered(surface, "No se pudo enviar el enlace", 205)
            self._draw_message(
                surface, self.status, 275, self.small_font, TEXTO_SECUNDARIO
            )
        elif self.page == "login":
            self._draw_centered(surface, "Iniciar sesión", 130)
        elif self.page == "email_pending":
            self._draw_centered(surface, "Correo sin verificar", 205)
            self._draw_message(
                surface, self.status, 275, self.small_font, TEXTO_SECUNDARIO
            )
        elif self.page == "recovery_request":
            self._draw_centered(surface, "Recuperar contraseña", 175)
            self._draw_centered(
                surface, "Te enviaremos un enlace si la cuenta existe.",
                215, self.small_font, TEXTO_SECUNDARIO
            )
        elif self.page == "recovery_sent":
            self._draw_centered(surface, "Revisa tu correo", 230)
            self._draw_message(
                surface, self.status, 295, self.small_font, TEXTO_SECUNDARIO
            )
        elif self.page == "menu":
            self._draw_centered(surface, f"Hola, {self.user_name}", 190)
            self._draw_avatar_placeholder(surface, self.user_name, 242)
            self._draw_centered(
                surface, "Tu sesión está activa.", 285,
                self.font, TEXTO_SECUNDARIO
            )
        elif self.page == "profile":
            self._draw_profile(surface)

        for field in self.fields:
            field.draw(surface, self.font, self.small_font)
        for button in self.buttons:
            button.draw(surface, pygame.mouse.get_pos())
        if self.status and self.page not in (
            "verify_pending", "email_error", "email_pending",
            "recovery_sent",
        ):
            self._draw_message(surface, self.status, 555, self.small_font, ERROR)

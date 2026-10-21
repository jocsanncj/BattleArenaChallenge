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


# Colores compartidos por los fondos, textos y errores de las escenas.
FONDO = (24, 24, 27)
TEXTO = (244, 244, 245)
TEXTO_SECUNDARIO = (161, 161, 170)
CAMPO = (39, 39, 42)
ERROR = (248, 113, 113)


## @brief Clase base con interfaz común para pantallas Pygame.
class BaseScene:
    ## @brief Define la interfaz mínima que espera la ventana para una escena.
    ## Las escenas concretas pueden sobrescribir los métodos vacíos.
    def __init__(self):
        # Se asigna cuando Window.set_scene activa esta escena.
        self.window = None

    ## @brief Recibe eventos de Pygame; las clases hijas implementan acciones.
    ## @param event Evento de teclado, ratón o ventana.
    ## @return None.
    def handle_event(self, event):
        # Método intencionalmente vacío para ofrecer una interfaz común.
        pass

    ## @brief Actualiza el estado de la escena en cada fotograma.
    ## @param mouse_pos Posición actual del cursor.
    ## @return None.
    def update(self, mouse_pos):
        # Método base sin animaciones ni actualizaciones predeterminadas.
        pass

    ## @brief Dibuja la escena en la superficie proporcionada.
    ## @param surface Superficie de Pygame que recibirá el dibujo.
    ## @return None.
    def draw(self, surface):
        # Método base vacío; la escena concreta debe dibujar sus elementos.
        pass


## @brief Campo editable con soporte opcional para ocultar texto sensible.
class CampoTexto:
    ## @brief Crea un campo de texto editable para las pantallas de cuenta.
    ## @param etiqueta Texto explicativo situado encima del campo.
    ## @param y Posición vertical del rectángulo.
    ## @param oculto Si True, muestra asteriscos en lugar del texto.
    ## @param max_length Cantidad máxima de caracteres permitidos.
    def __init__(self, etiqueta, y, oculto=False, max_length=256):
        # Guarda la etiqueta y coloca el campo en el centro de la ventana.
        self.etiqueta = etiqueta
        self.rect = pygame.Rect(250, y, 400, 42)
        # Inicia el valor sin texto introducido.
        self.texto = ""
        # Conserva las reglas visuales del campo.
        self.oculto = oculto
        self.max_length = max_length
        self.activo = False

    ## @brief Actualiza el contenido o foco del campo según el evento recibido.
    ## @param event Evento de Pygame que se procesa.
    ## @return None.
    def handle_event(self, event):
        # Un clic izquierdo activa el campo seleccionado y desactiva los demás.
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.activo = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.activo:
            # Retroceso elimina el último carácter cuando el campo tiene foco.
            if event.key == pygame.K_BACKSPACE:
                self.texto = self.texto[:-1]
            # Enter termina la edición del campo.
            elif event.key == pygame.K_RETURN:
                self.activo = False
            # Añade solo caracteres imprimibles y no supera el límite configurado.
            elif event.unicode.isprintable() and len(self.texto) < self.max_length:
                self.texto += event.unicode

    ## @brief Dibuja etiqueta, borde, fondo y contenido visible del campo.
    ## @param surface Superficie de Pygame sobre la que se dibuja.
    ## @param font Fuente utilizada para el texto introducido.
    ## @param label_font Fuente utilizada para la etiqueta.
    ## @return None.
    def draw(self, surface, font, label_font):
        # Renderiza y coloca la etiqueta encima del rectángulo.
        label = label_font.render(self.etiqueta, True, TEXTO)
        surface.blit(label, (self.rect.left, self.rect.top - 25))
        # Resalta el borde azul cuando el control tiene foco.
        color = (96, 165, 250) if self.activo else (82, 82, 91)
        pygame.draw.rect(surface, CAMPO, self.rect, border_radius=5)
        pygame.draw.rect(surface, color, self.rect, 2, border_radius=5)
        # En campos sensibles se dibuja un asterisco por cada carácter.
        visible_text = "*" * len(self.texto) if self.oculto else self.texto
        rendered = font.render(visible_text, True, TEXTO)
        # Recorta el texto al área interior para que no sobresalga del campo.
        surface.set_clip(self.rect.inflate(-12, -8))
        surface.blit(rendered, (self.rect.x + 8, self.rect.y + 9))
        surface.set_clip(None)


## @brief Gestiona la navegación y presentación de las pantallas de usuario.
class MainMenuScene(BaseScene):
    ## @brief Prepara las pantallas de bienvenida, cuenta, sesión y perfil.
    ## @param font Fuente principal compartida por controles y textos.
    def __init__(self, font):
        # Inicializa la referencia a ventana heredada de BaseScene.
        super().__init__()
        # Conserva fuentes de diferentes tamaños para la interfaz.
        self.font = font
        self.title_font = pygame.font.SysFont("Segoe UI", 32, bold=True)
        self.small_font = pygame.font.SysFont("Segoe UI", 17)
        self.detail_font = pygame.font.SysFont("Segoe UI", 15)
        # Comienza mostrando la pantalla de bienvenida.
        self.page = "welcome"
        # Inicializa colecciones de controles que cambian según la página.
        self.fields = []
        self.buttons = []
        self.status = ""
        self.user_name = ""
        self.current_user = {}
        # Lleva la cuenta local de fallos consecutivos de inicio de sesión.
        self.failed_attempts = 0
        self.last_login_identifier = ""
        self.profile_scroll = 0
        # Crea los botones y campos iniciales para la pantalla de bienvenida.
        self._configure_page()

    ## @brief Crea y registra un botón en la colección de la página activa.
    ## @param x Coordenada horizontal del control.
    ## @param y Coordenada vertical del control.
    ## @param width Ancho del control.
    ## @param text Etiqueta visible del botón.
    ## @param callback Acción ejecutada al hacer clic.
    ## @return None.
    def _button(self, x, y, width, text, callback):
        # Usa la altura común de botones y la fuente principal de la interfaz.
        self.buttons.append(Boton(x, y, width, 46, text, self.font, callback))

    ## @brief Cambia la página y reconstruye sus controles.
    ## @param page Identificador interno de pantalla.
    ## @return None.
    def _set_page(self, page):
        # Guarda la pantalla que determinará dibujo, campos y navegación.
        self.page = page
        # Elimina mensajes de estado pertenecientes a la página anterior.
        self.status = ""
        # Configura los controles correspondientes a la nueva pantalla.
        self._configure_page()

    ## @brief Configura campos y botones según el identificador de pantalla.
    ## @return None.
    def _configure_page(self):
        # Descarta los controles previos para evitar mostrar los de otra pantalla.
        self.fields = []
        self.buttons = []
        # Cada rama construye la navegación y formulario de una pantalla.
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
                CampoTexto("Correo electrónico", 210, max_length=254),
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
                CampoTexto("Correo electrónico", 255, max_length=254)
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

    ## @brief Guarda el nombre y navega al menú luego de autenticar.
    ## @param nombre Nombre de la cuenta que inició sesión.
    ## @return None.
    def _mostrar_menu(self, nombre):
        # El nombre se utiliza para saludar al usuario en la pantalla principal.
        self.user_name = nombre
        self._set_page("menu")

    ## @brief Envía el formulario de registro y muestra el resultado al usuario.
    ## @return None.
    def _registrar(self):
        # Extrae los cuatro campos en el orden configurado para el registro.
        nombre, correo, password, confirmation = (
            field.texto for field in self.fields
        )
        # Delega validación y creación al cliente HTTP.
        try:
            response = registrar_usuario(nombre, password, confirmation, correo)
        except (OSError, RuntimeError, ValueError) as error:
            self.status = str(error)
            return

        # Conserva el correo para permitir reenviar la verificación de Firebase.
        self.user_name = correo.strip()
        # Diferencia entre el alta correcta y el envío fallido del correo.
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

    ## @brief Envía credenciales e interpreta éxito, errores y fallos consecutivos.
    ## @return None.
    def _iniciar_sesion(self):
        # Lee el identificador y contraseña de los campos visibles.
        identificador, password = (field.texto for field in self.fields)
        # Guarda el identificador para recuperación o reenvío posteriores.
        self.last_login_identifier = identificador.strip()
        # El adaptador convierte credenciales inválidas y correo pendiente en casos distintos.
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

        # None indica credenciales incorrectas; se cuentan hasta ofrecer recuperación.
        if profile is None:
            self.failed_attempts += 1
            if self.failed_attempts >= 3:
                # Una autenticación correcta reinicia el contador de errores.
                self.failed_attempts = 0
                self._set_page("recovery_request")
                self.fields[0].texto = self.last_login_identifier
                self.status = "Fallaste tres veces. Puedes solicitar un enlace para recuperar tu contraseña."
            else:
                self.status = (
                    f"Correo o contraseña incorrectos. "
                    f"Intento {self.failed_attempts}/3."
                )
            return

        self.failed_attempts = 0
        self.current_user = profile
        self._mostrar_menu(str(profile["name"]))

    ## @brief Abre la pantalla de solicitud de recuperación con el identificador escrito.
    ## @return None.
    def _abrir_recuperacion(self):
        # Preserva el identificador si el jugador ya lo escribió en login.
        identifier = self.fields[0].texto.strip()
        self._set_page("recovery_request")
        self.fields[0].texto = identifier

    ## @brief Envía una solicitud de recuperación y muestra una respuesta genérica.
    ## @return None.
    def _solicitar_recuperacion(self):
        # Lee el correo ingresado.
        identifier = self.fields[0].texto.strip()
        # Pide al backend enviar un enlace, mostrando errores de red al jugador.
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

    ## @brief Solicita reenviar la verificación al usuario de la pantalla actual.
    ## @return None.
    def _reenviar_verificacion(self):
        # Usa el nombre guardado o el último identificador de inicio de sesión.
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

    ## @brief Solicita datos actualizados y abre la pantalla de perfil.
    ## @return None.
    def _abrir_perfil(self):
        # Recupera el perfil protegido por el token de sesión local.
        try:
            self.current_user = obtener_usuario()
        except (OSError, RuntimeError, ValueError) as error:
            self.status = str(error)
            return
        self.profile_scroll = 0
        self._set_page("profile")

    ## @brief Borra el estado de sesión y regresa a la bienvenida.
    ## @return None.
    def _cerrar_sesion(self):
        # Elimina el token almacenado por el adaptador HTTP.
        cerrar_sesion()
        self.current_user = {}
        self.user_name = ""
        self.failed_attempts = 0
        self._set_page("welcome")

    ## @brief Prepara estadísticas, logros e historial en líneas de texto.
    ## @return Lista de líneas que se dibujarán dentro del área desplazable.
    def _profile_lines(self):
        # Comprueba la forma de los datos remotos antes de usarlos en la UI.
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
        # Construye primero el resumen general y los encabezados del perfil.
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
        # Añade logros o un texto que indique que todavía no hay ninguno.
        if achievements:
            lines.extend(f"• {achievement}" for achievement in achievements)
        else:
            lines.append("Aún no hay logros.")
        lines.extend(("", "Historial de partidas"))
        # Añade cada partida válida o informa que el historial está vacío.
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

    ## @brief Distribuye eventos a campos, botones y navegación por teclado/rueda.
    ## @param event Evento recibido por la ventana de Pygame.
    ## @return None.
    def handle_event(self, event):
        # Delega cada evento a los campos visibles para mantener el foco correcto.
        for field in self.fields:
            field.handle_event(event)
        # Los botones solo reaccionan a clic izquierdo.
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button in list(self.buttons):
                button.handle_event(event)
        # La rueda desplaza las líneas dentro del perfil sin mover otros paneles.
        if self.page == "profile" and event.type == pygame.MOUSEWHEEL:
            max_scroll = max(0, len(self._profile_lines()) - 14)
            self.profile_scroll = max(
                0, min(max_scroll, self.profile_scroll - event.y)
            )
        # Enter ejecuta la acción principal de los formularios correspondientes.
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            if self.page == "register":
                self._registrar()
            elif self.page == "login":
                self._iniciar_sesion()
            elif self.page == "recovery_request":
                self._solicitar_recuperacion()

    ## @brief Actualiza la escena; no se requieren animaciones por ahora.
    ## @param mouse_pos Posición actual del cursor.
    ## @return None.
    def update(self, mouse_pos):
        # El método se conserva para cumplir la interfaz común de BaseScene.
        return

    ## @brief Dibuja una línea de texto alineada al centro de la superficie.
    ## @param surface Superficie de destino.
    ## @param text Texto que se va a renderizar.
    ## @param y Coordenada vertical del centro del texto.
    ## @param font Fuente opcional; usa la tipografía de título si falta.
    ## @param color Color RGB del texto.
    ## @return None.
    def _draw_centered(self, surface, text, y, font=None, color=TEXTO):
        # Renderiza el texto y calcula su rectángulo centrado en la pantalla.
        rendered = (font or self.title_font).render(text, True, color)
        surface.blit(rendered, rendered.get_rect(center=(surface.get_width() // 2, y)))

    ## @brief Ajusta el mensaje al ancho permitido y centra sus líneas.
    ## @param surface Superficie donde se dibuja el mensaje.
    ## @param text Mensaje largo que se debe distribuir.
    ## @param y Centro vertical aproximado del bloque.
    ## @param font Fuente usada para medir y renderizar.
    ## @param color Color de las líneas.
    ## @param max_width Ancho máximo de cada línea en píxeles.
    ## @return None.
    def _draw_message(self, surface, text, y, font, color, max_width=820):
        # Acumula palabras hasta que agregar otra excedería el ancho configurado.
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
        # Calcula la altura total y el inicio para centrar verticalmente el bloque.
        line_height = font.get_linesize()
        first_y = y - (len(lines) - 1) * line_height // 2
        for index, line in enumerate(lines):
            self._draw_centered(
                surface, line, first_y + index * line_height, font, color
            )

    ## @brief Dibuja identidad y datos históricos dentro de un área desplazable.
    ## @param surface Superficie donde se dibuja el perfil.
    ## @return None.
    def _draw_profile(self, surface):
        # Lee el estado de verificación, avatar y récord del perfil actual.
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

        # Limita estadísticas e historial a una ventana gráfica desplazable.
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

    ## @brief Dibuja el avatar temporal con las iniciales del usuario.
    ## @param surface Superficie donde se dibuja el avatar.
    ## @param name Nombre usado para obtener iniciales.
    ## @param center_y Coordenada vertical del círculo.
    ## @return None.
    def _draw_avatar_placeholder(self, surface, name, center_y):
        # Ubica el círculo en el centro horizontal de la ventana.
        center = (surface.get_width() // 2, center_y)
        pygame.draw.circle(surface, (59, 130, 246), center, 32)
        # Usa como máximo dos iniciales y evita elementos vacíos del nombre.
        initials = "".join(part[0] for part in name.split() if part)[:2].upper()
        rendered = self.title_font.render(initials, True, TEXTO)
        surface.blit(rendered, rendered.get_rect(center=center))

    ## @brief Dibuja el fondo, contenido de la página y controles activos.
    ## @param surface Superficie entregada por el ciclo de la ventana.
    ## @return None.
    def draw(self, surface):
        # Limpia el contenido anterior para empezar un nuevo fotograma.
        surface.fill(FONDO)
        # Dibuja el contenido principal según la página activa.
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

        # Dibuja los campos y botones que se configuraron para esta pantalla.
        for field in self.fields:
            field.draw(surface, self.font, self.small_font)
        for button in self.buttons:
            button.draw(surface, pygame.mouse.get_pos())
        # Muestra mensajes breves abajo, evitando duplicar pantallas de estado.
        if self.status and self.page not in (
            "verify_pending", "email_error", "email_pending",
            "recovery_sent",
        ):
            self._draw_message(surface, self.status, 555, self.small_font, ERROR)

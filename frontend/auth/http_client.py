"""Capa de infraestructura del cliente: habla con Firebase Auth y con el servidor del juego."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from dotenv import load_dotenv
load_dotenv()
# ---------------------------------------------------------------- errores
class AuthError(RuntimeError):
    """Error base de autenticación; su mensaje se puede mostrar al usuario."""
class CredencialesInvalidas(AuthError):
    """Usuario, correo o contraseña incorrectos."""
class CorreoPendiente(AuthError):
    """La cuenta existe pero su correo aún no está verificado."""


class PerfilNoEncontrado(AuthError):
    """La cuenta está autenticada, pero todavía no tiene perfil en el juego."""

MENSAJES_FIREBASE = {
    "EMAIL_EXISTS": "Ese correo ya tiene una cuenta.",
    "INVALID_EMAIL": "La dirección de correo no es válida.",
    "WEAK_PASSWORD": "La contraseña es demasiado débil.",
    "USER_DISABLED": "Esta cuenta fue deshabilitada.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Demasiados intentos. Espera un momento.",
    "OPERATION_NOT_ALLOWED": "Activa Correo/contraseña en Firebase Authentication.",
    "API_KEY_INVALID": "Falta una API key válida en FIREBASE_API_KEY.",
}
CODIGOS_CREDENCIALES = {"INVALID_PASSWORD", "INVALID_LOGIN_CREDENTIALS", "EMAIL_NOT_FOUND"}
# ------------------------------------------------------------- HTTP común
class _ErrorHttp(Exception):
    """Respuesta HTTP de error; guarda el cuerpo JSON para que lo interprete el adaptador."""
    # Guarda por separado el estado HTTP y el JSON de error. El cliente usa el 404 de /api/profile para reconocer un primer ingreso.
    ## @brief Guarda el cuerpo y el código de una respuesta HTTP de error.
    def __init__(self, cuerpo: dict, estado: int):
        super().__init__("error HTTP")
        self.cuerpo = cuerpo
        self.estado = estado

## @brief Convierte bytes JSON en un diccionario o devuelve un objeto vacío si no es válido.
def _json(datos: bytes) -> dict:
    try:
        resultado = json.loads(datos.decode("utf-8"))
    except ValueError:
        return {}
    return resultado if isinstance(resultado, dict) else {}

## @brief US-01–US-31: envía una petición HTTP y normaliza errores de red y respuesta.
def _enviar(request: Request, timeout: int = 15) -> dict:
    """Ejecuta la petición y devuelve el JSON de la respuesta."""
    try:
        with urlopen(request, timeout=timeout) as respuesta:
            datos = respuesta.read()
    except HTTPError as error:
        # Conserva el código HTTP para que el cliente pueda reconocer el 404 de un perfil nuevo.
        raise _ErrorHttp(_json(error.read()), error.code) from error
    except (URLError, TimeoutError, OSError) as error:
        raise AuthError(f"No se pudo conectar con el servicio: {error}") from error
    return _json(datos)

# ------------------------------------------------------------- adaptadores
class FirebaseAuth:
    """Adaptador de la API REST de Firebase Auth (implementa ProveedorIdentidad)."""
    URL = "https://identitytoolkit.googleapis.com/v1/accounts:"
    URL_TOKEN = "https://securetoken.googleapis.com/v1/token"
    ## @brief Lee la clave de API de Firebase y falla si no está configurada.
    @staticmethod
    def _key() -> str:
        key = os.getenv("FIREBASE_API_KEY", "").strip()
        if not key:
            raise AuthError("Configura FIREBASE_API_KEY en el archivo .env.")
        return key
    ## @brief US-01–US-05 y US-29: llama un método REST de Firebase Auth.
    def _llamar(self, accion: str, datos: dict) -> dict:
        request = Request(
            f"{self.URL}{accion}?key={self._key()}",
            json.dumps(datos).encode("utf-8"),
            {"Content-Type": "application/json"},
            method="POST",
        )
        try:
            return _enviar(request)
        except _ErrorHttp as error:
            detalle = error.cuerpo.get("error")
            mensaje = detalle.get("message", "") if isinstance(detalle, dict) else ""
            codigo = mensaje.split(" : ")[0] or "ERROR"
            if codigo in CODIGOS_CREDENCIALES:
                raise CredencialesInvalidas("Usuario/correo o contraseña incorrectos.") from error
            raise AuthError(
                MENSAJES_FIREBASE.get(codigo, f"Firebase rechazó la solicitud ({codigo}).")
            ) from error
    ## @brief US-01: crea una cuenta de Firebase con correo y contraseña.
    def registrar(self, correo, password):
        return self._llamar("signUp", {"email": correo, "password": password,"returnSecureToken": True})
    ## @brief US-03: inicia sesión en Firebase con correo y contraseña.
    def iniciar_sesion(self, correo, password):
        return self._llamar("signInWithPassword", {"email": correo, "password": password,"returnSecureToken": True})

    def iniciar_sesion_google(self, credencial: str) -> dict:
        """Canjea la credencial de Google por los tokens de Firebase que usa la API del juego."""
        # Firebase espera el proveedor y el access token en postBody. La respuesta aporta un idToken para el servidor del juego
        # y un refreshToken para renovar el acceso sin volver a abrir el navegador.
        return self._llamar("signInWithIdp", {
            "requestUri": "http://localhost",
            "postBody": urlencode({"providerId": "google.com", "access_token": credencial}),
            "returnSecureToken": True,
        })
    ## @brief US-03–US-04: renueva los tokens de una sesión de Firebase.
    def renovar(self, refresh_token):
        form = urlencode({"grant_type": "refresh_token", "refresh_token": refresh_token})
        request = Request(f"{self.URL_TOKEN}?key={self._key()}", form.encode("utf-8"),{"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            r = _enviar(request)
        except _ErrorHttp as error:
            raise AuthError("No se pudo renovar la sesión. Inicia sesión de nuevo.") from error
        if not r.get("id_token") or not r.get("refresh_token"):
            raise AuthError("Firebase devolvió una sesión inválida.")
        return {"idToken": r["id_token"], "refreshToken": r["refresh_token"]}
    ## @brief US-02–US-04: consulta a Firebase los datos de la cuenta autenticada.
    def datos_cuenta(self, id_token):
        usuarios = self._llamar("lookup", {"idToken": id_token}).get("users")
        if not usuarios:
            raise AuthError("Firebase no devolvió los datos de la cuenta.")
        return usuarios[0]
    ## @brief US-01: asigna el nombre visible de la cuenta de Firebase.
    def poner_nombre(self, id_token, nombre):
        self._llamar("update", {"idToken": id_token, "displayName": nombre})
    ## @brief US-02: solicita a Firebase el correo de verificación.
    def enviar_verificacion(self, id_token):
        self._llamar("sendOobCode", {"requestType": "VERIFY_EMAIL", "idToken": id_token})
    ## @brief US-05: solicita el correo de restablecimiento de contraseña.
    def enviar_recuperacion(self, correo):
        self._llamar("sendOobCode", {"requestType": "PASSWORD_RESET", "email": correo})

class ClienteServidor:
    """Adaptador del servidor del juego (implementa ApiPerfiles)."""
    ## @brief Configura la dirección base de la API del juego.
    def __init__(self, url: str | None = None):
        self.url = (url or os.getenv("BATTLE_ARENA_SERVER", "http://127.0.0.1:8000")).rstrip("/")
    # Añade el token de Firebase como cabecera Bearer cuando la ruta lo necesita. Los datos de entrada viajan como JSON;
    # el servicio recibe el JSON de respuesta o una excepción cuyo tipo distingue un perfil inexistente.
    ## @brief US-01–US-31: ejecuta una petición autenticada a la API Flask.
    def _llamar(self, metodo, ruta, token=None, cuerpo=None, **params) -> dict:
        url = self.url + ruta + (f"?{urlencode(params)}" if params else "")
        cabeceras = {"Accept": "application/json"}
        if token:
            cabeceras["Authorization"] = f"Bearer {token}"
        datos = None
        if cuerpo is not None:
            datos = json.dumps(cuerpo).encode("utf-8")
            cabeceras["Content-Type"] = "application/json"
        try:
            return _enviar(Request(url, datos, cabeceras, method=metodo), timeout=10)
        except _ErrorHttp as error:
            # Solo este 404 permite a US29 crear el perfil de primer ingreso. Un fallo de red debe llegar al menú.
            if metodo == "GET" and ruta == "/api/profile" and error.estado == 404:
                raise PerfilNoEncontrado("No existe el perfil del jugador.") from error
            raise AuthError(str(error.cuerpo.get("error", "El servidor rechazó la solicitud."))) from error
    ## @brief Valida y extrae el objeto de perfil de la respuesta de la API.
    @staticmethod
    def _perfil(respuesta: dict) -> dict:
        perfil = respuesta.get("user")
        if not isinstance(perfil, dict):
            raise AuthError("El servidor devolvió un perfil inválido.")
        return perfil
    ## @brief US-01: consulta si un nombre de usuario está disponible.
    def nombre_disponible(self, nombre):
        return bool(self._llamar("GET", "/api/disponible", nombre=nombre).get("disponible"))
    ## @brief US-03 y US-05: busca el correo asociado al nombre de usuario.
    def correo_de(self, nombre):
        return self._llamar("GET", "/api/correo", nombre=nombre).get("correo")
    ## @brief US-01 y US-04: crea o actualiza el perfil del usuario.
    def guardar_perfil(self, token, nombre):
        return self._perfil(self._llamar("POST", "/api/profile", token, {"name": nombre}))
    ## @brief US-04: obtiene perfil, estadísticas, logros e historial del jugador.
    def obtener_perfil(self, token):
        return self._perfil(self._llamar("GET", "/api/profile", token))
    # CAMBIO ONLINE: persistencia compartida de avatares y sala en el servidor Docker.
    ## @brief US-06: consulta la elección de avatar persistida en el servidor.
    def obtener_avatar(self, token, id_usuario):
        return self._llamar("GET", "/api/game/avatar", token, id=int(id_usuario)).get("avatar")
    ## @brief US-06: guarda la elección de avatar del jugador autenticado.
    def guardar_avatar(self, token, eleccion):
        return self._llamar("PUT", "/api/game/avatar", token, eleccion)
    ## @brief US-09–US-31: consulta la sala, el estado de juego y el mapa.
    def obtener_partida(self, token):
        return self._llamar("GET", "/api/game/state", token)
    ## @brief US-09–US-10: solicita unirse a la sala online.
    def unirse_partida(self, token):
        return self._llamar("POST", "/api/game/join", token)
    ## @brief US-10: solicita salir o desconectarse de la sala.
    def salir_partida(self, token):
        return self._llamar("POST", "/api/game/leave", token)
    ## @brief US-09: solicita iniciar la partida cuando se cumple el mínimo de jugadores.
    def iniciar_partida(self, token):
        return self._llamar("POST", "/api/game/start", token)
    ## @brief US-11: envía una dirección de movimiento para validación del servidor.
    def mover_jugador(self, token, direccion):
        return self._llamar("POST", "/api/game/move", token, {"direction": direccion})
    ## @brief US-18–US-19: inicia o cancela una interacción identificada con el reactor.
    def interactuar_reactor(self, token, accion, event_id):
        return self._llamar(
            "POST",
            "/api/game/reactor",
            token,
            {"action": accion, "event_id": event_id},
        )
    ## @brief US-08 y US-23: solicita guardar la configuración de sala.
    def guardar_configuracion_partida(self, token, configuracion):
        return self._llamar("PUT", "/api/game/config", token, configuracion)
    ## @brief US-27: obtiene y valida la lista del ranking global.
    def obtener_ranking(self):
        ranking = self._llamar("GET", "/api/ranking").get("ranking")
        if not isinstance(ranking, list):
            raise AuthError("El servidor devolvió un ranking inválido.")
        return ranking

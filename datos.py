"""
CAPA DE DATOS: modelos y persistencia en archivos JSON

Este módulo es la única parte del programa que sabe cómo se guardan los datos.
Define los modelos (qué información existe) y los repositorios (cómo se lee y se
escribe esa información en disco). El resto del sistema trabaja solo con las
clases abstractas Repositorio..., por lo que cambiar JSON por otra tecnología
(base de datos, servidor) no obliga a modificar la lógica ni la interfaz.

Archivos que se crean solos junto al código:
    avatares.json  ->  avatar elegido por cada jugador (predeterminado o imagen
                       personalizada codificada en base64).
    partida.json   ->  configuración, estado, hora de inicio y jugadores de la sala.

Estructura del archivo:
    1. Librerías
    2. Constantes
    3. Modelos de datos (EleccionAvatar, ConfiguracionPartida, Jugador, Partida)
    4. Acceso seguro a un archivo JSON (_ArchivoJson)
    5. Repositorio de avatares (abstracto + JSON)
    6. Repositorio de la partida (abstracto + JSON)
"""


# 1. LIBRERÍAS

# Librerías estándar de Python (vienen incluidas, no hay que instalarlas)

# json: convierte los diccionarios a texto y viceversa para guardarlos en archivos .json,
# un formato legible por personas y fácil de compartir entre ejecuciones.
import json

# os: arma rutas que funcionan en cualquier sistema (os.path), comprueba si un archivo
# existe y reemplaza archivos de forma atómica (os.replace).
import os

# time: pausas muy cortas (time.sleep) para reintentar cuando otro programa tiene
# el archivo ocupado en ese momento.
import time

# abc (ABC, abstractmethod): permite definir los repositorios como contratos abstractos,
# de modo que el resto del sistema no dependa de JSON.
from abc import ABC, abstractmethod

# dataclasses (asdict, dataclass, field): crean los modelos sin escribir código repetitivo
# (constructor, comparación, texto); asdict convierte un modelo en diccionario para
# guardarlo en JSON y field(default_factory=...) da listas/objetos por defecto
# independientes para cada instancia.
from dataclasses import asdict, dataclass, field

# typing (List, Optional): anotaciones de tipo que documentan qué recibe y devuelve cada
# función; Optional indica que el valor también puede ser None.
from typing import List, Optional

# Carpeta donde está este archivo. Los JSON se guardan aquí y no en el directorio desde
# donde se ejecuta el comando, para que todos los jugadores lean los mismos archivos.
_CARPETA = os.path.dirname(os.path.abspath(__file__))


@dataclass(frozen=True)
class EleccionAvatar:
    """
    Descripción:
        Modelo inmutable que representa el avatar que un jugador eligió. Al ser
        'frozen' no se puede modificar después de creado: para cambiar de avatar se
        crea una elección nueva y se guarda en el repositorio.
    Atributos:
        tipo (str): 'predeterminado' si eligió uno del catálogo, o 'personalizado' si subió
            una imagen propia.
        valor (str): el identificador del avatar predeterminado (por ejemplo 'avatar_3'),
            o la imagen subida convertida a texto en base64 cuando es personalizado.
    """

    tipo: str
    valor: str


@dataclass
class ConfiguracionPartida:
    """
    Descripción:
        Modelo con las reglas que el usuario puede configurar antes de iniciar una
        partida. Cada atributo tiene un valor por defecto, de modo que siempre existe
        una configuración válida aunque nadie haya configurado nada todavía.
    Atributos:
        modo_fin (str): cómo termina la partida. 'tiempo' = por tiempo, 'puntos' = por
            puntos. Por defecto 'tiempo'.
        minutos_fin (int): duración en minutos cuando el modo es 'tiempo'. Por defecto 5.
        puntos_fin (int): puntos necesarios para ganar cuando el modo es 'puntos'.
            Por defecto 20.
        segundos_congelacion (int): segundos que un jugador queda congelado al ser
            alcanzado por el arma paralizadora. Por defecto 3.
    """

    modo_fin: str = "tiempo"
    minutos_fin: int = 5
    puntos_fin: int = 20
    segundos_congelacion: int = 3


@dataclass(frozen=True)
class Jugador:
    """
    Descripción:
        Modelo inmutable de un jugador que está dentro de la sala de la partida.
    Atributos:
        id_usuario (int): identificador único del usuario.
        nombre_usuario (str): nombre que se muestra en pantalla.
        indice_inicio (int): posición (empezando en 0) del punto de inicio de la arena
            que le corresponde a este jugador.
    """

    id_usuario: int
    nombre_usuario: str
    indice_inicio: int


@dataclass
class Partida:
    """
    Descripción:
        Modelo de la partida o sala única del juego. Agrupa la configuración, el estado
        actual y los jugadores. Es el objeto que se guarda completo en partida.json y
        al que se le pueden ir agregando campos (puntaje, ganador, etc.).
    Atributos:
        configuracion (ConfiguracionPartida): reglas de la partida. Se crea con los
            valores por defecto si no se indica otra.
        estado (str): 'esperando' mientras los jugadores se reúnen, 'jugando' cuando
            ya inició.
        iniciada_en (Optional[float]): momento exacto de inicio (segundos desde la
            época, como time.time()); None mientras no haya iniciado. Sirve para calcular
            el temporizador.
        jugadores (List[Jugador]): jugadores que están en la sala, en orden de llegada.
    """

    configuracion: ConfiguracionPartida = field(default_factory=ConfiguracionPartida)
    estado: str = "esperando"
    iniciada_en: Optional[float] = None
    jugadores: List[Jugador] = field(default_factory=list)


class _ArchivoJson:
    """
    Descripción:
        Herramienta interna que lee y escribe un diccionario en un archivo JSON de forma
        segura. Existe porque varios programas (uno por jugador) pueden acceder al mismo
        archivo casi al mismo tiempo, y un acceso ingenuo podría leer un archivo a medio
        escribir o fallar en Windows. Por eso la lectura reintenta y la escritura es
        atómica.
    Atributos:
        _ruta (str): ruta completa del archivo JSON que administra.
    """

    def __init__(self, ruta: str):
        """
        Descripción:
            Guarda la ruta del archivo con el que va a trabajar. No lo abre ni lo crea;
            el archivo solo aparece cuando se escribe por primera vez.
        Entradas:
            ruta (str): ruta completa del archivo JSON.
        Salidas:
            Ninguna.
        """
        self._ruta = ruta

    def leer(self) -> dict:
        """
        Descripción:
            Lee el archivo y devuelve su contenido como diccionario.

            Pasos:
            1. Si el archivo no existe devuelve un diccionario vacío (primera ejecución).
            2. Intenta abrirlo y decodificarlo hasta 3 veces. Si falla porque otro programa
               lo está escribiendo en ese instante (OSError) o porque el JSON quedó incompleto
               (JSONDecodeError), espera 0.02 segundos y vuelve a intentar.
            3. Si el contenido válido no es un diccionario, o si los 3 intentos fallan,
               devuelve un diccionario vacío en lugar de provocar un error.
        Entradas:
            Ninguna.
        Salidas:
            dict: el contenido del JSON, o {} si no existe o no se pudo leer.
        """
        if not os.path.exists(self._ruta):
            return {}
        for _ in range(3):
            try:
                with open(self._ruta, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                return datos if isinstance(datos, dict) else {}
            except (OSError, json.JSONDecodeError):
                time.sleep(0.02)
        return {}

    def escribir(self, datos: dict) -> None:
        """
        Descripción:
            Guarda un diccionario en el archivo de forma atómica, es decir, de modo que un
            lector nunca encuentre el archivo a medio escribir.

            Pasos:
            1. Escribe todo el contenido en un archivo temporal (ruta + '.tmp') con sangría
               de 2 espacios y conservando tildes y eñes (ensure_ascii=False).
            2. Reemplaza el archivo real por el temporal con os.replace, que es una
               operación indivisible. Si Windows lo impide porque otro programa está leyendo
               el archivo (PermissionError), espera 0.02 segundos y reintenta hasta 5 veces.
            3. Si los 5 intentos fallan, hace un último reemplazo y deja que el error se
               propague para que no se pierda silenciosamente.
        Entradas:
            datos (dict): diccionario que se quiere guardar; debe ser serializable a JSON.
        Salidas:
            Ninguna. Efecto: el archivo queda actualizado con los datos recibidos.
        """
        tmp = self._ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)
        for _ in range(5):
            try:
                os.replace(tmp, self._ruta)
                return
            except PermissionError:
                time.sleep(0.02)
        os.replace(tmp, self._ruta)


class RepositorioAvatares(ABC):
    """
    Descripción:
        Contrato (clase abstracta) que define qué operaciones debe ofrecer cualquier
        almacén de avatares. La lógica del juego depende de este contrato y no de JSON,
        así que se puede cambiar el almacenamiento sin modificar la lógica.
    Atributos:
        Sin atributos. Las clases hijas deben implementar obtener y guardar.
    """

    @abstractmethod
    def obtener(self, id_usuario: int) -> Optional[EleccionAvatar]:
        """
        Descripción:
            Método abstracto: busca el avatar guardado de un usuario.
        Entradas:
            id_usuario (int): identificador del usuario.
        Salidas:
            Optional[EleccionAvatar]: la elección guardada, o None si el usuario nunca eligió.
        """
        ...

    @abstractmethod
    def guardar(self, id_usuario: int, eleccion: EleccionAvatar) -> None:
        """
        Descripción:
            Método abstracto: guarda (o reemplaza) el avatar de un usuario.
        Entradas:
            id_usuario (int): identificador del usuario.
            eleccion (EleccionAvatar): avatar que se quiere guardar.
        Salidas:
            Ninguna.
        """
        ...


class RepositorioAvataresJson(RepositorioAvatares):
    """
    Descripción:
        Implementación de RepositorioAvatares que guarda todos los avatares en el archivo
        avatares.json. Cada usuario es una clave del JSON (como texto) con su tipo y
        valor de avatar.
    Atributos:
        _archivo (_ArchivoJson): acceso seguro al archivo avatares.json.
    """

    def __init__(self, ruta: str = os.path.join(_CARPETA, "avatares.json")):
        """
        Descripción:
            Prepara el acceso al archivo de avatares. Por defecto usa avatares.json en la
            misma carpeta que este código.
        Entradas:
            ruta (str): ruta del archivo JSON; opcional, útil para pruebas con otro archivo.
        Salidas:
            Ninguna.
        """
        self._archivo = _ArchivoJson(ruta)

    def obtener(self, id_usuario: int) -> Optional[EleccionAvatar]:
        """
        Descripción:
            Lee el JSON completo y busca la entrada del usuario. Como las claves JSON siempre
            son texto, el identificador se convierte a str antes de buscar. Si la entrada
            existe pero le falta 'tipo' o 'valor' (archivo dañado o editado a mano) se
            trata como si el usuario no hubiera elegido nada.
        Entradas:
            id_usuario (int): identificador del usuario.
        Salidas:
            Optional[EleccionAvatar]: la elección encontrada, o None si no hay una válida.
        """
        e = self._archivo.leer().get(str(id_usuario))
        return EleccionAvatar(e["tipo"], e["valor"]) if e and "tipo" in e and "valor" in e else None

    def guardar(self, id_usuario: int, eleccion: EleccionAvatar) -> None:
        """
        Descripción:
            Lee el JSON actual, agrega o reemplaza la entrada del usuario y vuelve a
            escribir el archivo completo. Se lee antes de escribir para no borrar los
            avatares de los demás jugadores.
        Entradas:
            id_usuario (int): identificador del usuario.
            eleccion (EleccionAvatar): avatar que se quiere guardar.
        Salidas:
            Ninguna. Efecto: avatares.json actualizado.
        """
        datos = self._archivo.leer()
        datos[str(id_usuario)] = {"tipo": eleccion.tipo, "valor": eleccion.valor}
        self._archivo.escribir(datos)


class RepositorioPartida(ABC):
    """
    Descripción:
        Contrato (clase abstracta) para cargar y guardar la partida única del juego. La
        lógica depende de este contrato; la forma concreta de almacenar la partida es
        intercambiable.
    Atributos:
        Sin atributos. Las clases hijas deben implementar cargar y guardar.
    """

    @abstractmethod
    def cargar(self) -> Partida:
        """
        Descripción:
            Método abstracto: obtiene la partida con su estado más reciente.
        Entradas:
            Ninguna.
        Salidas:
            Partida: la partida guardada, o una nueva con valores por defecto si no hay.
        """
        ...

    @abstractmethod
    def guardar(self, partida: Partida) -> None:
        """
        Descripción:
            Método abstracto: guarda el estado completo de la partida.
        Entradas:
            partida (Partida): la partida que se quiere guardar.
        Salidas:
            Ninguna.
        """
        ...


class RepositorioPartidaJson(RepositorioPartida):
    """
    Descripción:
        Implementación de RepositorioPartida que guarda la partida en partida.json.
        Como el archivo es compartido, cada jugador (cada programa) ve los cambios de los
        demás cuando vuelve a cargarlo.
    Atributos:
        _archivo (_ArchivoJson): acceso seguro al archivo partida.json.
    """

    def __init__(self, ruta: str = os.path.join(_CARPETA, "partida.json")):
        """
        Descripción:
            Prepara el acceso al archivo de la partida. Por defecto usa partida.json en la
            misma carpeta que este código.
        Entradas:
            ruta (str): ruta del archivo JSON; opcional, útil para pruebas con otro archivo.
        Salidas:
            Ninguna.
        """
        self._archivo = _ArchivoJson(ruta)

    def cargar(self) -> Partida:
        """
        Descripción:
            Lee partida.json y reconstruye el objeto Partida con sus objetos anidados.
            Los datos que falten se completan con valores por defecto (configuración por
            defecto, estado 'esperando', sin hora de inicio, sin jugadores), de modo que un
            archivo inexistente o vacío produce una partida nueva y válida. Si el archivo
            tiene campos que no corresponden a los modelos (TypeError), se descarta su
            contenido y se devuelve una partida nueva.
        Entradas:
            Ninguna.
        Salidas:
            Partida: la partida guardada, o una partida nueva si no hay datos utilizables.
        """
        d = self._archivo.leer()
        try:
            return Partida(ConfiguracionPartida(**d.get("configuracion", {})), d.get("estado", "esperando"),
                           d.get("iniciada_en"), [Jugador(**j) for j in d.get("jugadores", [])])
        except TypeError:
            return Partida()

    def guardar(self, partida: Partida) -> None:
        """
        Descripción:
            Convierte la partida completa (incluyendo configuración y jugadores) en un
            diccionario con asdict y lo escribe en partida.json de forma atómica.
        Entradas:
            partida (Partida): la partida que se quiere guardar.
        Salidas:
            Ninguna. Efecto: partida.json actualizado.
        """
        self._archivo.escribir(asdict(partida))

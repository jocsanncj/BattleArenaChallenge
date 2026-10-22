"""
CAPA DE LÓGICA: reglas del juego, sin pantallas

Aquí viven las reglas de negocio. Este módulo no dibuja ventanas ni reacciona a
clics (eso es trabajo de interfaz.py) y tampoco sabe cómo se guardan los datos
(eso es trabajo de datos.py): solo usa los repositorios abstractos que recibe.
CAMBIO ONLINE: los mismos servicios funcionan con repositorios HTTP conectados al servidor Docker.

Clases principales:
    ServicioAvatar   ->  elegir, subir y dibujar avatares (US-06).
    MapaArena        ->  plano de la arena, límites, casillas transitables, puntos de
                         inicio y reactor (US-07).
    ServicioPartida  ->  configuración (US-08) y sala, inicio y temporizador (US-09).
    ErrorApp         ->  errores pensados para mostrarse al usuario.

Estructura del archivo:
    1. Librerías
    2. Errores de la aplicación
    3. Avatares
    4. Arena
    5. Partida
"""


# 1. LIBRERÍAS

# Librerías estándar de Python (vienen incluidas, no hay que instalarlas)

# base64: convierte los bytes de la imagen de un avatar personalizado a texto (y de vuelta)
# para poder guardarla dentro del JSON.
import base64

# io: BytesIO es un archivo en memoria; permite leer y guardar imágenes sin crear archivos
# temporales en el disco.
import io

# os: comprueba que la ruta de la imagen elegida exista y sea un archivo (os.path.isfile).
import os

# time: time.time() da la hora actual, que se usa como hora de inicio de la partida y para
# calcular los segundos transcurridos.
import time

# dataclasses.dataclass: crea el modelo AvatarPredeterminado sin código repetitivo.
from dataclasses import dataclass

# enum.Enum: define los tipos de casilla como un conjunto cerrado de valores con nombre,
# en vez de usar caracteres sueltos.
from enum import Enum

# typing (Dict, List, Tuple): anotaciones de tipo que documentan qué recibe y devuelve
# cada función.
from typing import Dict, List, Tuple

# Librería externa (se instala con: pip install pygame)

# pygame: se usa para crear, cargar, recortar, escalar y dibujar las imágenes de los avatares
# (Surface, image, transform y draw).
import pygame

# Módulos propios del proyecto

# datos: modelos (configuración, avatar, jugador, partida) y repositorios abstractos que
# usa la lógica; así depende de los contratos y no de cómo se guardan los datos.
from datos import (ConfiguracionPartida, EleccionAvatar, Jugador, Partida, RepositorioAvatares,
                   RepositorioPartida)


# 2. ERRORES DE LA APLICACIÓN

class ErrorApp(Exception):
    """
    Descripción:
        Excepción propia del programa para errores que el usuario debe conocer (sala
        llena, archivo inválido, configuración bloqueada, etc.). Su mensaje está escrito
        para personas, no para programadores. La interfaz la captura y muestra ese
        mensaje en pantalla en lugar de cerrar el programa.
    Atributos:
        Sin atributos propios: el mensaje es el texto con el que se crea la excepción.
    """


# 3. AVATARES

@dataclass(frozen=True)
class AvatarPredeterminado:
    """
    Descripción:
        Modelo inmutable de un avatar del catálogo. No guarda una imagen: guarda los datos
        con los que se dibuja por código.
    Atributos:
        id (str): identificador único, por ejemplo 'avatar_1'.
        nombre (str): nombre mostrado al usuario, por ejemplo 'Rojo'.
        color (Tuple[int, int, int]): color RGB del círculo de fondo.
        forma (str): figura blanca del centro: 'circulo', 'cuadrado', 'triangulo',
            'rombo' o 'cruz'.
    """

    id: str
    nombre: str
    color: Tuple[int, int, int]
    forma: str


# Catálogo de avatares que el jugador puede elegir sin subir imagen. Se dibujan por
# código (círculo de color con una figura blanca), por eso no necesitan archivos.
AVATARES_PREDETERMINADOS: List[AvatarPredeterminado] = [
    AvatarPredeterminado("avatar_1", "Rojo",     (200, 60, 60),  "circulo"),
    AvatarPredeterminado("avatar_2", "Azul",     (60, 110, 210), "cuadrado"),
    AvatarPredeterminado("avatar_3", "Verde",    (60, 170, 90),  "triangulo"),
    AvatarPredeterminado("avatar_4", "Amarillo", (220, 180, 40), "rombo"),
    AvatarPredeterminado("avatar_5", "Morado",   (150, 80, 190), "cruz"),
]



class ServicioAvatar:
    """
    Descripción:
        Reglas de los avatares: cada jugador siempre tiene uno, puede elegir uno del
        catálogo o subir una imagen propia, y puede obtener una imagen lista para
        dibujar en cualquier pantalla. Guarda y lee sus datos a través de un
        RepositorioAvatares, sin saber si detrás hay JSON u otra cosa.
    Atributos:
        _repo (RepositorioAvatares): almacén donde se guardan las elecciones.
        _predeterminados (Dict[str, AvatarPredeterminado]): catálogo indexado por id,
            para buscar un avatar rápidamente.
    """

    def __init__(self, repositorio: RepositorioAvatares):
        """
        Descripción:
            Guarda el repositorio recibido y construye un diccionario del catálogo de avatares
            predeterminados indexado por su id.
        Entradas:
            repositorio (RepositorioAvatares): almacén de avatares.
        Salidas:
            Ninguna.
        """
        self._repo = repositorio
        self._predeterminados: Dict[str, AvatarPredeterminado] = {a.id: a for a in AVATARES_PREDETERMINADOS}

    def listar_predeterminados(self) -> List[AvatarPredeterminado]:
        """
        Descripción:
            Devuelve el catálogo de avatares predeterminados. Entrega una copia de la lista
            para que quien la reciba no pueda alterar el catálogo original.
        Entradas:
            Ninguna.
        Salidas:
            List[AvatarPredeterminado]: los avatares del catálogo, en orden.
        """
        return list(AVATARES_PREDETERMINADOS)

    def obtener_eleccion(self, id_usuario: int) -> EleccionAvatar:
        """
        Descripción:
            Devuelve la elección de avatar de un jugador. Garantiza que todo jugador tenga
            avatar: si todavía no eligió ninguno (el repositorio devuelve None), se le asigna
            el primer avatar predeterminado, sin guardarlo.
        Entradas:
            id_usuario (int): identificador del jugador.
        Salidas:
            EleccionAvatar: la elección guardada o, si no hay, el primer avatar del catálogo.
        """
        return self._repo.obtener(id_usuario) or EleccionAvatar("predeterminado", AVATARES_PREDETERMINADOS[0].id)

    def obtener_superficie(self, id_usuario: int, tam: int = 64) -> pygame.Surface:
        """
        Descripción:
            Construye la imagen del avatar de un jugador, lista para dibujar con pygame en
            cualquier ventana. La imagen se arma de nuevo cada vez a partir de lo guardado.

            Pasos:
            1. Obtiene la elección del jugador.
            2. Si es personalizada, decodifica el texto base64, lo carga como imagen en
               memoria y la recorta a cuadrado con el tamaño pedido.
            3. Si la imagen está dañada (base64 inválido o formato no reconocido), no se
               detiene: cae al camino de los avatares predeterminados.
            4. Si es predeterminada (o hubo fallo), busca el avatar en el catálogo, usando
               el primero si el id no existe, y lo dibuja por código.
        Entradas:
            id_usuario (int): identificador del jugador.
            tam (int): lado en píxeles de la imagen cuadrada resultante. Por defecto 64.
        Salidas:
            pygame.Surface: imagen cuadrada del avatar de tam x tam píxeles.
        """
        eleccion = self.obtener_eleccion(id_usuario)
        if eleccion.tipo == "personalizado":
            try:
                imagen = pygame.image.load(io.BytesIO(base64.b64decode(eleccion.valor)), "avatar.png")
                return self._cuadrar(imagen, tam)
            except (ValueError, pygame.error):
                pass
        avatar = self._predeterminados.get(eleccion.valor, AVATARES_PREDETERMINADOS[0])
        return self.dibujar_predeterminado(avatar, tam)

    def seleccionar_predeterminado(self, id_usuario: int, id_avatar: str) -> None:
        """
        Descripción:
            Guarda como avatar del jugador uno del catálogo. Primero comprueba que el id exista
            para no guardar un avatar inexistente.
        Entradas:
            id_usuario (int): identificador del jugador.
            id_avatar (str): id del avatar del catálogo, por ejemplo 'avatar_2'.
        Salidas:
            Ninguna. Efecto: la elección queda guardada. Lanza ErrorApp si el id no existe.
        """
        if id_avatar not in self._predeterminados:
            raise ErrorApp("El avatar seleccionado no existe.")
        self._repo.guardar(id_usuario, EleccionAvatar("predeterminado", id_avatar))

    def subir_personalizado(self, id_usuario: int, ruta_origen: str) -> None:
        """
        Descripción:
            Permite que un jugador use una imagen de su computador como avatar. La imagen se
            guarda dentro del propio JSON como texto, no como archivo aparte.

            Pasos:
            1. Verifica que la ruta exista y sea un archivo; si no, lanza ErrorApp.
            2. Carga la imagen con pygame, la recorta a cuadrado y la reduce a 128 x 128
               píxeles para que el JSON se mantenga liviano. Si no es una imagen válida, lanza

            ErrorApp con un mensaje claro.
            3. La convierte a PNG en memoria, la codifica en base64 y la guarda como avatar
               de tipo 'personalizado'.
        Entradas:
            id_usuario (int): identificador del jugador.
            ruta_origen (str): ruta de la imagen elegida en el disco.
        Salidas:
            Ninguna. Efecto: avatar personalizado guardado. Lanza ErrorApp si el archivo no
                existe o no es una imagen.
        """
        if not ruta_origen or not os.path.isfile(ruta_origen):
            raise ErrorApp("No se encontró el archivo seleccionado.")
        try:
            pequena = self._cuadrar(pygame.image.load(ruta_origen), 128)
        except pygame.error:
            raise ErrorApp("El archivo no es una imagen válida (use PNG, JPG, BMP...).")
        buffer = io.BytesIO()
        pygame.image.save(pequena, buffer, "avatar.png")
        self._repo.guardar(id_usuario, EleccionAvatar("personalizado", base64.b64encode(buffer.getvalue()).decode("ascii")))

    @staticmethod
    def _cuadrar(imagen: pygame.Surface, tam: int) -> pygame.Surface:
        """
        Descripción:
            Convierte cualquier imagen en un cuadrado. Toma el lado menor de la imagen, recorta
            un cuadrado centrado de ese lado (así no se deforma) y lo escala suavemente al
            tamaño pedido. Si ya existe una ventana de pygame, convierte antes la imagen a un
            formato con transparencia (convert_alpha), que es más rápido de dibujar. Es un
            método estático porque no usa datos del objeto.
        Entradas:
            imagen (pygame.Surface): imagen original, de cualquier proporción.
            tam (int): lado en píxeles del cuadrado final.
        Salidas:
            pygame.Surface: imagen cuadrada de tam x tam píxeles.
        """
        imagen = imagen.convert_alpha() if pygame.display.get_surface() else imagen
        ancho, alto = imagen.get_size()
        lado = min(ancho, alto)
        recorte = imagen.subsurface(((ancho - lado) // 2, (alto - lado) // 2, lado, lado)).copy()
        return pygame.transform.smoothscale(recorte, (tam, tam))

    @staticmethod
    def dibujar_predeterminado(avatar: AvatarPredeterminado, tam: int) -> pygame.Surface:
        """
        Descripción:
            Dibuja por código un avatar del catálogo, sin necesidad de archivos de imagen.
            Crea una superficie transparente, pinta un círculo del color del avatar que
            ocupa todo el cuadro y encima una figura blanca centrada según su forma:
            - circulo: círculo pequeño.
            - cuadrado: cuadrado.
            - triangulo: triángulo apuntando hacia arriba.
            - rombo: rombo.
            - cruz: dos rectángulos cruzados.

            Si la forma no se reconoce, queda solo el círculo de color. Es un método estático
            porque no usa datos del objeto.
        Entradas:
            avatar (AvatarPredeterminado): avatar que se va a dibujar.
            tam (int): lado en píxeles de la imagen cuadrada.
        Salidas:
            pygame.Surface: imagen del avatar de tam x tam píxeles con fondo transparente.
        """
        s = pygame.Surface((tam, tam), pygame.SRCALPHA)
        c, q, blanco = tam // 2, tam // 4, (255, 255, 255)
        pygame.draw.circle(s, avatar.color, (c, c), c)
        if avatar.forma == "circulo":
            pygame.draw.circle(s, blanco, (c, c), q)
        elif avatar.forma == "cuadrado":
            pygame.draw.rect(s, blanco, (c - q, c - q, 2 * q, 2 * q))
        elif avatar.forma == "triangulo":
            pygame.draw.polygon(s, blanco, [(c, c - q), (c - q, c + q), (c + q, c + q)])
        elif avatar.forma == "rombo":
            pygame.draw.polygon(s, blanco, [(c, c - q), (c + q, c), (c, c + q), (c - q, c)])
        elif avatar.forma == "cruz":
            g = max(2, q // 2)
            pygame.draw.rect(s, blanco, (c - g, c - q, 2 * g, 2 * q))
            pygame.draw.rect(s, blanco, (c - q, c - g, 2 * q, 2 * g))
        return s


# 4. ARena

class Casilla(Enum):
    """
    Descripción:
        Tipos de casilla que puede tener el plano de la arena. Cada valor es el carácter
        con el que se escribe esa casilla en el plano de texto. Los puntos de inicio se
        escriben en el plano con dígitos (1, 2, 3...), pero ya dentro del mapa se
        representan como INICIO.
    Atributos:
        PISO ('.'): casilla transitable.
        MURO ('#'): no transitable; forma el límite de la arena.
        OBSTACULO ('X'): no transitable.
        REACTOR ('R'): no transitable; ocupa el centro de la arena.
        INICIO ('S'): transitable; punto donde comienza un jugador.
    """

    PISO = "."
    MURO = "#"
    OBSTACULO = "X"
    REACTOR = "R"
    INICIO = "S"


# Tipos de casilla por los que un avatar puede caminar.
CASILLAS_TRANSITABLES = frozenset({Casilla.PISO, Casilla.INICIO})


class MapaArena:
    """
    Descripción:
        Convierte un plano escrito como texto (una cadena por fila) en una cuadrícula de
        casillas y responde preguntas sobre ella: tamaño, qué hay en cada casilla, si se
        puede caminar por ahí, dónde empieza cada jugador y dónde está el reactor. No
        dibuja nada: solo guarda la información del escenario.
    Atributos:
        nombre (str): nombre del escenario.
        _casillas (List[List[Casilla]]): cuadrícula, indexada como [fila][columna].
        _inicios (List[Tuple[int, int]]): puntos de inicio (columna, fila) ordenados por
            el número de jugador.
        _reactor (List[Tuple[int, int]]): coordenadas (columna, fila) de las casillas del
            reactor.
    """

    def __init__(self, nombre: str, plano: Tuple[str, ...]):
        """
        Descripción:
            Lee el plano carácter por carácter y construye la cuadrícula.

            Pasos:
            1. Si el carácter es un dígito, lo registra como punto de inicio de ese jugador
               (la posición se guarda por su número) y coloca una casilla INICIO.
            2. Cualquier otro carácter se convierte en su Casilla; un carácter que no esté
               definido en Casilla provoca un ValueError.
            3. Ordena los puntos de inicio por su número, de modo que el índice 0 sea el del
               jugador 1.
            4. Recoge las coordenadas de todas las casillas del reactor.
        Entradas:
            nombre (str): nombre del escenario.
            plano (Tuple[str, ...]): filas del escenario; todas deberían tener el mismo largo.
        Salidas:
            Ninguna.
        """
        self.nombre = nombre
        self._casillas: List[List[Casilla]] = []
        inicios: Dict[int, Tuple[int, int]] = {}
        for f, fila in enumerate(plano):
            linea = []
            for c, caracter in enumerate(fila):
                if caracter.isdigit():
                    inicios[int(caracter)] = (c, f)
                    linea.append(Casilla.INICIO)
                else:
                    linea.append(Casilla(caracter))
            self._casillas.append(linea)
        self._inicios = [inicios[k] for k in sorted(inicios)]
        self._reactor = [(c, f) for f in range(self.filas) for c in range(self.columnas)
                         if self._casillas[f][c] is Casilla.REACTOR]

    @property
    def columnas(self) -> int:
        """
        Descripción:
            Propiedad: cantidad de columnas de la cuadrícula, medida con la primera fila.
        Entradas:
            Ninguna.
        Salidas:
            int: número de columnas.
        """
        return len(self._casillas[0])

    @property
    def filas(self) -> int:
        """
        Descripción:
            Propiedad: cantidad de filas de la cuadrícula.
        Entradas:
            Ninguna.
        Salidas:
            int: número de filas.
        """
        return len(self._casillas)

    def casilla_en(self, columna: int, fila: int) -> Casilla:
        """
        Descripción:
            Devuelve el tipo de casilla en una posición. No comprueba límites: pedir una
            posición fuera del mapa provoca un error de índice (para eso existe
            es_transitable, que sí los valida).
        Entradas:
            columna (int): posición horizontal, empezando en 0.
            fila (int): posición vertical, empezando en 0.
        Salidas:
            Casilla: el tipo de casilla en esa posición.
        """
        return self._casillas[fila][columna]

    def es_transitable(self, columna: int, fila: int) -> bool:
        """
        Descripción:
            Indica si un avatar puede estar en una posición. Primero verifica que la posición
            esté dentro de la arena (fuera de ella la respuesta siempre es False) y luego que
            el tipo de casilla sea transitable (piso o inicio). Muros, obstáculos y reactor
            no lo son.
        Entradas:
            columna (int): posición horizontal, empezando en 0.
            fila (int): posición vertical, empezando en 0.
        Salidas:
            bool: True si se puede pisar esa casilla, False en caso contrario.
        """
        return (0 <= columna < self.columnas and 0 <= fila < self.filas
                and self._casillas[fila][columna] in CASILLAS_TRANSITABLES)

    def puntos_inicio(self) -> List[Tuple[int, int]]:
        """
        Descripción:
            Devuelve los puntos de inicio de los jugadores. El primer punto corresponde al
            primer jugador, el segundo al segundo, y así sucesivamente. Entrega una copia
            para proteger la lista interna.
        Entradas:
            Ninguna.
        Salidas:
            List[Tuple[int, int]]: lista de (columna, fila), uno por jugador posible.
        """
        return list(self._inicios)

    def centro_reactor(self) -> Tuple[float, float]:
        """
        Descripción:
            Calcula el centro del reactor tomando el punto medio del rectángulo que contiene
            todas sus casillas. El resultado puede tener decimales (por ejemplo 10.0 o 10.5)
            porque el centro puede quedar entre dos casillas. Si el plano no tiene reactor
            se produce un ValueError.
        Entradas:
            Ninguna.
        Salidas:
            Tuple[float, float]: (columna, fila) del centro, en unidades de casilla.
        """
        columnas, filas = [c for c, _ in self._reactor], [f for _, f in self._reactor]
        return (min(columnas) + max(columnas)) / 2, (min(filas) + max(filas)) / 2


# Escenario que usa el juego. Leyenda del plano:
#   '#' muro   'X' obstáculo   'R' reactor (centro)   '.' piso
#   dígitos 1 a 4: punto de inicio de cada jugador
# Para usar otro escenario basta con reemplazar el nombre y el plano.
ARENA_PREDETERMINADA = MapaArena("Arena Clásica", (
    "#####################",
    "#1.................2#",
    "#...................#",
    "#...XX.........XX...#",
    "#...XX.........XX...#",
    "#...................#",
    "#........RRR........#",
    "#........RRR........#",
    "#........RRR........#",
    "#...................#",
    "#...XX.........XX...#",
    "#...XX.........XX...#",
    "#...................#",
    "#3.................4#",
    "#####################",
))


# 5. PARTIDA

# CAMBIO ONLINE: todas las operaciones de sala/configuración pasan por el repositorio
# inyectado; con RepositorioPartidaServidor el estado se comparte entre clientes.
class ServicioPartida:
    """
    Descripción:
        Reglas de la partida única del juego: configuración, sala de espera, inicio y
        temporizador. Cada operación carga la partida desde el repositorio, la modifica
        y la guarda, sin mantener copias en memoria; así siempre se trabaja con el
        estado más reciente, aunque otro jugador lo haya cambiado.
    Atributos:
        JUGADORES_MINIMOS (int): jugadores necesarios para iniciar (regla definitiva: 2).
        PERMITIR_UN_JUGADOR (bool): modo provisional de pruebas; si es True se puede
            iniciar con un solo jugador. Para exigir JUGADORES_MINIMOS basta con ponerlo en
            False.
        _repo (RepositorioPartida): almacén donde se guarda la partida.
        arena (MapaArena): escenario donde se juega; define cuántos jugadores caben.
    """

    JUGADORES_MINIMOS = 2
    PERMITIR_UN_JUGADOR = False  # CAMBIO ONLINE: se exigen dos jugadores conectados para iniciar

    def __init__(self, repositorio: RepositorioPartida, arena: MapaArena = ARENA_PREDETERMINADA):
        """
        Descripción:
            Guarda el repositorio y el escenario que usará la partida.
        Entradas:
            repositorio (RepositorioPartida): almacén de la partida.
            arena (MapaArena): escenario; por defecto ARENA_PREDETERMINADA.
        Salidas:
            Ninguna.
        """
        self._repo = repositorio
        self.arena = arena

    def obtener_partida(self) -> Partida:
        """
        Descripción:
            Carga la partida actual desde el repositorio. Se vuelve a leer en cada llamada para
            reflejar los cambios hechos por otros jugadores.
        Entradas:
            Ninguna.
        Salidas:
            Partida: la partida con su estado más reciente.
        """
        return self._repo.cargar()

    # ----- Configuración de la partida -----
    def verificar_configurable(self) -> None:
        """
        Descripción:
            Comprueba que todavía se pueda configurar la partida. Si ya está en estado
            'jugando' lanza un ErrorApp; si no, no hace nada. Se usa antes de abrir la
            pantalla de configuración y antes de guardar cambios.
        Entradas:
            Ninguna.
        Salidas:
            Ninguna. Lanza ErrorApp si la partida ya inició.
        """
        if self._repo.cargar().estado == "jugando":
            raise ErrorApp("La partida ya inició: no se puede cambiar la configuración.")

    def actualizar_configuracion(self, configuracion: ConfiguracionPartida) -> None:
        """
        Descripción:
            Guarda una nueva configuración de la partida.

            Pasos:
            1. Verifica que la partida no haya iniciado.
            2. Valida que el modo de fin sea 'tiempo' o 'puntos' y que los minutos, los
               puntos y los segundos de congelación sean al menos 1; si no, lanza ErrorApp.
            3. Carga la partida, reemplaza su configuración y la guarda.
        Entradas:
            configuracion (ConfiguracionPartida): la configuración que se quiere aplicar.
        Salidas:
            Ninguna. Efecto: configuración guardada. Lanza ErrorApp si está bloqueada o es
                inválida.
        """
        self.verificar_configurable()
        if configuracion.modo_fin not in ("tiempo", "puntos") or min(
                configuracion.minutos_fin, configuracion.puntos_fin, configuracion.segundos_congelacion) < 1:
            raise ErrorApp("Valores de configuración inválidos.")
        partida = self._repo.cargar()
        partida.configuracion = configuracion
        self._repo.guardar(partida)

    # ----- Sala de espera, inicio y temporizador -----
    def unirse(self, id_usuario: int, nombre_usuario: str) -> Jugador:
        """
        Descripción:
            Hace que un jugador entre a la sala y le asigna un punto de inicio distinto al de
            los demás. Es idempotente: si el jugador ya está en la sala, devuelve su registro
            sin duplicarlo.

            Pasos:
            1. Si ya está en la sala, lo devuelve.
            2. Si la partida ya inició, lanza ErrorApp.
            3. Calcula los puntos de inicio libres; si no queda ninguno, lanza ErrorApp
               ('La sala está llena').
            4. Crea el Jugador con el primer punto libre, lo agrega y guarda la partida.
        Entradas:
            id_usuario (int): identificador del jugador.
            nombre_usuario (str): nombre que se mostrará.
        Salidas:
            Jugador: el jugador dentro de la sala. Lanza ErrorApp si la sala está llena o la
                partida ya inició.
        """
        partida = self._repo.cargar()
        for j in partida.jugadores:
            if j.id_usuario == id_usuario:
                return j
        if partida.estado == "jugando":
            raise ErrorApp("La partida ya inició. Espere a que termine.")
        usados = {j.indice_inicio for j in partida.jugadores}
        libres = [i for i in range(len(self.arena.puntos_inicio())) if i not in usados]
        if not libres:
            raise ErrorApp("La sala está llena.")
        jugador = Jugador(id_usuario, nombre_usuario, libres[0])
        partida.jugadores.append(jugador)
        self._repo.guardar(partida)
        return jugador

    def salir(self, id_usuario: int) -> None:
        """
        Descripción:
            Saca a un jugador de la sala y libera su punto de inicio. Solo guarda si el
            jugador realmente estaba dentro. Si con su salida la sala queda vacía, la partida
            vuelve al estado 'esperando' y se borra la hora de inicio, de modo que una sala
            vacía nunca quede marcada como 'jugando'.
        Entradas:
            id_usuario (int): identificador del jugador que se va.
        Salidas:
            Ninguna. Efecto: partida actualizada.
        """
        partida = self._repo.cargar()
        restantes = [j for j in partida.jugadores if j.id_usuario != id_usuario]
        if len(restantes) != len(partida.jugadores):
            partida.jugadores = restantes
            if not restantes:
                partida.estado, partida.iniciada_en = "esperando", None
            self._repo.guardar(partida)

    def iniciar(self) -> None:
        """
        Descripción:
            Inicia la partida si se cumplen las condiciones.

            Pasos:
            1. Si ya está en estado 'jugando', lanza ErrorApp.
            2. Determina cuántos jugadores se necesitan: 1 en modo provisional, o

            JUGADORES_MINIMOS en caso contrario.
            3. Si hay menos jugadores, lanza ErrorApp con el mensaje 'Esperando jugador...'.
            4. Cambia el estado a 'jugando', registra la hora actual como hora de inicio y
               guarda la partida.
        Entradas:
            Ninguna.
        Salidas:
            Ninguna. Efecto: partida en estado 'jugando'. Lanza ErrorApp si ya inició o faltan
                jugadores.
        """
        partida = self._repo.cargar()
        if partida.estado == "jugando":
            raise ErrorApp("La partida ya inició.")
        necesarios = 1 if self.PERMITIR_UN_JUGADOR else self.JUGADORES_MINIMOS
        if len(partida.jugadores) < necesarios:
            raise ErrorApp("Esperando jugador...")
        partida.estado, partida.iniciada_en = "jugando", time.time()
        self._repo.guardar(partida)

    def segundos_transcurridos(self, partida: Partida) -> float:
        """
        Descripción:
            Calcula cuántos segundos han pasado desde que inició la partida, restando la hora
            de inicio a la hora actual. Si la partida aún no inició devuelve 0.0, y nunca
            devuelve valores negativos. Con este dato la interfaz arma el temporizador.
        Entradas:
            partida (Partida): partida de la que se quiere conocer el tiempo transcurrido.
        Salidas:
            float: segundos desde el inicio de la partida, o 0.0 si no ha iniciado.
        """
        return max(0.0, time.time() - partida.iniciada_en) if partida.iniciada_en else 0.0

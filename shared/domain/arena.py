"""Modelo del mapa de arena y escenario predeterminado."""

from enum import Enum
from typing import Dict, List, Tuple


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


# En el plano, los dígitos indican los puntos de inicio y R representa el reactor.
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

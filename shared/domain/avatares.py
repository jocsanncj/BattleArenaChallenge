"""Catálogo y reglas para seleccionar, almacenar y dibujar avatares."""

import base64
import io
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

import pygame

from shared.data import EleccionAvatar, RepositorioAvatares
from .errores import ErrorApp


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


# Se dibujan por código y no dependen de archivos de imagen.
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
        self._predeterminados: Dict[str, AvatarPredeterminado] = {
            a.id: a for a in AVATARES_PREDETERMINADOS
        }

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
        return self._repo.obtener(id_usuario) or EleccionAvatar(
            "predeterminado", AVATARES_PREDETERMINADOS[0].id
        )

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
                imagen = pygame.image.load(
                    io.BytesIO(base64.b64decode(eleccion.valor)), "avatar.png"
                )
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
        self._repo.guardar(
            id_usuario,
            EleccionAvatar(
                "personalizado",
                base64.b64encode(buffer.getvalue()).decode("ascii"),
            ),
        )

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

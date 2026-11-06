"""Reglas de configuración, sala de espera e inicio de partida."""

import time

from shared.data import (
    ConfiguracionPartida,
    Jugador,
    Partida,
    RepositorioPartida,
    RepositorioPartidaOnline,
)
from .arena import ARENA_PREDETERMINADA, MapaArena
from .errores import ErrorApp


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
        if (
            configuracion.modo_fin not in ("tiempo", "puntos")
            or min(
                configuracion.minutos_fin,
                configuracion.puntos_fin,
                configuracion.segundos_congelacion,
            ) < 1
        ):
            raise ErrorApp("Valores de configuración inválidos.")
        if isinstance(self._repo, RepositorioPartidaOnline):
            try:
                self._repo.guardar(Partida(configuracion=configuracion))
            except (OSError, RuntimeError, ValueError) as error:
                raise ErrorApp(str(error)) from error
            return
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
        if isinstance(self._repo, RepositorioPartidaOnline):
            try:
                self._repo.unirse_online()
                partida = self._repo.cargar()
            except (OSError, RuntimeError, ValueError) as error:
                raise ErrorApp(str(error)) from error
            jugador = next((j for j in partida.jugadores if j.id_usuario == id_usuario), None)
            if jugador is None:
                raise ErrorApp("El servidor no confirmó tu ingreso a la sala.")
            return jugador
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
        if isinstance(self._repo, RepositorioPartidaOnline):
            try:
                self._repo.salir_online()
            except (OSError, RuntimeError, ValueError) as error:
                raise ErrorApp(str(error)) from error
            return
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
        if isinstance(self._repo, RepositorioPartidaOnline):
            try:
                self._repo.iniciar_online()
            except (OSError, RuntimeError, ValueError) as error:
                raise ErrorApp(str(error)) from error
            return
        partida = self._repo.cargar()
        if partida.estado == "jugando":
            raise ErrorApp("La partida ya inició.")
        necesarios = 1 if self.PERMITIR_UN_JUGADOR else self.JUGADORES_MINIMOS
        if len(partida.jugadores) < necesarios:
            raise ErrorApp("Esperando jugador...")
        partida.estado, partida.iniciada_en = "jugando", time.time()
        self._repo.guardar(partida)

    def mover(self, direccion: str) -> None:
        """Solicita un movimiento al servidor; este valida y confirma la acción."""
        if not isinstance(self._repo, RepositorioPartidaOnline):
            raise ErrorApp("Los movimientos remotos requieren el servidor de juego.")
        try:
            self._repo.mover_online(direccion)
        except (OSError, RuntimeError, ValueError) as error:
            raise ErrorApp(str(error)) from error

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

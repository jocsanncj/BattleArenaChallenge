// Escritorio y móvil guardan las reglas en la misma sala. El servidor valida el rol de creador.
// movil.js proporciona tres funciones. pedir envía solicitudes a la API, jugadorActual identifica
// la cuenta abierta y actualizar solicita el estado de la sala tras guardar. El objeto devuelto
// permite ajustar la edición cada vez que llega un estado de partida.
/** @brief US-08 y US-30: conecta el editor móvil con la configuración validada por el servidor. */
export function prepararConfiguracion({ pedir, jugadorActual, actualizar }) {
  const panel = document.getElementById("opciones-configuracion");
  const form = document.getElementById("form-configuracion");
  const campos = form.elements;
  const editar = document.getElementById("editar-configuracion");
  const guardar = document.getElementById("guardar-configuracion");
  const cancelar = document.getElementById("cancelar-configuracion");
  const aviso = document.getElementById("aviso-configuracion");
  let reglas;
  let peticion;

  // Al abrir el formulario o cambiar el modo de fin se muestra solo el límite elegido. El otro campo
  // queda deshabilitado. Al guardar se conserva su valor anterior por si la sala vuelve a ese modo.
  /** @brief US-08 y US-30: muestra y habilita el límite de la partida seleccionado. */
  function mostrarLimite() {
    const porTiempo = campos.modo_fin.value === "tiempo";
    document.getElementById("cfg-limite-tiempo").hidden = !porTiempo;
    document.getElementById("cfg-limite-puntos").hidden = porTiempo;
    campos.minutos_fin.disabled = !porTiempo;
    campos.puntos_fin.disabled = porTiempo;
  }

  // Cierra el formulario y cambia aria-expanded para que los lectores de pantalla anuncien el panel cerrado.
  // Cerrar solo modifica la interfaz del móvil.
  /** @brief US-08 y US-30: cierra el editor de configuración y actualiza su estado accesible. */
  function cerrar() {
    form.hidden = true;
    editar.setAttribute("aria-expanded", "false");
  }

  // Al abrir el editor copia la última configuración confirmada en los campos. La opción «aleatorio»
  // representa la rotación de escenarios y el foco pasa al modo de fin para poder editar con el teclado.
  editar.addEventListener("click", () => {
    if (!form.hidden) {
      cerrar();
      return;
    }
    for (const nombre of ["modo_fin", "minutos_fin", "puntos_fin", "segundos_congelacion"]) {
      campos[nombre].value = reglas[nombre];
    }
    campos.escenario.value = reglas.rotacion ? "aleatorio" : (reglas.escenario ?? 0);
    aviso.textContent = "";
    mostrarLimite();
    form.hidden = false;
    editar.setAttribute("aria-expanded", "true");
    campos.modo_fin.focus();
  });
  campos.modo_fin.addEventListener("change", mostrarLimite);
  // Cancelar descarta la edición visible y devuelve el foco a Editar. Al reabrir se leerán otra vez las reglas de la sala.
  cancelar.addEventListener("click", () => { cerrar(); editar.focus(); });

  // Al pulsar Guardar, el formulario intercepta submit para que la página siga abierta. Reúne los
  // valores de los campos y los envía por PUT a /api/game/config con el token de quien edita. El servidor comprueba
  // el permiso de creador. Tras una respuesta válida se cierra el editor y se vuelve a consultar la sala.
  form.addEventListener("submit", async evento => {
    evento.preventDefault();
    const jugador = jugadorActual();
    if (!jugador || !reglas || peticion || form.hidden) return;
    const rotacion = campos.escenario.value === "aleatorio";
    const datos = {
      modo_fin: campos.modo_fin.value,
      minutos_fin: campos.minutos_fin.disabled ? reglas.minutos_fin : campos.minutos_fin.valueAsNumber,
      puntos_fin: campos.puntos_fin.disabled ? reglas.puntos_fin : campos.puntos_fin.valueAsNumber,
      segundos_congelacion: campos.segundos_congelacion.valueAsNumber,
      escenario: rotacion ? (reglas.escenario ?? 0) : Number(campos.escenario.value),
      rotacion,
    };
    // Guardar conserva el identificador de esta solicitud para bloquear envíos duplicados. La señal
    // de AbortController permite dejar de esperar su respuesta si cambia el creador o el estado de la sala.
    const solicitud = new AbortController();
    peticion = solicitud;
    guardar.disabled = editar.disabled = cancelar.disabled = true;
    try {
      const token = await jugador.getIdToken();
      if (solicitud.signal.aborted || jugador !== jugadorActual()) return;
      await pedir("/api/game/config", {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(datos),
        signal: solicitud.signal,
      });
      if (solicitud.signal.aborted || jugador !== jugadorActual()) return;
      reglas = datos;
      cerrar();
      aviso.textContent = "Configuración guardada.";
      actualizar();
    } catch (error) {
      if (!solicitud.signal.aborted && jugador === jugadorActual()) aviso.textContent = error.message;
    } finally {
      if (peticion === solicitud) {
        peticion = null;
        guardar.disabled = editar.disabled = cancelar.disabled = false;
      }
    }
  });

  return {
    // Cada respuesta de la sala trae sus jugadores y su estado. Mientras espera, el primer jugador es el creador.
    // Solo si coincide con idActual se muestra la edición. Si pierde el permiso, se cancela la espera de la
    // solicitud en el navegador, se cierra el formulario y se limpian sus avisos.
    sincronizar(partida, idActual) {
      const creador = idActual != null && partida?.estado === "esperando"
        && partida.jugadores?.[0]?.id_usuario === idActual;
      panel.hidden = !creador;
      reglas = creador ? partida.configuracion : null;
      if (!creador) {
        peticion?.abort();
        peticion = null;
        guardar.disabled = editar.disabled = cancelar.disabled = false;
        cerrar();
        aviso.textContent = "";
      }
    },
  };
}

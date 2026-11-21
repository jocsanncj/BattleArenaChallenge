// Escritorio y móvil guardan las reglas en la misma sala. El servidor valida el rol de creador.
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

  function mostrarLimite() {
    const porTiempo = campos.modo_fin.value === "tiempo";
    document.getElementById("cfg-limite-tiempo").hidden = !porTiempo;
    document.getElementById("cfg-limite-puntos").hidden = porTiempo;
    campos.minutos_fin.disabled = !porTiempo;
    campos.puntos_fin.disabled = porTiempo;
  }

  function cerrar() {
    form.hidden = true;
    editar.setAttribute("aria-expanded", "false");
  }

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
  cancelar.addEventListener("click", () => { cerrar(); editar.focus(); });

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

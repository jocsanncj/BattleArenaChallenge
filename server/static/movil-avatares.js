// Las rutas y los nombres del catálogo vienen del servidor que también usa Pygame.
const radios = [...document.querySelectorAll('input[name="avatar"]')];
export const catalogo = new Map(radios.filter(radio => radio.dataset.personaje).map(radio => [
  radio.value, { nombre: radio.dataset.nombre, retrato: radio.parentElement.querySelector("img").src, personaje: radio.dataset.personaje },
]));

export function retratoPersonalizado(valor) {
  return typeof valor === "string" && valor.startsWith("iVBORw0KGgo") && valor.length <= 2_000_000
    ? "data:image/png;base64," + valor : "";
}

async function convertirImagen(archivo) {
  if (archivo.size > 10 * 1024 * 1024 || !["image/png", "image/jpeg", "image/webp"].includes(archivo.type)) {
    throw new Error("Elige una imagen PNG, JPG o WebP de hasta 10 MB.");
  }
  const url = URL.createObjectURL(archivo);
  try {
    const imagen = new Image();
    imagen.src = url;
    await imagen.decode();
    // El escritorio guarda los avatares personales como un PNG cuadrado de 128 × 128 en base64.
    const lado = Math.min(imagen.naturalWidth, imagen.naturalHeight);
    const lienzo = document.createElement("canvas");
    lienzo.width = lienzo.height = 128;
    lienzo.getContext("2d").drawImage(imagen, (imagen.naturalWidth - lado) / 2,
      (imagen.naturalHeight - lado) / 2, lado, lado, 0, 0, 128, 128);
    return lienzo.toDataURL("image/png").split(",")[1];
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function prepararSeleccion(cambio) {
  const personalizado = document.querySelector("#opcion-personalizada");
  const archivo = document.querySelector("#archivo-avatar");
  const aviso = document.querySelector("#aviso-avatar");
  const vista = document.querySelector("#retrato-seleccionado");
  let imagenPersonal, guardado, revision = 0, leyendo = false;

  function actualizarVista() {
    const opcion = radios.find(radio => radio.checked);
    const retrato = catalogo.get(opcion?.value)?.retrato || retratoPersonalizado(imagenPersonal);
    if (retrato) vista.src = retrato;
    else vista.removeAttribute("src");
    vista.hidden = !retrato;
    document.querySelector("#nombre-seleccionado").textContent = opcion?.dataset.nombre || "—";
    cambio();
  }
  function mostrarPersonal(valor) {
    imagenPersonal = valor;
    const retrato = retratoPersonalizado(valor);
    personalizado.hidden = !retrato;
    const img = personalizado.querySelector("img");
    if (retrato) img.src = retrato;
    else img.removeAttribute("src");
  }
  for (const radio of radios) radio.addEventListener("change", () => {
    revision++;
    leyendo = false;
    aviso.textContent = "";
    actualizarVista();
  });
  archivo.addEventListener("change", async () => {
    const elegido = archivo.files[0];
    archivo.value = "";
    if (!elegido) return;
    const intento = ++revision;
    leyendo = true;
    aviso.textContent = "Preparando la imagen…";
    cambio();
    try {
      const valor = await convertirImagen(elegido);
      if (revision !== intento) return;
      mostrarPersonal(valor);
      personalizado.querySelector("input").checked = true;
      aviso.textContent = "";
    } catch (error) {
      if (revision === intento) aviso.textContent = error.message || "No se pudo abrir la imagen.";
    } finally {
      if (revision === intento) { leyendo = false; actualizarVista(); }
    }
  });

  return {
    async cargar(usuario, pedir, sigueActivo) {
      const intento = revision;
      try {
        const { avatar } = await pedir("/api/game/avatar", { headers: { Authorization: `Bearer ${await usuario.getIdToken()}` } });
        if (!sigueActivo()) return;
        if (intento !== revision) return;
        guardado = avatar;
        if (avatar?.tipo === "personalizado") mostrarPersonal(avatar.valor);
        const radio = avatar?.tipo === "personalizado" && !personalizado.hidden ? personalizado.querySelector("input")
          : radios.find(item => item.value === avatar?.valor) || radios[0];
        radio.checked = true;
        actualizarVista();
      } catch {
        if (sigueActivo() && revision === intento) aviso.textContent = "No se pudo consultar tu avatar. Elige uno para continuar.";
      }
    },
    eleccion() {
      const opcion = radios.find(radio => radio.checked);
      if (!opcion || leyendo) return null;
      if (opcion.value === "personalizado") return { tipo: "personalizado", valor: imagenPersonal };
      return { tipo: "predeterminado", valor: opcion.value };
    },
    async guardar(eleccion, cabeceras, pedir, sigueActivo) {
      if (guardado?.tipo === eleccion.tipo && guardado.valor === eleccion.valor) return;
      await pedir("/api/game/avatar", { method: "PUT", headers: cabeceras, body: JSON.stringify(eleccion) });
      if (sigueActivo()) guardado = eleccion;
    },
    limpiar() {
      revision++;
      leyendo = false;
      guardado = undefined;
      mostrarPersonal(null);
      radios.forEach(radio => { radio.checked = false; });
      archivo.value = "";
      actualizarVista();
    },
  };
}

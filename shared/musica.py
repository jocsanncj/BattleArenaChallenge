"""Melodía de victoria que comparten la ventana Pygame y el cliente web."""
from array import array
from functools import lru_cache
from io import BytesIO
import math
import sys
import wave


def make_celebration_pcm(sample_rate: int = 22050, channels: int = 2) -> bytes:
    """
    Sintetiza una melodía original de ocho segundos con acordes y bajo, sin descargar archivos de música.
    """
    # El escritorio pasa la frecuencia y el número de canales de su mezclador. Para el móvil se genera un
    # solo canal. Ambos reciben muestras PCM de 16 bits que representan la misma melodía.
    if sample_rate <= 0 or channels not in {1, 2}:
        raise ValueError("La frecuencia de muestreo debe ser positiva y el número de canales debe ser 1 o 2.")
    notes = [72, 76, 79, 84, 79, 76, 74, 79,
             69, 72, 76, 81, 79, 76, 72, 69,
             65, 69, 72, 77, 76, 72, 69, 65,
             67, 71, 74, 79, 83, 79, 74, 71]
    roots = [48, 45, 41, 43]
    pcm = array("h")

    # A partir del número de nota calcula las oscilaciones por segundo. La nota 69 equivale a 440 Hz
    # y una octava (12 notas) duplica la frecuencia. Se usa tanto para la melodía como para el acompañamiento.
    def frequency(note):
        return 440 * 2 ** ((note - 69) / 12)

    for index in range(sample_rate * 8):
        t = index / sample_rate
        local = t % 0.25
        step = min(int(t / 0.25), len(notes) - 1)
        envelope = min(local / 0.015, 1) * max(0, 1 - local / 0.25) ** 0.5
        hz = frequency(notes[step])
        lead = (math.sin(math.tau * hz * t)
                + 0.2 * math.sin(math.tau * hz * 2 * t)) * envelope
        root = roots[min(int(t / 2), 3)]
        chord = sum(math.sin(math.tau * frequency(root + interval) * t)
                    for interval in (12, 15 if root == 45 else 16, 19)) / 3
        bass = math.sin(math.tau * frequency(root) * t)
        beat = math.exp(-(t % 0.5) * 28) * math.sin(math.tau * 90 * t)
        fade = min(t / 0.025, (8 - t) / 0.025, 1)
        sample = int(max(-1, min(1, (lead * 0.32 + chord * 0.13 + bass * 0.14 + beat * 0.08) * fade)) * 32767)
        for _ in range(channels):
            pcm.append(sample)
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()


@lru_cache(maxsize=1)
def wav_celebracion() -> bytes:
    """Envuelve la misma melodía PCM en un WAV mono que el navegador puede reproducir."""
    # La cabecera WAV indica que las muestras usan un canal, dos bytes por muestra y una frecuencia de 22 050 Hz.
    # La caché permite que /movil/audio/resultados.wav entregue los mismos bytes en cada solicitud.
    sample_rate = 22050
    salida = BytesIO()
    with wave.open(salida, "wb") as wav:
        wav.setparams((1, 2, sample_rate, 0, "NONE", "not compressed"))
        wav.writeframes(make_celebration_pcm(sample_rate, 1))
    return salida.getvalue()

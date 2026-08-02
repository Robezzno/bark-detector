#!/usr/bin/env python3
"""
generar_sonidos.py
===============================================================================
Genera los ficheros WAV de respuesta. No necesita tarjeta de sonido: solo
numpy y el modulo `wave` de la libreria estandar.

    python3 generar_sonidos.py                 # genera todos en ./sonidos/
    python3 generar_sonidos.py --duracion 4    # 4 segundos cada uno

Ficheros generados:
    ultrasonico.wav   barrido 18-23 kHz pulsado. Por encima del limite de la
                      audicion humana adulta y dentro del rango canino. Es el
                      principio de los disuasores comerciales antiladrido.
    estridente.wav    sirena disonante 1.5-4.5 kHz, la banda donde el oido
                      humano es mas sensible. Audible.
    mixto.wav         alterna los dos.
    chirrido.wav      ruido de banda estrecha con modulacion rapida, tipo
                      "unas contra pizarra". Muy saliente a bajo volumen.

Nota: para el ultrasonico hace falta 48 kHz de muestreo y un altavoz que
llegue ahi (un tweeter piezoelectrico barato vale; los altavoces de portatil
NO). Comprueba con un movil y una app de analizador de espectro que esta
saliendo algo por encima de 18 kHz.
===============================================================================
"""

import argparse
import os
import wave

import numpy as np

FS = 48000  # 48 kHz: necesario para que quepan los 23 kHz del ultrasonido


def _envolvente(n, ataque_ms=5, caida_ms=15):
    """Rampas de entrada y salida para que no chasquee al cortar."""
    env = np.ones(n)
    na = max(1, int(FS * ataque_ms / 1000))
    nc = max(1, int(FS * caida_ms / 1000))
    env[:na] = np.linspace(0, 1, na)
    env[-nc:] = np.linspace(1, 0, nc)
    return env


def _barrido(f0, f1, dur):
    """Barrido lineal de frecuencia con fase continua."""
    t = np.linspace(0, dur, int(FS * dur), endpoint=False)
    fase = 2 * np.pi * (f0 * t + 0.5 * (f1 - f0) / dur * t**2)
    return np.sin(fase)


def ultrasonico(dur):
    """Pulsos de barrido 18->23->18 kHz. El pulsado impide que el perro
    se acostumbre, que es el fallo de los emisores continuos."""
    pulso = 0.09  # 90 ms por barrido
    trozos = []
    subir = True
    while sum(len(c) for c in trozos) < FS * dur:
        s = _barrido(18000, 23000, pulso) if subir else _barrido(23000, 18000, pulso)
        s *= _envolvente(len(s), 3, 3)
        trozos.append(s)
        trozos.append(np.zeros(int(FS * 0.03)))  # silencio entre pulsos
        subir = not subir
    x = np.concatenate(trozos)[: int(FS * dur)]
    return x * 0.95


def estridente(dur):
    """Sirena de dos tonos en tritono (el intervalo mas disonante) con
    modulacion de amplitud a 7 Hz, que es la tasa a la que el oido peor
    se adapta. Armonicos impares para darle aspereza."""
    n = int(FS * dur)
    t = np.arange(n) / FS

    # Portadora que salta entre pares en tritono, 6 saltos por segundo
    pares = [(2100, 2970), (2300, 3250), (1800, 2545), (2600, 3675)]
    salto = 1.0 / 6
    x = np.zeros(n)
    for i in range(int(np.ceil(dur / salto))):
        a, b = pares[i % len(pares)]
        ini, fin = int(i * salto * FS), min(n, int((i + 1) * salto * FS))
        if ini >= fin:
            break
        tt = t[ini:fin] - t[ini]
        seg = np.zeros(fin - ini)
        for f, peso in ((a, 1.0), (b, 0.9)):
            # ligero barrido ascendente dentro de cada salto -> efecto sirena
            ff = f * (1 + 0.12 * tt / salto)
            fase = 2 * np.pi * np.cumsum(ff) / FS
            seg += peso * (np.sin(fase) + 0.35 * np.sin(3 * fase) + 0.2 * np.sin(5 * fase))
        seg *= _envolvente(len(seg), 2, 2)
        x[ini:fin] = seg

    x *= 0.55 + 0.45 * np.sin(2 * np.pi * 7 * t)  # modulacion a 7 Hz
    x /= np.max(np.abs(x)) + 1e-9
    return x * 0.95 * _envolvente(n)


def chirrido(dur):
    """Ruido filtrado en banda 2.5-4 kHz con modulacion irregular.
    Suena a metal rascando cristal. Muy eficaz a volumen bajo."""
    n = int(FS * dur)
    rng = np.random.default_rng(1234)  # semilla fija: resultado reproducible
    ruido = rng.standard_normal(n)

    # Filtro de banda por FFT (mas simple que disenar un IIR y suficiente)
    espectro = np.fft.rfft(ruido)
    freqs = np.fft.rfftfreq(n, 1 / FS)
    mascara = np.exp(-((freqs - 3200) ** 2) / (2 * 450**2))
    x = np.fft.irfft(espectro * mascara, n)

    t = np.arange(n) / FS
    modulacion = 0.4 + 0.6 * np.abs(np.sin(2 * np.pi * 11 * t) * np.sin(2 * np.pi * 3.3 * t))
    x *= modulacion
    x /= np.max(np.abs(x)) + 1e-9
    return x * 0.95 * _envolvente(n)


def mixto(dur):
    """Alterna ultrasonido y estridente en bloques de 0.5 s."""
    bloque = 0.5
    trozos, usa_ultra = [], True
    restante = dur
    while restante > 0.01:
        d = min(bloque, restante)
        trozos.append(ultrasonico(d) if usa_ultra else estridente(d))
        usa_ultra = not usa_ultra
        restante -= d
    return np.concatenate(trozos)[: int(FS * dur)]


def guardar(ruta, x):
    """Escribe WAV mono de 16 bits."""
    datos = np.clip(x, -1.0, 1.0)
    pcm = (datos * 32767).astype("<i2")
    with wave.open(ruta, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes(pcm.tobytes())
    print(f"  {ruta}  ({len(pcm) / FS:.1f} s, {FS} Hz)")


def main():
    ap = argparse.ArgumentParser(description="Genera los WAV de respuesta")
    ap.add_argument("--duracion", type=float, default=3.0, help="segundos (por defecto 3)")
    ap.add_argument("--salida", default="sonidos", help="directorio de salida")
    args = ap.parse_args()

    os.makedirs(args.salida, exist_ok=True)
    d = args.duracion
    print(f"Generando en {args.salida}/ ...")
    guardar(os.path.join(args.salida, "ultrasonico.wav"), ultrasonico(d))
    guardar(os.path.join(args.salida, "estridente.wav"), estridente(d))
    guardar(os.path.join(args.salida, "chirrido.wav"), chirrido(d))
    guardar(os.path.join(args.salida, "mixto.wav"), mixto(d))
    print("\nListo. Para el DFPlayer Mini, copia el elegido a la microSD")
    print("como 0001.mp3 (convirtiendolo antes a MP3) o 0001.wav.")


if __name__ == "__main__":
    main()

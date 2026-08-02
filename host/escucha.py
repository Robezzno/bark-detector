#!/usr/bin/env python3
"""
escucha.py
===============================================================================
Detector de ladridos por PC. Hace lo mismo que el firmware de Arduino pero con
analisis espectral completo (FFT), asi que la tasa de acierto es bastante mayor.
Ademas registra cada evento en un CSV con marca de tiempo, apto para analisis
posterior o como serie temporal de actividad acustica.

Modos de funcionamiento
-----------------------
  --fuente micro     escucha por el microfono del PC/USB  (recomendado)
  --fuente serie     escucha los eventos que manda el Arduino por el puerto
                     serie, y responde desde el PC

Uso tipico
----------
  python3 generar_sonidos.py                       # crea los WAV una vez
  python3 escucha.py --calibrar                    # mide tu ruido de fondo
  python3 escucha.py --solo-registrar              # 1 noche solo registrando
  python3 escucha.py --respuesta ultrasonico       # ya respondiendo
  python3 escucha.py --resumen registro.csv        # informe de lo registrado

Empieza SIEMPRE por --solo-registrar un ciclo completo de 24 h: permite ajustar
los umbrales sin emitir nada y deja una linea base de actividad.
===============================================================================
"""

import argparse
import csv
import os
import queue
import subprocess
import sys
import time
import wave
from collections import deque
from datetime import datetime, time as dtime

import numpy as np

# ---------------------------------------------------------------------------
# PARAMETROS DE DETECCION
# ---------------------------------------------------------------------------

FS = 44100
BLOQUE = 1024                  # 23.2 ms por bloque
MS_BLOQUE = 1000 * BLOQUE / FS

BANDA_LADRIDO = (300, 4000)    # donde vive la energia de un ladrido
BANDA_GRAVE = (20, 250)        # trafico, obras, portazos

UMBRAL_DB = 12.0               # dB por encima del fondo para abrir evento
HISTERESIS_DB = 6.0            # dB por encima del fondo para mantenerlo
DUR_MIN_MS = 80
DUR_MAX_MS = 700
CENTROIDE_MIN = 400            # Hz
CENTROIDE_MAX = 3500           # Hz
RATIO_MIN_DB = 3.0             # banda ladrido debe superar a la grave

LADRIDOS_PARA_DISPARAR = 3
VENTANA_RAFAGA_S = 8.0

ENFRIAMIENTO_S = 20.0          # pausa minima entre respuestas
MAX_RESPUESTAS_HORA = 12
SORDO_TRAS_RESPUESTA_S = 1.5   # no escuchar justo despues (te oirias a ti)


# ---------------------------------------------------------------------------
# REPRODUCCION
# ---------------------------------------------------------------------------

class Reproductor:
    """Reproduce un WAV. Usa sounddevice si esta; si no, tira de aplay/paplay
    (Linux) o afplay (macOS), asi funciona aunque no instales nada."""

    def __init__(self, ruta, volumen=1.0):
        self.ruta = ruta
        self.volumen = max(0.0, min(1.0, volumen))
        self.datos = None
        self.fs = None
        self.backend = None
        self._sd = None

        if not os.path.isfile(ruta):
            raise FileNotFoundError(
                f"No existe {ruta}. Ejecuta primero: python3 generar_sonidos.py"
            )

        try:
            import sounddevice as sd
            self._sd = sd
            with wave.open(ruta, "rb") as w:
                self.fs = w.getframerate()
                bruto = w.readframes(w.getnframes())
            self.datos = np.frombuffer(bruto, dtype="<i2").astype(np.float32) / 32768.0
            self.datos *= self.volumen
            self.backend = "sounddevice"
        except ImportError:
            for cmd in (["paplay"], ["aplay", "-q"], ["afplay"]):
                if _existe(cmd[0]):
                    self.backend = cmd
                    break
            if self.backend is None:
                raise RuntimeError(
                    "Sin sounddevice y sin aplay/paplay/afplay. "
                    "Instala: pip install sounddevice"
                )

    def reproducir(self, dur_max_s=None):
        if self.backend == "sounddevice":
            x = self.datos
            if dur_max_s:
                x = x[: int(self.fs * dur_max_s)]
            self._sd.play(x, self.fs, blocking=True)
        else:
            subprocess.run(self.backend + [self.ruta],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _existe(prog):
    from shutil import which
    return which(prog) is not None


# ---------------------------------------------------------------------------
# REGISTRO
# ---------------------------------------------------------------------------

class Registro:
    CABECERA = ["fecha_hora", "duracion_ms", "pico_db", "centroide_hz", "respondido"]

    def __init__(self, ruta):
        self.ruta = ruta
        nuevo = not os.path.isfile(ruta)
        self.f = open(ruta, "a", newline="", encoding="utf-8")
        self.w = csv.writer(self.f)
        if nuevo:
            self.w.writerow(self.CABECERA)
            self.f.flush()

    def anotar(self, dur_ms, pico_db, centroide, respondido=False):
        self.w.writerow([
            datetime.now().isoformat(timespec="seconds"),
            round(dur_ms), round(pico_db, 1), round(centroide), int(respondido),
        ])
        self.f.flush()

    def cerrar(self):
        self.f.close()


def resumen(ruta):
    """Informe por dia y por hora. Esto es lo que imprimes y adjuntas."""
    if not os.path.isfile(ruta):
        sys.exit(f"No existe {ruta}")

    filas = []
    with open(ruta, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            filas.append(r)
    if not filas:
        sys.exit("El registro esta vacio.")

    por_dia = {}
    por_hora = {}
    for r in filas:
        ts = datetime.fromisoformat(r["fecha_hora"])
        por_dia.setdefault(ts.date(), []).append(ts)
        por_hora[ts.hour] = por_hora.get(ts.hour, 0) + 1

    print(f"\nREGISTRO DE LADRIDOS  ({ruta})")
    print(f"Total: {len(filas)} ladridos entre "
          f"{filas[0]['fecha_hora']} y {filas[-1]['fecha_hora']}\n")

    print("Por dia:")
    for dia in sorted(por_dia):
        ts = sorted(por_dia[dia])
        nocturnos = sum(1 for t in ts if t.hour >= 22 or t.hour < 8)
        print(f"  {dia}  {len(ts):5d} ladridos   "
              f"primero {ts[0]:%H:%M}  ultimo {ts[-1]:%H:%M}   "
              f"nocturnos (22h-8h): {nocturnos}")

    print("\nPor hora del dia:")
    pico = max(por_hora.values())
    for h in range(24):
        n = por_hora.get(h, 0)
        barra = "#" * int(40 * n / pico) if n else ""
        marca = " <- horario de descanso" if (h >= 22 or h < 8) and n else ""
        print(f"  {h:02d}:00  {n:5d}  {barra}{marca}")
    print()


# ---------------------------------------------------------------------------
# DETECTOR
# ---------------------------------------------------------------------------

class Detector:
    """Maquina de estados: silencio -> evento -> clasificacion -> rafaga."""

    def __init__(self, umbral_db=UMBRAL_DB):
        self.umbral_db = umbral_db
        self.freqs = np.fft.rfftfreq(BLOQUE, 1 / FS)
        self.i_ladrido = np.where(
            (self.freqs >= BANDA_LADRIDO[0]) & (self.freqs <= BANDA_LADRIDO[1]))[0]
        self.i_grave = np.where(
            (self.freqs >= BANDA_GRAVE[0]) & (self.freqs <= BANDA_GRAVE[1]))[0]
        self.ventana = np.hanning(BLOQUE)

        self.fondo_db = None
        self.en_evento = False
        self.bloques = 0
        self.pico_db = -120.0
        self.centroides = []
        self.ratios = []

    def _db(self, x):
        return 10 * np.log10(x + 1e-12)

    def procesar(self, bloque):
        """Devuelve (dur_ms, pico_db, centroide) si acaba de cerrarse un
        evento clasificado como ladrido; si no, None."""
        esp = np.abs(np.fft.rfft(bloque * self.ventana)) ** 2

        e_ladrido = float(esp[self.i_ladrido].sum())
        e_grave = float(esp[self.i_grave].sum())
        db = self._db(e_ladrido)

        if self.fondo_db is None:
            self.fondo_db = db

        if not self.en_evento:
            if db > self.fondo_db + self.umbral_db:
                self.en_evento = True
                self.bloques = 1
                self.pico_db = db
                self.centroides = [self._centroide(esp)]
                self.ratios = [db - self._db(e_grave)]
            else:
                # el fondo solo se adapta en silencio, y despacio
                self.fondo_db += 0.02 * (db - self.fondo_db)
            return None

        if db > self.fondo_db + HISTERESIS_DB and self.bloques * MS_BLOQUE < DUR_MAX_MS + 100:
            self.bloques += 1
            self.pico_db = max(self.pico_db, db)
            self.centroides.append(self._centroide(esp))
            self.ratios.append(db - self._db(e_grave))
            return None

        # cierre del evento
        self.en_evento = False
        dur_ms = self.bloques * MS_BLOQUE
        centroide = float(np.mean(self.centroides))
        ratio = float(np.mean(self.ratios))
        realce = self.pico_db - self.fondo_db

        es_ladrido = (
            DUR_MIN_MS <= dur_ms <= DUR_MAX_MS
            and CENTROIDE_MIN <= centroide <= CENTROIDE_MAX
            and ratio >= RATIO_MIN_DB
            and realce >= self.umbral_db
        )
        return (dur_ms, realce, centroide) if es_ladrido else None

    def _centroide(self, esp):
        i = self.i_ladrido
        pot = esp[i]
        s = pot.sum()
        return float((self.freqs[i] * pot).sum() / s) if s > 0 else 0.0

    def reiniciar_fondo(self):
        self.fondo_db = None
        self.en_evento = False


# ---------------------------------------------------------------------------
# POLITICA DE RESPUESTA
# ---------------------------------------------------------------------------

class Politica:
    """Decide si se responde. Aqui viven los limites que te evitan problemas."""

    def __init__(self, args):
        self.args = args
        self.ladridos = deque(maxlen=LADRIDOS_PARA_DISPARAR)
        self.ultima = 0.0
        self.en_hora = 0
        self.inicio_hora = time.time()

    def _en_horario_permitido(self):
        if not self.args.horario:
            return True, ""
        ini, fin = self.args.horario
        ahora = datetime.now().time()
        dentro = (ini <= ahora <= fin) if ini <= fin else (ahora >= ini or ahora <= fin)
        return dentro, "" if dentro else "fuera del horario permitido"

    def registrar_ladrido(self):
        """Devuelve (responder: bool, motivo: str)."""
        ahora = time.time()
        self.ladridos.append(ahora)

        if time.time() - self.inicio_hora >= 3600:
            self.inicio_hora = time.time()
            self.en_hora = 0

        if len(self.ladridos) < LADRIDOS_PARA_DISPARAR:
            return False, ""
        if ahora - self.ladridos[0] > VENTANA_RAFAGA_S:
            return False, ""
        if self.args.solo_registrar:
            return False, "modo solo-registrar"
        if ahora - self.ultima < ENFRIAMIENTO_S:
            return False, "enfriando"
        if self.en_hora >= self.args.max_hora:
            return False, f"tope de {self.args.max_hora} respuestas/hora alcanzado"

        permitido, motivo = self._en_horario_permitido()
        if not permitido:
            return False, motivo

        self.ultima = ahora
        self.en_hora += 1
        self.ladridos.clear()
        return True, ""


# ---------------------------------------------------------------------------
# BUCLES PRINCIPALES
# ---------------------------------------------------------------------------

def bucle_micro(args, reg, rep):
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("Falta sounddevice.  pip install sounddevice numpy")

    det = Detector(args.umbral)
    pol = Politica(args)
    cola = queue.Queue()

    def callback(indata, frames, tiempo, estado):
        if estado:
            pass  # xruns ocasionales: no son criticos para esto
        cola.put(indata[:, 0].copy())

    print(f"Escuchando en el dispositivo {args.dispositivo or 'por defecto'} "
          f"({FS} Hz, bloques de {MS_BLOQUE:.0f} ms)")
    print(f"Umbral: {args.umbral:.0f} dB sobre el fondo   "
          f"Rafaga: {LADRIDOS_PARA_DISPARAR} ladridos en {VENTANA_RAFAGA_S:.0f} s")
    print(f"Respuesta: {'NINGUNA (solo registro)' if rep is None else rep.ruta}")
    print("Ctrl-C para parar.\n")

    total = 0
    with sd.InputStream(samplerate=FS, blocksize=BLOQUE, channels=1,
                        dtype="float32", device=args.dispositivo,
                        callback=callback):
        while True:
            bloque = cola.get()
            ev = det.procesar(bloque)
            if ev is None:
                continue

            dur, realce, centroide = ev
            total += 1
            responder, motivo = pol.registrar_ladrido()
            reg.anotar(dur, realce, centroide, responder)

            marca = datetime.now().strftime("%H:%M:%S")
            print(f"[{marca}] ladrido #{total}  {dur:4.0f} ms  "
                  f"+{realce:4.1f} dB  {centroide:4.0f} Hz"
                  + (f"   -> {motivo}" if motivo else ""))

            if responder:
                print(f"[{marca}] >>> RAFAGA: respondiendo "
                      f"({pol.en_hora}/{args.max_hora} esta hora)")
                rep.reproducir(args.duracion)
                # vaciar lo capturado durante la respuesta y reajustar el fondo
                time.sleep(SORDO_TRAS_RESPUESTA_S)
                while not cola.empty():
                    cola.get_nowait()
                det.reiniciar_fondo()


def bucle_serie(args, reg, rep):
    try:
        import serial
    except ImportError:
        sys.exit("Falta pyserial.  pip install pyserial")

    pol = Politica(args)
    ser = serial.Serial(args.puerto, args.baudios, timeout=1)
    print(f"Conectado a {args.puerto} @ {args.baudios}. Ctrl-C para parar.\n")
    time.sleep(2)  # el Uno se reinicia al abrir el puerto

    total = 0
    while True:
        linea = ser.readline().decode("utf-8", "replace").strip()
        if not linea:
            continue
        if not linea.startswith("LADRIDO"):
            if linea.startswith(("INFO", "RAFAGA", "DISPARO")):
                print(f"    arduino: {linea}")
            continue

        campos = dict(
            p.split("=", 1) for p in linea.split(",")[1:] if "=" in p
        )
        dur = float(campos.get("dur", 0))
        freq = float(campos.get("f", 0))
        pico = float(campos.get("pico", 0))
        fondo = float(campos.get("fondo", 1)) or 1.0
        realce = 20 * np.log10(pico / fondo) if pico > 0 else 0.0

        total += 1
        responder, motivo = pol.registrar_ladrido()
        reg.anotar(dur, realce, freq, responder)

        marca = datetime.now().strftime("%H:%M:%S")
        print(f"[{marca}] ladrido #{total}  {dur:4.0f} ms  "
              f"+{realce:4.1f} dB  {freq:4.0f} Hz"
              + (f"   -> {motivo}" if motivo else ""))

        if responder:
            print(f"[{marca}] >>> RAFAGA: respondiendo")
            rep.reproducir(args.duracion)
            time.sleep(SORDO_TRAS_RESPUESTA_S)
            ser.reset_input_buffer()


def calibrar(args):
    """Escucha 30 s y propone un umbral. Hazlo con el ruido habitual de la
    calle, no en silencio absoluto."""
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("Falta sounddevice.  pip install sounddevice numpy")

    det = Detector(args.umbral)
    niveles = []
    print("Calibrando 30 s. Deja el ambiente normal (sin ladridos si puedes)...")
    with sd.InputStream(samplerate=FS, blocksize=BLOQUE, channels=1,
                        dtype="float32", device=args.dispositivo) as s:
        fin = time.time() + 30
        while time.time() < fin:
            bloque, _ = s.read(BLOQUE)
            esp = np.abs(np.fft.rfft(bloque[:, 0] * det.ventana)) ** 2
            niveles.append(10 * np.log10(esp[det.i_ladrido].sum() + 1e-12))
            restante = fin - time.time()
            print(f"\r  {restante:4.1f} s  nivel actual {niveles[-1]:6.1f} dB",
                  end="", flush=True)

    a = np.array(niveles)
    p50, p95, pmax = np.percentile(a, 50), np.percentile(a, 95), a.max()
    print(f"\n\n  fondo (mediana): {p50:6.1f} dB")
    print(f"  percentil 95:    {p95:6.1f} dB")
    print(f"  maximo:          {pmax:6.1f} dB")
    sugerido = max(8.0, (p95 - p50) + 6.0)
    print(f"\n  Umbral sugerido: --umbral {sugerido:.0f}")
    print("  (si te salen falsos positivos subelo de 3 en 3; si no detecta, bajalo)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _hora(txt):
    try:
        h, m = txt.split(":")
        return dtime(int(h), int(m))
    except Exception:
        raise argparse.ArgumentTypeError(f"hora invalida: {txt} (usa HH:MM)")


def _rango(txt):
    try:
        a, b = txt.split("-")
        return (_hora(a), _hora(b))
    except ValueError:
        raise argparse.ArgumentTypeError("usa el formato HH:MM-HH:MM")


def main():
    ap = argparse.ArgumentParser(
        description="Detector de ladridos con respuesta sonora y registro",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Uso tipico")[-1] if __doc__ else None,
    )
    ap.add_argument("--fuente", choices=["micro", "serie"], default="micro")
    ap.add_argument("--respuesta", default="ultrasonico",
                    choices=["ultrasonico", "estridente", "mixto", "chirrido"],
                    help="que sonido devolver (por defecto ultrasonico)")
    ap.add_argument("--sonidos", default="sonidos", help="directorio de los WAV")
    ap.add_argument("--volumen", type=float, default=0.8, help="0.0 a 1.0")
    ap.add_argument("--duracion", type=float, default=2.5,
                    help="segundos maximos de cada respuesta")
    ap.add_argument("--umbral", type=float, default=UMBRAL_DB,
                    help="dB sobre el ruido de fondo (usa --calibrar)")
    ap.add_argument("--max-hora", type=int, default=MAX_RESPUESTAS_HORA,
                    help="tope de respuestas por hora")
    ap.add_argument("--horario", type=_rango, default=None, metavar="HH:MM-HH:MM",
                    help="franja en la que se permite responder, p.ej. 09:00-21:30")
    ap.add_argument("--solo-registrar", action="store_true",
                    help="detecta y registra, pero no emite ningun sonido")
    ap.add_argument("--registro", default="registro.csv")
    ap.add_argument("--dispositivo", default=None,
                    help="indice o nombre del microfono (ver --listar)")
    ap.add_argument("--puerto", default="/dev/ttyUSB0", help="puerto serie del Arduino")
    ap.add_argument("--baudios", type=int, default=115200)
    ap.add_argument("--calibrar", action="store_true", help="mide el ruido de fondo y sale")
    ap.add_argument("--listar", action="store_true", help="lista dispositivos de audio")
    ap.add_argument("--probar", action="store_true", help="reproduce la respuesta y sale")
    ap.add_argument("--resumen", metavar="CSV", help="imprime el informe de un registro")
    args = ap.parse_args()

    if args.resumen:
        resumen(args.resumen)
        return
    if args.listar:
        import sounddevice as sd
        print(sd.query_devices())
        return
    if args.calibrar:
        calibrar(args)
        return

    ruta_wav = os.path.join(args.sonidos, f"{args.respuesta}.wav")
    rep = None
    if not args.solo_registrar or args.probar:
        rep = Reproductor(ruta_wav, args.volumen)

    if args.probar:
        print(f"Reproduciendo {ruta_wav} ...")
        rep.reproducir(args.duracion)
        return

    reg = Registro(args.registro)
    try:
        if args.fuente == "micro":
            bucle_micro(args, reg, rep)
        else:
            bucle_serie(args, reg, rep)
    except KeyboardInterrupt:
        print("\nParado.")
    finally:
        reg.cerrar()
        print(f"Registro guardado en {args.registro}")
        print(f"Informe:  python3 escucha.py --resumen {args.registro}")


if __name__ == "__main__":
    main()

# bark-detector

Detector acústico de ladridos con respuesta sonora automática y registro de
eventos. Escucha por micrófono, distingue un ladrido del resto del ruido
ambiente, y ante una **ráfaga** (varios ladridos en pocos segundos) dispara una
respuesta sonora configurable y anota el evento con marca de tiempo.

Dos implementaciones, usables por separado o combinadas:

| | dónde corre | detección | características |
|---|---|---|---|
| `firmware/detector_ladridos/` | Arduino (ATmega328P) | envolvente + cruces por cero | autónomo, 24/7, ~10 KB de flash |
| `host/escucha.py` | PC (Python) | FFT: bandas de energía + centroide espectral | más preciso, registro CSV, informes |

Verificado con señales sintéticas: **4 de 4 ladridos detectados, 0 falsos
positivos** con 2 s de ruido grave continuo tipo tráfico. El firmware compila en
10.786 bytes de flash (33 %) y 414 bytes de RAM (20 %) en un Arduino Uno.

---

## Para qué sirve

El proyecto está escrito alrededor del ladrido, pero el pipeline —umbral
adaptativo, detección de onsets, clasificación por duración y contenido
espectral, lógica de ráfaga, respuesta con límites— es genérico. Usos:

**Con perros**

- **Bienestar animal / ansiedad por separación.** Dejarlo en modo
  `--solo-registrar` mientras no estás en casa te dice cuánto ladra tu perro,
  a qué horas y si se dispara con eventos concretos (el ascensor, el cartero).
  Es un dato que un veterinario o un etólogo puede usar, y que de otro modo no
  tienes.
- **Adiestramiento antiladrido.** Es el principio de funcionamiento de los
  disuasores ultrasónicos comerciales, pero con detección propia y ajustable
  en vez de un umbral fijo de fábrica.
- **Monitorización de perreras, refugios o residencias caninas**, para
  cuantificar niveles de estrés acústico a lo largo del día.

**Como detector genérico de eventos acústicos**

- Cambiando cuatro constantes (`BANDA_LADRIDO`, `DUR_MIN_MS`, `DUR_MAX_MS`,
  `CENTROIDE_*`) el mismo código detecta **cualquier evento impulsivo**: rotura
  de cristal, portazos, alarmas, sirenas, disparos, chirridos de maquinaria,
  goteo. La clasificación es un rectángulo en el plano duración × frecuencia.
- **Domótica**: disparar cualquier acción ante un patrón sonoro, sin depender
  de un asistente en la nube ni enviar audio a ningún sitio. Todo el
  procesamiento es local.
- **Bioacústica y ciencia ciudadana**: registro de actividad animal por
  vocalización, con marca de tiempo y series por hora.
- **Medida de contaminación acústica**: con un micrófono de sensibilidad fija
  (INMP441 en vez del MAX9814 con AGC) el registro pasa a dar dB SPL reales.
  Ver [HARDWARE.md](HARDWARE.md#2-el-micrófono).
- **Base para clasificación con ML**: el registro CSV y los eventos segmentados
  son directamente el conjunto de datos etiquetado que necesitas para entrenar
  un clasificador (Edge Impulse, MFCC + CNN) si quieres distinguir *qué* perro
  ladra, o separar ladrido de aullido.

**Educativo**

Es un ejemplo compacto y real de muestreo de ADC por interrupción en
free-running, filtrado IIR de un polo para seguimiento de continua, detección de
onsets con umbral adaptativo, estimación de frecuencia por cruces por cero,
Goertzel frente a FFT, y máquinas de estados con histéresis.

---

## Uso responsable

El proyecto puede emitir sonido audible a alto nivel. Antes de conectar el
altavoz:

- **Nivel.** Estos sonidos pueden superar los 100 dB SPL a un metro. No te
  sitúes cerca del emisor mientras dispara. El modo ultrasónico es igual de
  lesivo para el oído por el hecho de no oírse.
- **Dirígelo a tu propio espacio.** Emitir ruido audible hacia una vivienda
  ajena está regulado en prácticamente cualquier jurisdicción, y un emisor
  automatizado deja registro de su propia actividad.
- **Otros animales.** El ultrasonido alcanza también a gatos, roedores y otros
  perros dentro del cono de emisión.
- **Ansiedad.** Si el ladrido es por ansiedad de separación, el estímulo
  aversivo la agrava. En ese caso el valor del proyecto está en el registro, no
  en la respuesta.

Por eso el modo por defecto es `RESP_NINGUNA` en el firmware, y el script
incluye `--solo-registrar`, `--horario` y `--max-hora`.

---

## Arranque rápido (solo PC, sin Arduino)

```bash
cd host
pip install -r requirements.txt        # Debian/Ubuntu: sudo apt install libportaudio2
python3 generar_sonidos.py             # crea sonidos/*.wav
python3 escucha.py --listar            # ver micrófonos disponibles
python3 escucha.py --calibrar          # 30 s midiendo el ruido de fondo
```

Un ciclo de 24 h solo registrando, para ajustar sin emitir nada:

```bash
python3 escucha.py --solo-registrar --umbral 14 --registro registro.csv
```

Después, el informe:

```bash
python3 escucha.py --resumen registro.csv
```

```
Por dia:
  2026-08-01    340 ladridos   primero 06:12  ultimo 23:58   nocturnos (22h-8h): 47

Por hora del dia:
  06:00     31  ##########  <- horario de descanso
  ...
```

Y ya con respuesta activa:

```bash
python3 escucha.py --respuesta ultrasonico --umbral 14 \
                   --max-hora 8 --horario 08:00-22:00 --volumen 0.7
```

### Opciones

| opción | descripción |
|---|---|
| `--umbral N` | dB por encima del fondo para abrir un evento. Súbelo si hay falsos positivos, bájalo si no detecta. `--calibrar` propone uno |
| `--respuesta X` | `ultrasonico`, `estridente`, `mixto` o `chirrido` |
| `--horario HH:MM-HH:MM` | franja en la que se permite emitir. Fuera de ella solo registra |
| `--max-hora N` | tope duro de respuestas por hora |
| `--duracion S` | segundos máximos de cada respuesta |
| `--solo-registrar` | detecta y anota, no emite nada |
| `--probar` | reproduce la respuesta una vez y sale |
| `--resumen CSV` | imprime el informe de un registro |
| `--fuente serie --puerto /dev/ttyUSB0` | los eventos los detecta el Arduino, el PC responde y registra |

---

## Los sonidos de respuesta

`generar_sonidos.py` sintetiza cuatro WAV a 48 kHz. Contenido espectral medido
sobre los ficheros generados:

| fichero | pico | banda con el 90 % de la energía | audible |
|---|---|---|---|
| `ultrasonico.wav` | 22.762 Hz | 18.346 – 22.654 Hz | no (adultos) |
| `estridente.wav` | 2.640 Hz | 1.853 – 10.096 Hz | sí |
| `chirrido.wav` | 3.194 Hz | 2.666 – 3.722 Hz | sí |
| `mixto.wav` | — | alterna los dos anteriores | parcialmente |

El ultrasónico va **pulsado y barriendo** en vez de emitir un tono fijo:
dificulta la habituación, que es el fallo típico de los emisores continuos.

---

## Montaje con Arduino

Lista de componentes, comparativas y decisiones de diseño en
**[HARDWARE.md](HARDWARE.md)**. Resumen de conexiones:

```
MAX9814   OUT ──────────── A0
          VCC ──────────── 5V
          GND ──────────── GND
          GAIN ─────────── al aire (60 dB) o a GND (50 dB) si satura

Salida    D9  ─────────── entrada del ampli / tweeter piezo (con R serie 10R 2W)
          D8  ─────────── habilitación del ampli (MOSFET, relé o pin SD)

DFPlayer  TX  ─────────── D10
          RX  ──[1k]───── D11
          SPK_1/SPK_2 ─── altavoz  (o DAC_L/DAC_R al ampli)

Pulsador  D2  ─────────── GND      (pull-up interno)
LED       D13 ─────────── integrado, parpadea con cada ladrido
```

> La resistencia en serie con un tweeter piezoeléctrico **no es opcional**: es
> una carga capacitiva y sin ella el amplificador puede oscilar o entrar en
> sobrecorriente. Ver [HARDWARE.md](HARDWARE.md#el-detalle-que-te-va-a-quemar-un-amplificador).

### Configuración del firmware

```cpp
uint8_t modoRespuesta = RESP_NINGUNA;   // 0=nada 1=ultrasonido 2=estridente 3=mixto 4=DFPlayer
float   FACTOR_UMBRAL = 4.5;            // veces por encima del ruido de fondo
const uint8_t  LADRIDOS_PARA_DISPARAR = 3;
const uint32_t VENTANA_RAFAGA_MS      = 8000;
const uint32_t ENFRIAMIENTO_MS        = 20000;
const uint8_t  MAX_RESPUESTAS_HORA    = 12;
```

Arranca en `RESP_NINGUNA` a propósito: súbelo solo cuando el monitor serie
demuestre que detecta ladridos y no portazos.

### Monitor serie (115200 baudios)

```
INFO,ruido_fondo=38
LADRIDO,t=41230,dur=260,f=1280,pico=214,fondo=38
LADRIDO,t=42890,dur=234,f=1350,pico=198,fondo=38
DESCARTE,dur=1105,f=95,pico=180        <- ruido grave largo, correctamente ignorado
LADRIDO,t=44510,dur=247,f=1310,pico=225,fondo=38
RAFAGA,ladridos=3,en_ms=3280
DISPARO,modo=1,n_hora=1
```

Comandos: `T` probar la respuesta · `S` silenciar/rearmar · `+` / `-`
sensibilidad · `M0`…`M4` cambiar de modo · `?` ayuda.

---

## Cómo funciona la detección

Un ladrido tiene una firma acústica bastante específica. El clasificador exige
**las cuatro condiciones a la vez**, que es lo que mantiene baja la tasa de
falsos positivos:

1. **Ataque brusco** — salto de ≥12 dB sobre un ruido de fondo *adaptativo*
   (media móvil exponencial que solo se actualiza fuera de evento, así que se
   ajusta solo entre el día y la noche).
2. **Duración 80–700 ms** — descarta vehículos, obras y conversaciones.
3. **Energía en 300–4000 Hz con centroide espectral entre 400 y 3500 Hz** —
   descarta tráfico y portazos, que son graves.
4. **Ráfaga** — 3 ladridos en 8 s. Un evento aislado nunca dispara respuesta.

Tras emitir, el sistema se queda "sordo" 1,5 s y recalibra el fondo, para no
detectar su propia emisión y entrar en bucle.

### Implementación en Arduino

El ATmega328P no tiene margen para una FFT en tiempo real, así que el firmware
usa un camino más barato con las mismas cuatro condiciones:

- ADC en **free-running con interrupción** a 16 MHz / 64 / 13 = **19.231 Hz**.
- Bloques de 256 muestras (13,3 ms): suma de valores absolutos y conteo de
  cruces por cero.
- Continua estimada con un IIR de un polo en formato Q8, así el código se centra
  solo sea cual sea la polarización de salida del módulo de micrófono (el
  MAX9814, por ejemplo, saca 2 Vpp sobre 1,25 V, no sobre Vcc/2).
- Frecuencia dominante estimada como `cruces · fs / (2 · N)`.
- Histéresis al 60 % del umbral para no cortar el evento antes de tiempo.

`tone()` se usa en **D9 a propósito**: en el Uno ese pin va al Timer1, de 16
bits, y llega a 23 kHz con precisión. En los pines 3 u 11 usaría el Timer2, de 8
bits, y la cuantización se comería el barrido.

---

## Estructura

```
firmware/detector_ladridos/detector_ladridos.ino   detector + respuesta autónomos
host/generar_sonidos.py                            síntesis de los WAV de respuesta
host/escucha.py                                    detección FFT, registro, informes
host/requirements.txt
HARDWARE.md                                        investigación de componentes
```

## Dependencias

`numpy` obligatorio. `sounddevice` para captura y reproducción (necesita
`libportaudio2`), con respaldo automático a `aplay` / `paplay` / `afplay` si no
está. `pyserial` solo para `--fuente serie`.

## Licencia

MIT.

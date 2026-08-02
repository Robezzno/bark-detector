/*
 * detector_ladridos.ino
 * ---------------------------------------------------------------------------
 * Detector de ladridos + respuesta sonora automatica.
 *
 * Hardware minimo (Arduino Uno / Nano, ATmega328P a 16 MHz):
 *   - Microfono con preamplificador y salida analogica centrada en Vcc/2:
 *       MAX9814 (recomendado, tiene AGC)  o  MAX4466 / KY-037.
 *       OUT -> A0,  VCC -> 5V,  GND -> GND.
 *       (En el MAX9814 deja GAIN al aire = 60 dB; si satura, GAIN -> GND = 50 dB)
 *   - Salida de audio, elige una:
 *       A) DFPlayer Mini (MP3 desde microSD) -> el mejor sonido.
 *          RX del DFPlayer <- resistencia 1k <- D11 (TX del Arduino)
 *          TX del DFPlayer -> D10 (RX del Arduino)
 *          SPK_1 / SPK_2 -> altavoz, o DAC_R/DAC_L -> amplificador.
 *       B) Tono generado por el propio Arduino en D9 -> ampli clase D (PAM8403)
 *          o tweeter piezoelectrico. Sirve para ultrasonidos.
 *   - D8: habilitacion del amplificador (MOSFET / rele / pin SD del ampli).
 *          Se activa solo mientras suena, asi no metes ruido de fondo.
 *   - D2 a GND con pulsador: silenciar / rearmar.
 *   - D13 (LED integrado): parpadea con cada ladrido detectado.
 *
 * Deteccion: muestreo del ADC por interrupcion a ~19.2 kHz, analisis por
 * bloques de 256 muestras (13.3 ms). Un ladrido se caracteriza por
 *   - ataque brusco muy por encima del ruido de fondo adaptativo,
 *   - duracion corta (80-700 ms),
 *   - contenido espectral medio-agudo (estimado por cruces por cero).
 * Solo se responde cuando hay una RAFAGA (varios ladridos en pocos segundos),
 * para no dispararse con un portazo o una moto.
 *
 * Telemetria por serie a 115200 baudios. El script host/escucha.py puede
 * leerla para registrar y/o reproducir la respuesta desde el PC.
 * ---------------------------------------------------------------------------
 */

#include <SoftwareSerial.h>

// ===========================================================================
// CONFIGURACION
// ===========================================================================

// --- Modo de respuesta ---------------------------------------------------
#define RESP_NINGUNA     0   // solo detecta y registra (empieza SIEMPRE por aqui)
#define RESP_ULTRASONIDO 1   // barrido 18-23 kHz, fuera del rango audible humano
#define RESP_ESTRIDENTE  2   // sirena disonante audible 1.5-4.5 kHz
#define RESP_MIXTA       3   // ultrasonido + estridente alternados
#define RESP_DFPLAYER    4   // reproduce pista del DFPlayer Mini

uint8_t modoRespuesta = RESP_NINGUNA;   // cambia aqui o por serie con el comando M

// --- Umbrales de deteccion ----------------------------------------------
// Cuantas veces por encima del ruido de fondo tiene que estar el pico.
// Sube este valor si hay falsos positivos, bajalo si no detecta.
float FACTOR_UMBRAL      = 4.5;
// Amplitud minima absoluta (cuentas ADC). Evita dispararse en silencio total.
const uint16_t AMP_MINIMA = 25;

const uint16_t DUR_MIN_MS = 80;    // un ladrido dura al menos esto
const uint16_t DUR_MAX_MS = 700;   // mas largo que esto ya no es un ladrido

// Banda de frecuencia estimada por cruces por cero (Hz)
const uint16_t FREQ_MIN_HZ = 200;
const uint16_t FREQ_MAX_HZ = 4500;

// --- Logica de rafaga ----------------------------------------------------
const uint8_t  LADRIDOS_PARA_DISPARAR = 3;      // ladridos necesarios...
const uint32_t VENTANA_RAFAGA_MS      = 8000UL; // ...dentro de esta ventana

// --- Limites de la respuesta (importante: no te pases) -------------------
const uint16_t DURACION_RESPUESTA_MS = 2500;    // cuanto suena cada respuesta
const uint32_t ENFRIAMIENTO_MS       = 20000UL; // pausa minima entre respuestas
const uint8_t  MAX_RESPUESTAS_HORA   = 12;      // tope duro por hora

// --- Pines ---------------------------------------------------------------
const uint8_t PIN_MIC      = A0;
const uint8_t PIN_TONO     = 9;
const uint8_t PIN_AMP_EN   = 8;
const uint8_t PIN_BOTON    = 2;
const uint8_t PIN_LED      = 13;
const uint8_t PIN_DF_RX    = 10;   // conectar al TX del DFPlayer
const uint8_t PIN_DF_TX    = 11;   // conectar al RX del DFPlayer (via 1k)

const uint8_t VOLUMEN_DFPLAYER = 25;  // 0-30
const uint8_t PISTA_DFPLAYER   = 1;   // 0001.mp3 en la raiz de la microSD

// ===========================================================================
// MUESTREO POR INTERRUPCION
// ===========================================================================

// fs = 16 MHz / preescalador 64 / 13 ciclos = 19231 Hz
const uint32_t FS_HZ    = 19231UL;
const uint16_t BLOQUE   = 256;                     // muestras por bloque
const uint16_t MS_BLOQUE = (1000UL * BLOQUE) / FS_HZ;  // ~13 ms

volatile uint32_t isrSumaAbs   = 0;
volatile uint16_t isrCruces    = 0;
volatile uint16_t isrMuestras  = 0;
volatile int32_t  isrDcAcum    = 512L << 8;   // continua estimada, formato Q8
volatile bool     isrSignoPrev = true;

volatile uint32_t blqSumaAbs = 0;
volatile uint16_t blqCruces  = 0;
volatile bool     blqListo   = false;

ISR(ADC_vect) {
  int16_t x = ADC;                                   // 0..1023

  // Continua adaptativa (filtro IIR de un polo) para centrar la senal
  isrDcAcum += (((int32_t)x << 8) - isrDcAcum) >> 8;
  int16_t centrada = x - (int16_t)(isrDcAcum >> 8);

  isrSumaAbs += (centrada < 0) ? -centrada : centrada;

  bool signo = (centrada >= 0);
  if (signo != isrSignoPrev) {
    isrCruces++;
    isrSignoPrev = signo;
  }

  if (++isrMuestras >= BLOQUE) {
    blqSumaAbs = isrSumaAbs;
    blqCruces  = isrCruces;
    blqListo   = true;
    isrSumaAbs = 0;
    isrCruces  = 0;
    isrMuestras = 0;
  }
}

void iniciarAdc(uint8_t canal) {
  ADMUX  = (1 << REFS0) | (canal & 0x07);            // referencia AVcc
  ADCSRB = 0;                                        // modo libre
  ADCSRA = (1 << ADEN)  |                            // ADC on
           (1 << ADSC)  |                            // primera conversion
           (1 << ADATE) |                            // auto-disparo
           (1 << ADIE)  |                            // interrupcion
           (1 << ADPS2) | (1 << ADPS1);              // preescalador 64
  DIDR0 |= (1 << (canal & 0x07));                    // desactiva E/S digital
  sei();
}

// ===========================================================================
// ESTADO
// ===========================================================================

SoftwareSerial dfSerial(PIN_DF_RX, PIN_DF_TX);

float    ruidoFondo   = 40.0;    // amplitud media del fondo, adaptativa
bool     enEvento     = false;
uint16_t bloquesEvento = 0;
uint32_t sumaCrucesEvento = 0;
uint16_t picoEvento   = 0;

uint32_t tsLadridos[LADRIDOS_PARA_DISPARAR];
uint8_t  idxLadrido   = 0;
uint16_t totalLadridos = 0;

uint32_t ultimaRespuesta = 0;
uint8_t  respuestasEnHora = 0;
uint32_t inicioHora      = 0;

bool silenciado = false;
bool botonPrev  = HIGH;
uint32_t tsBoton = 0;

// ===========================================================================
// DFPLAYER (protocolo minimo, sin libreria)
// ===========================================================================

void dfComando(uint8_t cmd, uint8_t p1, uint8_t p2) {
  uint16_t suma = 0xFFFF - (0xFF + 0x06 + cmd + 0x00 + p1 + p2) + 1;
  uint8_t trama[10] = {
    0x7E, 0xFF, 0x06, cmd, 0x00, p1, p2,
    (uint8_t)(suma >> 8), (uint8_t)(suma & 0xFF), 0xEF
  };
  dfSerial.write(trama, 10);
}

// ===========================================================================
// SONIDOS GENERADOS
// ===========================================================================

// Barrido ultrasonico 18-23 kHz. Por encima del limite auditivo de un adulto
// y dentro del rango canino (hasta ~45 kHz). El barrido, frente a un tono
// fijo, dificulta la habituacion del animal.
void sonidoUltrasonido(uint16_t ms) {
  uint32_t fin = millis() + ms;
  while (millis() < fin) {
    for (uint16_t f = 18000; f <= 23000 && millis() < fin; f += 250) {
      tone(PIN_TONO, f);
      delay(6);
    }
    for (uint16_t f = 23000; f >= 18250 && millis() < fin; f -= 250) {
      tone(PIN_TONO, f);
      delay(6);
    }
  }
  noTone(PIN_TONO);
}

// Sirena disonante en la banda donde el oido humano es mas sensible
// (2-4 kHz), con saltos de tritono y modulacion rapida. Maxima
// saliencia perceptiva por vatio emitido. AUDIBLE: usar con criterio.
void sonidoEstridente(uint16_t ms) {
  uint32_t fin = millis() + ms;
  const uint16_t base[] = {2100, 2970, 2300, 3250, 1800, 2545};  // pares en tritono
  uint8_t i = 0;
  while (millis() < fin) {
    uint16_t f = base[i % 6];
    // barrido rapido ascendente sobre cada nota -> efecto "sirena"
    for (uint16_t k = 0; k < 12 && millis() < fin; k++) {
      tone(PIN_TONO, f + k * 45);
      delay(8);
    }
    i++;
  }
  noTone(PIN_TONO);
}

void sonidoMixto(uint16_t ms) {
  uint32_t fin = millis() + ms;
  while (millis() < fin) {
    sonidoUltrasonido(400);
    if (millis() >= fin) break;
    sonidoEstridente(400);
  }
  noTone(PIN_TONO);
}

// ===========================================================================
// RESPUESTA
// ===========================================================================

void lanzarRespuesta() {
  ultimaRespuesta = millis();
  respuestasEnHora++;

  Serial.print(F("DISPARO,modo="));
  Serial.print(modoRespuesta);
  Serial.print(F(",n_hora="));
  Serial.println(respuestasEnHora);

  if (modoRespuesta == RESP_NINGUNA) return;

  digitalWrite(PIN_AMP_EN, HIGH);
  delay(30);                              // deja asentar el amplificador

  switch (modoRespuesta) {
    case RESP_ULTRASONIDO: sonidoUltrasonido(DURACION_RESPUESTA_MS); break;
    case RESP_ESTRIDENTE:  sonidoEstridente(DURACION_RESPUESTA_MS);  break;
    case RESP_MIXTA:       sonidoMixto(DURACION_RESPUESTA_MS);       break;
    case RESP_DFPLAYER:
      dfComando(0x03, 0x00, PISTA_DFPLAYER);   // reproducir pista N
      delay(DURACION_RESPUESTA_MS);
      dfComando(0x16, 0x00, 0x00);             // stop
      break;
  }

  digitalWrite(PIN_AMP_EN, LOW);

  // Tras responder, reinicia la deteccion de rafaga y da margen para que
  // el ruido de fondo se reajuste (el altavoz habra saturado el microfono).
  totalLadridos = 0;
  idxLadrido = 0;
  for (uint8_t i = 0; i < LADRIDOS_PARA_DISPARAR; i++) tsLadridos[i] = 0;
  ruidoFondo = max(ruidoFondo, 40.0);
  delay(200);
}

// ===========================================================================
// EVENTOS
// ===========================================================================

void registrarLadrido(uint16_t durMs, uint16_t freqHz, uint16_t pico) {
  uint32_t ahora = millis();

  Serial.print(F("LADRIDO,t="));   Serial.print(ahora);
  Serial.print(F(",dur="));        Serial.print(durMs);
  Serial.print(F(",f="));          Serial.print(freqHz);
  Serial.print(F(",pico="));       Serial.print(pico);
  Serial.print(F(",fondo="));      Serial.println((uint16_t)ruidoFondo);

  digitalWrite(PIN_LED, HIGH);

  tsLadridos[idxLadrido] = ahora;
  idxLadrido = (idxLadrido + 1) % LADRIDOS_PARA_DISPARAR;
  if (totalLadridos < 255) totalLadridos++;

  if (totalLadridos < LADRIDOS_PARA_DISPARAR) return;

  // El mas antiguo del anillo es el que ocupa la posicion que acabamos
  // de dejar libre: si esta dentro de la ventana, hay rafaga.
  uint32_t masAntiguo = tsLadridos[idxLadrido];
  if (masAntiguo == 0 || (ahora - masAntiguo) > VENTANA_RAFAGA_MS) return;

  Serial.print(F("RAFAGA,ladridos="));
  Serial.print(LADRIDOS_PARA_DISPARAR);
  Serial.print(F(",en_ms="));
  Serial.println(ahora - masAntiguo);

  if (silenciado) { Serial.println(F("INFO,silenciado")); return; }
  if (ultimaRespuesta && (ahora - ultimaRespuesta) < ENFRIAMIENTO_MS) {
    Serial.println(F("INFO,enfriando"));
    return;
  }
  if (respuestasEnHora >= MAX_RESPUESTAS_HORA) {
    Serial.println(F("INFO,tope_horario"));
    return;
  }

  lanzarRespuesta();
}

void procesarBloque(uint32_t suma, uint16_t cruces) {
  uint16_t amp = suma / BLOQUE;                 // amplitud media del bloque
  float umbral = ruidoFondo * FACTOR_UMBRAL;
  if (umbral < AMP_MINIMA) umbral = AMP_MINIMA;

  if (!enEvento) {
    if (amp > umbral) {
      enEvento = true;
      bloquesEvento = 1;
      sumaCrucesEvento = cruces;
      picoEvento = amp;
    } else {
      // Solo adaptamos el fondo fuera de evento, y despacio.
      ruidoFondo += (amp - ruidoFondo) * 0.02;
      if (ruidoFondo < 2.0) ruidoFondo = 2.0;
    }
    return;
  }

  // Dentro de un evento: histeresis al 60% del umbral para no cortarlo antes.
  if (amp > umbral * 0.6 && bloquesEvento < (DUR_MAX_MS / MS_BLOQUE) + 4) {
    bloquesEvento++;
    sumaCrucesEvento += cruces;
    if (amp > picoEvento) picoEvento = amp;
    return;
  }

  // Fin del evento: clasificar.
  enEvento = false;
  uint16_t durMs = bloquesEvento * MS_BLOQUE;

  // Frecuencia dominante estimada: cruces_por_bloque * fs / (2 * BLOQUE)
  uint16_t crucesMedios = sumaCrucesEvento / bloquesEvento;
  uint16_t freqHz = (uint32_t)crucesMedios * FS_HZ / (2UL * BLOQUE);

  bool duracionOk = (durMs >= DUR_MIN_MS && durMs <= DUR_MAX_MS);
  bool bandaOk    = (freqHz >= FREQ_MIN_HZ && freqHz <= FREQ_MAX_HZ);

  if (duracionOk && bandaOk) {
    registrarLadrido(durMs, freqHz, picoEvento);
  } else {
    Serial.print(F("DESCARTE,dur="));  Serial.print(durMs);
    Serial.print(F(",f="));            Serial.print(freqHz);
    Serial.print(F(",pico="));         Serial.println(picoEvento);
  }
}

// ===========================================================================
// COMANDOS POR SERIE
// ===========================================================================

void atenderSerie() {
  if (!Serial.available()) return;
  char c = Serial.read();
  switch (c) {
    case 'T': case 't':                       // probar la respuesta
      Serial.println(F("INFO,prueba"));
      lanzarRespuesta();
      break;
    case 'S': case 's':                       // silenciar / rearmar
      silenciado = !silenciado;
      Serial.print(F("INFO,silenciado=")); Serial.println(silenciado);
      break;
    case '+':
      FACTOR_UMBRAL -= 0.5;                   // menos factor = mas sensible
      if (FACTOR_UMBRAL < 1.5) FACTOR_UMBRAL = 1.5;
      Serial.print(F("INFO,factor=")); Serial.println(FACTOR_UMBRAL);
      break;
    case '-':
      FACTOR_UMBRAL += 0.5;
      if (FACTOR_UMBRAL > 20.0) FACTOR_UMBRAL = 20.0;
      Serial.print(F("INFO,factor=")); Serial.println(FACTOR_UMBRAL);
      break;
    case 'M': case 'm': {                     // cambiar modo: M0..M4
      while (!Serial.available()) { /* espera el digito */ }
      char d = Serial.read();
      if (d >= '0' && d <= '4') {
        modoRespuesta = d - '0';
        Serial.print(F("INFO,modo=")); Serial.println(modoRespuesta);
      }
      break;
    }
    case '?':
      Serial.println(F("INFO,cmds: T=probar S=silencio +/-=sensibilidad M0..M4=modo"));
      break;
  }
}

// ===========================================================================
// SETUP / LOOP
// ===========================================================================

void setup() {
  Serial.begin(115200);
  pinMode(PIN_AMP_EN, OUTPUT);  digitalWrite(PIN_AMP_EN, LOW);
  pinMode(PIN_LED,    OUTPUT);  digitalWrite(PIN_LED, LOW);
  pinMode(PIN_BOTON,  INPUT_PULLUP);
  pinMode(PIN_TONO,   OUTPUT);

  dfSerial.begin(9600);
  delay(500);
  dfComando(0x06, 0x00, VOLUMEN_DFPLAYER);    // volumen

  for (uint8_t i = 0; i < LADRIDOS_PARA_DISPARAR; i++) tsLadridos[i] = 0;

  iniciarAdc(0);   // A0

  inicioHora = millis();
  Serial.println(F("INFO,detector de ladridos listo. Envia ? para ayuda."));

  // Calibracion inicial del ruido de fondo: 2 segundos escuchando.
  Serial.println(F("INFO,calibrando 2s, silencio por favor"));
  uint32_t fin = millis() + 2000;
  uint32_t acum = 0; uint16_t n = 0;
  while (millis() < fin) {
    if (blqListo) {
      blqListo = false;
      acum += blqSumaAbs / BLOQUE;
      n++;
    }
  }
  if (n) ruidoFondo = (float)acum / n;
  if (ruidoFondo < 2.0) ruidoFondo = 2.0;
  Serial.print(F("INFO,ruido_fondo=")); Serial.println((uint16_t)ruidoFondo);
}

void loop() {
  atenderSerie();

  // Boton de silencio (antirrebotes simple)
  bool b = digitalRead(PIN_BOTON);
  if (botonPrev == HIGH && b == LOW && millis() - tsBoton > 250) {
    tsBoton = millis();
    silenciado = !silenciado;
    Serial.print(F("INFO,silenciado=")); Serial.println(silenciado);
  }
  botonPrev = b;

  // Reinicio del contador horario
  if (millis() - inicioHora >= 3600000UL) {
    inicioHora = millis();
    respuestasEnHora = 0;
    Serial.println(F("INFO,contador horario reiniciado"));
  }

  if (blqListo) {
    noInterrupts();
    uint32_t s = blqSumaAbs;
    uint16_t c = blqCruces;
    blqListo = false;
    interrupts();
    procesarBloque(s, c);
    digitalWrite(PIN_LED, enEvento ? HIGH : LOW);
  }
}

# Investigación de hardware — qué módulos comprar y por qué

Investigación de los componentes para fabricar el detector, con las alternativas
evaluadas y el criterio de cada decisión. Al final hay tres listas de compra
cerradas según presupuesto y objetivo.

**Aviso sobre los precios:** los rangos que doy son de orden de magnitud
(AliExpress / Amazon.es) basados en el mercado típico de estos módulos, **no son
precios verificados a día de hoy**. El único dato confirmado en esta
investigación es el MAX9814 oficial de Adafruit a 7,95 $. Verifica antes de
comprar.

---

## 1. Resumen ejecutivo

El sistema tiene cuatro bloques, y **solo uno es realmente difícil**:

| bloque | dificultad | por qué |
|---|---|---|
| Micrófono | fácil | cualquier módulo decente vale |
| Cerebro | fácil | ESP32, y se acabó la discusión |
| **Emisor** | **el problema** | un altavoz normal **no emite ultrasonidos**, y los ultrasonidos apenas se propagan |
| Alimentación y caja | fácil | pero es donde falla el 90% de los proyectos de exterior |

La conclusión más importante de toda la investigación: **el ultrasonido es muy
direccional y se atenúa rapidísimo**. Los emisores comerciales declaran de 5 a
15 metros con un cono de unos 110°, y cualquier pared, cristal o seto lo bloquea
casi por completo ([ToolsNova](https://toolsnova.com/best-ultrasonic-dog-repellers/),
[DogNotebook](https://www.dognotebook.com/best-ultrasonic-bark-control-devices/)).

Esto condiciona el montaje entero: **necesitas línea de visión directa** entre
el emisor y el punto donde está el animal, a menos de ~10 m. Sin eso no hay
vatios que valgan, y el valor del sistema pasa a estar en la parte de detección
y registro, no en la de emisión. Dimensiona el proyecto sabiéndolo antes de
comprar el emisor.

---

## 2. El micrófono

### Los tres candidatos reales

| | MAX4466 | MAX9814 | INMP441 |
|---|---|---|---|
| Tipo | electret + ampli analógico | electret + ampli analógico | MEMS digital I²S |
| Salida | analógica | analógica | I²S 24 bits |
| Ganancia | manual (potenciómetro) | **AGC automático** 40/50/60 dB | fija |
| Ruido/interferencias | sensible | sensible, mejor inmunidad | **inmune** (es digital) |
| Compatible Arduino Uno | sí | sí | no (el Uno no tiene I²S por hardware) |
| ¿Sirve para medir dB SPL reales? | con calibración | **no, el AGC lo impide** | **sí, directamente** |
| Precio orientativo | 2–3 € | 2–4 € (7,95 $ el de Adafruit) | 2–4 € |

### La decisión clave que nadie te cuenta

El MAX9814 es el que todo el mundo recomienda, y para **detectar** es
efectivamente el mejor: su AGC mantiene la señal en rango tanto si el perro
ladra cerca como lejos, y aguanta bien ambientes acústicos complicados
([comparativa AliExpress](https://www.aliexpress.com/s/wiki-ssr/article/max9814-vs-max4466)).

Pero ese mismo AGC **inutiliza la medición de nivel**: si la ganancia cambia
sola, un ladrido de 80 dB SPL y uno de 95 dB SPL pueden dar la misma lectura. Si
lo que quieres es una serie temporal cuantitativa y no solo una cuenta de
eventos, el AGC es un problema, no una ventaja.

El **INMP441** no tiene ese problema. Su hoja de características da una
sensibilidad de −26 dBFS a 94 dB SPL y 1 kHz, con punto de saturación acústica
en 120 dB SPL ([datasheet Farnell](https://www.farnell.com/datasheets/1824785.pdf)).
Con eso, el nivel real sale de una fórmula directa sobre las muestras:

```
dB SPL ≈ 120 + 20 · log10(muestra_pico / 2^23)
```

Es decir: pasas de anotar *"ladrido, +38 dB sobre el fondo"* —una medida
relativa, solo comparable consigo misma— a anotar *"ladrido, 87 dB SPL a 12 m"*,
que es una magnitud física con unidades. Además es digital, así que no le entra
el ruido eléctrico que sí le entra a un cable analógico de dos metros metido en
una caja junto a un amplificador.

> **Recomendación:** INMP441 con ESP32. Si vas con Arduino Uno (sin I²S por
> hardware), MAX9814. Si vas a montar los dos, compra los dos: valen 3 € cada uno.

**Detalle de integración ya resuelto en el código:** el MAX9814 no saca la señal
centrada en Vcc/2 sino unos **2 Vpp sobre una continua de 1,25 V**
([Adafruit](https://www.adafruit.com/product/1713)). El firmware estima la
continua con un filtro IIR adaptativo y se centra solo, así que da igual el
módulo que pongas — no tienes que tocar nada.

### Lo que NO comprar

El **KY-037 / KY-038** (esos módulos azules con potenciómetro y un LED que se
venden como "sensor de sonido"). Su salida digital es un simple comparador de
umbral: te dice "hay ruido / no hay ruido", sin duración ni frecuencia. Con eso
es imposible distinguir un ladrido de un portazo, y todo el filtro del proyecto
deja de funcionar. Su salida analógica sirve, pero es sorda y ruidosa comparada
con un MAX9814 que cuesta lo mismo.

---

## 3. El cerebro: Arduino Uno vs ESP32

| | Arduino Uno/Nano (ATmega328P) | ESP32 |
|---|---|---|
| CPU | 1 núcleo, 16 MHz | **2 núcleos, 240 MHz** |
| RAM | 2 KB | **520 KB** |
| ADC | 10 bits, muy lineal | 12 bits, **no lineal** (necesita calibración) |
| I²S por hardware | no | **sí, con DMA** |
| FFT en tiempo real | inviable | **sí**, 44,1 kHz con ventanas de 2048 |
| WiFi | no | **sí** |
| Precio | 3–5 € (clon Nano) | 4–8 € |

No hay debate. El ESP32 tiene 260 veces más RAM por el mismo dinero, y hacer FFT
en un ATmega328P choca con los límites de memoria y proceso enseguida
([JLCPCB](https://jlcpcb.com/blog/esp32-vs-arduino),
[ThinkRobotics](https://thinkrobotics.com/blogs/product-reviews-buying-guides/esp32-vs-arduino-uno-5-reasons-to-upgrade-for-iot-projects)).
Por eso el firmware de este repo usa envolvente y cruces por cero en vez de FFT:
es lo único que cabe en un Uno.

Con ESP32 además ganas tres cosas que aquí importan de verdad:

- **I²S con DMA**: el micrófono digital llena un buffer en memoria por su cuenta,
  sin que la CPU tenga que ir a buscar cada muestra. Deja el procesador libre
  para la FFT.
- **WiFi**: el registro se sube solo, y te puede mandar un aviso al móvil. Se
  acabó el "tengo que dejar el portátil encendido toda la noche".
- Existe ya un ecosistema entero de proyectos ESP32 + INMP441 + FFT del que
  copiar ([ESP32 Audio Analyzer](https://github.com/ElectroPrashant/ESP32-Audio-Analyzer-Loudness-and-Frequency-Detection),
  [tutorial FFT / detección de sonidos](https://iotassistant.io/esp32/smart-door-bell-noise-meter-using-fft-esp32/)),
  incluido clasificación de sonidos entrenada con Edge Impulse si algún día
  quieres distinguir *ese* perro de los otros tres del barrio.

> Ojo con el ADC del ESP32 si vas con micrófono **analógico**: es notoriamente no
> lineal. Es otra razón más para ir de INMP441, que se salta el ADC por completo.

---

## 4. El emisor: aquí está el problema de verdad

### Un altavoz normal no emite ultrasonidos

Esto hay que dejarlo claro antes de gastar un euro. Un altavoz de PC, uno de
móvil o un cono de 3" **no reproduce nada por encima de 18–20 kHz**. Puedes tener
el código perfecto generando 22 kHz y no salir absolutamente nada por el aire.
**Compruébalo siempre con una app de analizador de espectro en el móvil antes de
dar por bueno el montaje.**

### Opciones para el ultrasonido

**a) Tweeter piezoeléctrico tipo Motorola KSN1005A** — 5–12 €
Respuesta de 4 kHz a 27 kHz, es decir, entra de lleno en el ultrasonido
([Springfield Speaker](https://www.springfieldspeakerrepair.com/products/2ksn1005aft)).
Es la opción clásica y la que más se usa en los circuitos antiladridos caseros.
Ventaja añadida: al ser piezoeléctrico, se puede atacar casi directamente sin un
amplificador de potencia grande.

Sus pegas, que son reales: la respuesta en frecuencia está **llena de picos y
valles de resonancia**, y tiene distorsión alta, hasta el punto de que los
armónicos se baten entre sí y generan productos de intermodulación **en la banda
audible** ([diyAudio](https://diyaudio.com/forums/everything-else/96465-piezo-tweeter-dogs-13.html)).
Traducido: puede que emitiendo "solo ultrasonidos" acabes oyendo un siseo. Otra
razón para probarlo antes con el analizador de espectro.

**b) Transductor ultrasónico de banda estrecha (25 / 40 kHz)** — 3–8 €
Los típicos de los sensores de distancia. Emiten mucho SPL pero **solo en su
frecuencia de resonancia**, así que se acabó el barrido de frecuencia. Y el
barrido es justo lo que evita que el perro se acostumbre. Además, 40 kHz está ya
en el límite alto de la audición canina y se propaga fatal. No los recomiendo.

**c) Canibalizar un repelente ultrasónico comercial** — 10–20 €
Compras uno barato y le cableas su emisor y su etapa de salida, ya diseñada y
adaptada. Es la vía rápida y probablemente la más sensata si no quieres pelearte
con la electrónica analógica.

### El detalle que te va a quemar un amplificador

Un tweeter piezoeléctrico **no es una carga resistiva, es un condensador**. Su
impedancia se desploma según sube la frecuencia, justo donde tú quieres
trabajar. Los amplificadores clase D, combinados con la resonancia de su filtro
de salida, entran en sobrecorriente e incluso oscilan con este tipo de carga:
los clase AB, D, G y H se diseñaron asumiendo cargas resistivas y **no son aptos
para cargas muy capacitivas** ([diyAudio](https://www.diyaudio.com/community/threads/driving-capacitor-with-class-d.194259/),
[Parts Express](https://techtalk.parts-express.com/forum/tech-talk-forum/25783-amps-pro-mi-drivers-piezos-and-capacitive-loads)).

**Solución, y no es opcional: una resistencia de potencia en serie con el
tweeter**, de unos 10 Ω y 2 W (el rango que se cita va de 2 a 10 Ω; para
ultrasonidos, tirando a alto). Aísla al amplificador de la capacidad, amortigua
la resonancia y evita que oscile. Cuesta 20 céntimos y te ahorra el
amplificador.

### La frecuencia que elegir

Aquí hay una tensión que hay que decidir a conciencia:

| frecuencia | ¿lo oyen las personas? | ¿se propaga? | ¿molesta al perro? |
|---|---|---|---|
| 17–19 kHz | **los jóvenes sí** | **bien** | mucho |
| 20–22 kHz | prácticamente nadie | regular | sí |
| 23–25 kHz | nadie | **mal** | menos |

Los repelentes comerciales trabajan entre 20 y 25 kHz, y los perros llegan a
unos 45 kHz frente a los 20 kHz humanos ([SoundCy](https://soundcy.com/article/what-sound-frequency-repels-dogs)).
Pero en los foros de diseño el consenso práctico es que la resonancia útil está
entre 16 y 22 kHz, y que **17–19 kHz se propaga bastante mejor** que empujar por
encima de 20 kHz ([Electro-Tech-Online](https://www.electro-tech-online.com/threads/dog-stopping-finding-a-piezo-buzzer-transducer.28029/)).

El firmware de este repo barre **18–23 kHz**, que es un compromiso razonable.
Ajústalo según el caso:

- **Si puede haber adolescentes o niños en el alcance**, sube el extremo inferior
  a 20 kHz. La pérdida auditiva por edad es real: una persona de 15 años oye
  perfectamente los 18 kHz que un adulto de 40 ya no percibe. "Inaudible" no es
  una propiedad del sonido, es una propiedad del oyente.
- **Si la distancia es grande** y a 20 kHz no llega, baja a 17 kHz asumiendo que
  parte de la gente joven lo va a oír.

---

## 5. Amplificación y reproducción

| módulo | qué es | precio | veredicto |
|---|---|---|---|
| **MAX98357A** | DAC + ampli clase D 3,2 W por I²S | 2–4 € | **el mejor para ESP32.** Acepta muestreo hasta 96 kHz, o sea que puede representar hasta 48 kHz — te llega de sobra para el ultrasonido. Conmuta a 330 kHz ([datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/max98357a-max98357b.pdf)) |
| **PAM8403** | ampli clase D 3 W estéreo, entrada analógica | 1–2 € | vale, y es **sin filtro de salida** ([Diodes](https://www.diodes.com/assets/Datasheets/products_inactive_data/PAM8403.pdf)), así que deja pasar el ultrasonido en vez de recortarlo. Barato y suficiente si vas con Arduino |
| **DFPlayer Mini** | reproductor MP3 con microSD y ampli | 1,5–3 € | cómodo: metes el WAV/MP3 en la tarjeta y lo disparas por serie. Avisa cuando termina la pista, cosa que sus clones no hacen |
| DY-SV17F / DY-SV5W | alternativas al DFPlayer | 2–4 € | el DY-SV17F trae 4 MB de flash interna (el doble que un JQ6500) y ampli de 5 W integrado, pero el DY-SV5W **no avisa por serie al terminar la pista**, solo tiene un pin BUSY ([Arduino Forum](https://forum.arduino.cc/t/how-to-use-dy-sv5w-mp3-player/1218247)) |
| JQ6500 | alternativa barata | 2–3 € | 2 MB de flash, versión -28P con ranura microSD ([gogo:tronics](https://sparks.gogo.co.nz/jq6500/index.html)) |

**Aviso sobre el DFPlayer y el ultrasonido:** un módulo MP3 decodifica a 44,1 kHz
como mucho, o sea Nyquist en 22,05 kHz. Un WAV con contenido a 23 kHz **no le
cabe**. Si vas por la vía DFPlayer, genera los sonidos con
`generar_sonidos.py` limitando el barrido a 21 kHz máximo, o mejor: usa el
DFPlayer solo para el modo *estridente* audible y genera el ultrasonido
directamente con `tone()` desde el microcontrolador, que es lo que hace ya el
firmware.

**Cómo lo genera el firmware actual:** `tone()` en el pin D9 del Uno usa el
Timer1, que es de 16 bits, así que llega a 23 kHz con precisión buena. Está
elegido a propósito — en los pines 3 y 11 usaría el Timer2, de 8 bits, y a esas
frecuencias el paso de cuantización se comería el barrido.

---

## 6. Alimentación

Esto se subestima siempre y es la causa número uno de falsos positivos: **un
amplificador dando picos y un micrófono compartiendo la misma alimentación =
ruido eléctrico que el detector confunde con sonido.**

| pieza | precio | notas |
|---|---|---|
| Fuente 5 V / 2 A con conector jack | 5–8 € | **no** alimentes esto del USB del portátil |
| Condensador electrolítico 1000 µF | 0,50 € | en la entrada de alimentación del amplificador |
| Condensador cerámico 100 nF | 0,10 € | uno pegado a cada pin de alimentación de cada módulo |
| Regulador AMS1117 3,3 V (si hace falta) | 1 € | el ESP32 es de 3,3 V; el MAX9814 tolera 3,3 V pero baja la señal |

Alimenta el micrófono desde el pin regulado de 3,3 V de la placa, **no** desde la
misma línea de 5 V que el amplificador. Y separa físicamente el cable del
micrófono del cable del altavoz dentro de la caja.

---

## 7. Caja e intemperie

Si va fuera (balcón, terraza, jardín), esto no es opcional:

| pieza | precio | notas |
|---|---|---|
| Caja estanca IP65 ABS | 8–15 € | Leroy Merlin, Famatel, IDE Electric ([IP65-IP67](https://ide.es/eng/products/junction-boxes-and-mechanisms/ip65-ip67-junction-boxes)) |
| Prensaestopas M12 | 1–2 € | para que el cable entre sin romper la estanqueidad |
| Membrana de venteo Gore-Tex | 2–5 € | **importante**: iguala presión y deja salir humedad sin dejar entrar agua. Sin esto se condensa dentro y se te oxida todo en un invierno |
| Rejilla o malla metálica fina | 1–2 € | delante del micrófono, contra insectos |
| Espuma antiviento | 1–3 € | el viento sobre un micrófono desnudo genera ruido de baja frecuencia constante que dispara falsos positivos |

Las cajas IP65 estándar **no traen ni membrana de venteo ni rejilla acústica**;
hay que añadirlas. Un truco que funciona: taladra el orificio del micrófono en la
**cara inferior** de la caja, así el agua no entra por gravedad, y cúbrelo por
dentro con la membrana.

---

## 8. Listas de compra cerradas

### A — Mínima, "a ver si esto funciona" (~20 €)

Para validar el concepto en una tarde, sin caja ni exterior.

| pieza | € |
|---|---|
| Arduino Nano (clon) | 4 |
| MAX9814 | 3 |
| Tweeter piezoeléctrico | 8 |
| Resistencia 10 Ω 2 W, cables, protoboard | 3 |
| **Total** | **~18 €** |

Con esto ya corre el firmware de `firmware/detector_ladridos/`. Sin registro
calibrado y sin exterior, pero te dice en una noche si el sistema detecta al
perro o no. **Empieza por aquí.**

### B — Recomendada (~45 €)

La que yo montaría. ESP32 con micrófono digital: detección buena, registro con
dB SPL reales, WiFi, y apto para exterior.

| pieza | € |
|---|---|
| ESP32 DevKit V1 | 6 |
| INMP441 (I²S) | 3 |
| MAX98357A (I²S) | 3 |
| Tweeter piezoeléctrico KSN1005A o similar | 9 |
| Resistencia 10 Ω 2 W | 0,5 |
| Fuente 5 V / 2 A | 7 |
| Caja IP65 + prensaestopas + membrana | 14 |
| Rejilla, espuma antiviento, condensadores, cable | 5 |
| **Total** | **~47 €** |

### C — Completa, con respuesta audible además de ultrasónica (~70 €)

La B, más la capacidad de reproducir sonidos audibles arbitrarios.

| pieza | € |
|---|---|
| Todo lo de la lista B | 47 |
| DFPlayer Mini + microSD 8 GB | 8 |
| PAM8403 | 2 |
| Altavoz de banda ancha 4 Ω 5 W | 8 |
| Pulsador de silencio + LED indicador | 2 |
| **Total** | **~67 €** |

### Y la alternativa honesta

Un **disuasor ultrasónico antiladrido comercial** cuesta 25–40 € y funciona nada
más sacarlo de la caja. Si el único objetivo es la respuesta automática, sale
más barato que la lista B y no hay que soldar nada.

Lo que **no** te da, y es la razón entera de montar esto: el registro con marca
de tiempo, el umbral y la clasificación ajustables al caso concreto, el control
de franja horaria y de tasa máxima, y unos datos exportables sobre los que
después puedes hacer análisis o entrenar un clasificador. Si lo que te interesa
es medir y entender el patrón acústico, el emisor comercial no sirve de nada.

---

## 9. Plan de montaje y validación

Por orden, sin saltarse pasos:

1. **Micrófono + placa en la mesa.** Comprueba en el monitor serie que las
   lecturas se mueven al dar una palmada. Sin salida de sonido conectada todavía.
2. **Calibra** (`python3 escucha.py --calibrar` o el arranque del firmware) con
   el ruido ambiente de verdad, no en silencio.
3. **Una noche entera en modo `--solo-registrar`.** Sin emitir nada. Mira el
   informe al día siguiente y ajusta el umbral hasta que los ladridos que
   recuerdas cuadren con los registrados.
4. **Prueba el emisor por separado**, con una app de analizador de espectro en el
   móvil. Confirma que sale energía donde tú crees. Este paso se salta todo el
   mundo y es donde falla el 90% de los montajes ultrasónicos.
5. **Une las dos mitades**, con la respuesta al volumen más bajo que funcione.
6. **Monta en la caja** solo cuando funcione en la mesa.

---

## 10. Limitaciones del montaje y uso responsable

### Esto no es un sonómetro homologado

Aunque con un INMP441 se puedan calcular dB SPL, el montaje **no está calibrado
ni homologado**. La sensibilidad declarada del INMP441 es ±3 dB, a lo que hay
que sumar la respuesta de la caja, el orificio del micrófono y la falta de
ponderación A. Sirve para comparaciones relativas, para caracterizar un patrón
y para decidir dónde y cuándo medir en serio; **no sustituye a un equipo
homologado con certificado de calibración** si el dato tiene que ser oponible a
terceros.

Si quieres acercarte, calibra contra una referencia conocida (un sonómetro
prestado, o incluso una app de móvil calibrada) y añade el offset como constante.

### Emisión

- **Nivel acústico.** El montaje puede superar los 100 dB SPL a un metro. No te
  sitúes cerca del emisor mientras dispara. El ultrasonido es igual de lesivo
  para el oído por el hecho de no percibirse: no hay reflejo de retirada.
- **Dirección.** Al ser muy directivo, el ultrasonido se puede apuntar con
  precisión, y eso es también una responsabilidad: cae sobre lo que apuntes.
- **Otros animales.** El cono de emisión alcanza a gatos, roedores y a cualquier
  otro perro que esté dentro, incluidos los propios.
- **Normativa.** Emitir ruido audible hacia espacios ajenos está regulado en
  prácticamente cualquier jurisdicción, normalmente por ordenanza local con
  límites de nivel y franja horaria. Un emisor automatizado además registra su
  propia actividad. Infórmate de la normativa aplicable antes de usar los modos
  audibles.
- **Bienestar animal.** Un estímulo aversivo aplicado a un animal que ladra por
  ansiedad de separación agrava el problema en vez de resolverlo. Si el patrón
  registrado apunta a eso (ladrido sostenido que empieza al quedarse solo), la
  respuesta correcta es la conductual, no la acústica.

Por estas razones el firmware arranca en `RESP_NINGUNA`, el modo por defecto del
script es el ultrasónico, y existen `--solo-registrar`, `--horario` y
`--max-hora`.

---

## Fuentes

**Micrófonos**
- [MAX4466 vs MAX9814 — comparativa](https://www.aliexpress.com/s/wiki-ssr/article/max9814-vs-max4466)
- [Guía completa del INMP441 I2S](https://easyelecmodule.com/a-complete-guide-to-the-inmp441-i2s-microphone/)
- [INMP441 datasheet (Farnell)](https://www.farnell.com/datasheets/1824785.pdf)
- [MAX9814 — Adafruit, especificaciones y precio](https://www.adafruit.com/product/1713)
- [ESP32 Audio Input: MAX4466, MAX9814, SPH0645, INMP441 — atomic14](https://www.atomic14.com/2020/09/12/esp32-audio-input)

**Microcontrolador**
- [ESP32 vs Arduino (JLCPCB, 2026)](https://jlcpcb.com/blog/esp32-vs-arduino)
- [ESP32 vs Arduino Uno — ThinkRobotics](https://thinkrobotics.com/blogs/product-reviews-buying-guides/esp32-vs-arduino-uno-5-reasons-to-upgrade-for-iot-projects)
- [ESP32 Audio Analyzer — FFT y detección de frecuencia](https://github.com/ElectroPrashant/ESP32-Audio-Analyzer-Loudness-and-Frequency-Detection)
- [FFT en ESP32 para detectar sonidos concretos](https://iotassistant.io/esp32/smart-door-bell-noise-meter-using-fft-esp32/)

**Emisor y ultrasonidos**
- [Motorola KSN1005A — respuesta 4–27 kHz](https://www.springfieldspeakerrepair.com/products/2ksn1005aft)
- [Elección de transductor para disuasión canina — Electro-Tech-Online](https://www.electro-tech-online.com/threads/dog-stopping-finding-a-piezo-buzzer-transducer.28029/)
- [Limitaciones de los tweeters piezo — diyAudio](https://diyaudio.com/forums/everything-else/96465-piezo-tweeter-dogs-13.html)
- [Circuito antiladridos por alta frecuencia](https://www.homemade-circuits.com/dog-barking-preventer-circuit/)
- [Frecuencias que disuaden a los perros — SoundCy](https://soundcy.com/article/what-sound-frequency-repels-dogs)
- [Alcance real de los repelentes ultrasónicos](https://toolsnova.com/best-ultrasonic-dog-repellers/)

**Amplificación**
- [PAM8403 datasheet — arquitectura sin filtro](https://www.diodes.com/assets/Datasheets/products_inactive_data/PAM8403.pdf)
- [MAX98357A/B datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/max98357a-max98357b.pdf)
- [Cargas capacitivas y clase D — diyAudio](https://www.diyaudio.com/community/threads/driving-capacitor-with-class-d.194259/)
- [Piezos y cargas capacitivas — Parts Express](https://techtalk.parts-express.com/forum/tech-talk-forum/25783-amps-pro-mi-drivers-piezos-and-capacitive-loads)
- [Guía de módulos MP3 para Arduino — DFRobot](https://www.dfrobot.com/blog-1568.html)
- [DY-SV5W: sin aviso por serie al terminar pista](https://forum.arduino.cc/t/how-to-use-dy-sv5w-mp3-player/1218247)
- [JQ6500 — gogo:tronics](https://sparks.gogo.co.nz/jq6500/index.html)

**Caja**
- [Cajas de conexión IP65/IP67 — IDE Electric](https://ide.es/eng/products/junction-boxes-and-mechanisms/ip65-ip67-junction-boxes)
- [Cajas estancas IP55/IP65 — Famatel](https://famatel.com/en/productos/cajas-estancas-ip55-ip65/)

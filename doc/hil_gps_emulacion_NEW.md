# Banco de pruebas Hardware-in-the-Loop (HIL): emulación del radar US-D1 y del GPS-PPK ZED-F9P

## 1. Requisitos para la emulación del comportamiento del GPS

### 1.1 Mensajes UBX necesarios para un flujo de trabajo PPK

El cálculo de posición de precisión centimétrica mediante PPK (*Post-Processed Kinematic*) no se basa en la solución de navegación en tiempo real del receptor, sino en las **observables crudas** de fase de portadora, pseudodistancia y Doppler, que un software de post-proceso ([RTKLIB](https://www.rtklib.com/)) combina con los datos de una estación base o servicio de corrección. De ello se derivan tres mensajes UBX de interés, con roles distintos:

| Mensaje | Rol | Localización en fuente primaria |
|---|---|---|
| `UBX-RXM-RAWX` | **Imprescindible.** Contiene las observables crudas por satélite (pseudorange, fase de portadora, Doppler) que constituyen la materia prima del cálculo PPK. | [1], apartado 3.17.6 "UBX-RXM-RAWX (0x02 0x15)", p. 198 |
| `UBX-RXM-SFRBX` | **Igualmente imprescindible, no meramente recomendable.** Contiene las efemérides transmitidas (posición orbital) que RTKLIB necesita para calcular la posición de cada satélite en el instante de cada medida. | [1], apartado 3.17.9 "UBX-RXM-SFRBX (0x02 0x13)", p. 201 |
| `UBX-NAV-PVT` | **Recomendable, no estrictamente obligatorio para el cálculo PPK en sí.** Aporta una solución de posición en tiempo real de menor precisión, útil como verificación en campo, y el flag `carrSoln` (calidad de fix RTK) que ni `RAWX` ni `SFRBX` proporcionan. | [1], apartado 3.15.13 "UBX-NAV-PVT (0x01 0x07)", p. 151 |

#### Por qué `RAWX` no es autosuficiente pese a contener más detalle que `PVT`

Es tentador asumir que, al ser el mensaje con más campos y mayor resolución (fase de portadora, desviaciones típicas, calidad de señal), `RAWX` debería bastar por sí solo. No es así, y la razón es conceptual, no de cantidad de datos: los campos de `RAWX` (`prMes`, `cpMes`, `doMes`) son **medidas de distancia y velocidad relativa a un satélite identificado por `gnssId`/`svId`/`sigId`**, pero en ningún campo de `RAWX` se indica **dónde estaba ese satélite en el espacio** en el instante de la medida. Sin esa posición orbital, una pseudodistancia es, matemáticamente, la distancia a un punto de coordenadas desconocidas — inútil para triangular una posición propia.

`UBX-RXM-SFRBX` transporta exactamente esa pieza que falta: su campo `dwrd` contiene las palabras crudas de la subtrama de navegación que el propio satélite retransmite continuamente, de las que RTKLIB extrae (tras decodificarlas según el formato de cada constelación) los parámetros orbitales — la efeméride. No es casualidad que `RAWX` y `SFRBX` compartan los campos identificadores `gnssId`, `svId`, `sigId` y `freqId`: son la clave para correlacionar "medí esta distancia a este satélite" (`RAWX`) con "y aquí está la posición de ese mismo satélite en ese instante" (`SFRBX` decodificado). Sin ambas piezas correladas para cada satélite, el post-proceso PPK no puede completarse — de ahí que `SFRBX` se clasifique aquí como igualmente imprescindible, no como un complemento opcional.

Una alternativa parcial existe: si la estación de referencia empleada en el post-proceso aporta su propio fichero de navegación (efemérides) para el mismo periodo, `SFRBX` en el propio rover pasa de ser estrictamente necesario a ser una redundancia de seguridad que hace el dataset autocontenido y no dependiente de la disponibilidad de esa fuente externa — pero dado que no puede garantizarse esa disponibilidad en todo momento, se mantiene como requisito de diseño en este proyecto.

> **Corrección respecto a la versión anterior de este documento:** el diseño original solo contemplaba `NAV-PVT` y `RAWX`. Se añade `RXM-SFRBX` tras revisión del propio estudiante, que detectó la ausencia de una fuente de efemérides en el diseño de logging.

### 1.2 Estado de configuración de fábrica

El ZED-F9P, en su configuración de fábrica, emite únicamente mensajes NMEA estándar sobre UART1 a 38400 baudios; ni `UBX-NAV-PVT` ni `UBX-RXM-RAWX` están activados por defecto ([2], apartado 3.1.3 "Default interface settings": *"UART1 output 38400 Baud, 8 bits, no parity bit, 1 stop bit"*, y apartado 3.1.2 "Default GNSS configuration" para el resto del comportamiento de arranque). Este comportamiento debe replicarse fielmente en el emulador HIL, de forma que el firmware de la Teensy se vea obligado a ejercitar su secuencia completa de configuración, en lugar de asumir un receptor ya preparado —una asunción que no sería válida frente al hardware real.

### 1.3 Parámetros de configuración requeridos

La activación de los mensajes necesarios y el ajuste del baud rate se realizan mediante mensajes `UBX-CFG-VALSET`, dirigidos a las siguientes claves de configuración ([1], apartado "Configuration Reference", dentro de la Interfaz de Configuración):

| Configuración | Key ID | Valor | Fuente |
|---|---|---|---|
| Activar `NAV-PVT` en UART1 (cada época) | `0x20910007` | `0x01` | [1], apartado 6.9.11 "CFG-MSGOUT", p. 270 |
| Activar `RXM-RAWX` en UART1 (cada época) | `0x209102A5` | `0x01` | [1], apartado "Configuration defaults", p. 315 |
| Activar `RXM-SFRBX` en UART1 (cada época) | `0x20910232` | `0x01` | [1], apartado "Configuration defaults", p. 316 |
| Baud rate de UART1 | `0x40520001` | `230400` | [1], apartado 6.9.31 "CFG-UART1", p. 292 |

> **Corrección respecto a la versión anterior de este documento:** las claves de `RAWX` y de baud rate estaban citadas erróneamente como pertenecientes al apartado descriptivo 6.9.11; solo `NAV-PVT` tiene entrada narrativa propia en ese apartado (p. 270). `RAWX` y `SFRBX` únicamente aparecen en la tabla compacta "Configuration defaults" (páginas 315 y 316 respectivamente), sin descripción textual individual.

El incremento del baud rate por encima del valor de fábrica se justifica en dos niveles distintos, que conviene distinguir con precisión:

- **Principio general documentado por u-blox** ([2], apartado 3.8.1 "UART", p. 48): si el volumen de datos configurado excede el ancho de banda del puerto a un baud rate dado, el búfer se llena y los mensajes nuevos se descartan; se recomienda seleccionar el baud rate y el número de mensajes activados de forma que el número de bytes esperado se transmita en menos de un segundo. Esta es la justificación conceptual, pero **no especifica una cifra concreta** de baud rate para el caso de activar `RAWX`.

#### Verificación cuantitativa del margen de baud rate

Para confirmar que 230400 baudios es suficiente, se ha determinado un valor de
peor caso para `numMeas` (número de señales simultáneas en `UBX-RXM-RAWX`)
combinando tres fuentes independientes:

1. **Verificación empírica**: sobre un fichero de datos crudos multi-constelación
   de referencia [8] (4521 tramas `RXM-RAWX` analizadas), el máximo observado
   fue numMeas = 66 (trama de 2136 bytes, coincidente exactamente con la
   fórmula estructural del apartado 1.1).
2. **Derivación analítica**: la literatura sobre disponibilidad GNSS reporta
   entre 19.7 y 35.0 satélites simultáneamente visibles combinando las cuatro
   constelaciones principales [9], y fuentes de referencia de la industria
   sitúan el máximo práctico en hasta 30-40 satélites simultáneos bajo cielo
   despejado [10]. Distribuyendo esa cifra proporcionalmente entre GPS,
   GLONASS, Galileo y BeiDou, y aplicando el número de señales por satélite
   que soporta el ZED-F9P-15B en cada banda (Tabla 6, [7]), se obtiene un
   rango de 72 a 90 señales simultáneas.

Se adopta **N = 90** como cota de diseño conservadora, coherente con las tres
fuentes. La longitud de trama resultante es:

longitud_total = 8 (framing) + 16 (payload fijo) + 32 × 90 = 2904 bytes

**Ancho de banda requerido**, a 4 Hz de tasa de actualización y considerando
10 bits por byte en formato UART 8N1:

baud_mínimo = 2904 bytes × 10 bits/byte × 4 Hz = 116 160 baudios

El baud rate configurado (230 400 baudios) supera este requisito con un
margen de seguridad de ×1.98, confirmando que la elección es suficiente
incluso bajo el escenario de mayor carga técnicamente plausible para este
receptor y esta configuración de constelaciones. Esta cifra coincide además
con el precedente práctico de un proyecto de registro RAWX de terceros para
el mismo receptor, que emplea igualmente 230400 baudios en producción [6].

### 1.4 Persistencia de configuración: capas disponibles y decisión de diseño

La configuración del receptor se organiza en cuatro capas apilables por prioridad
([1], apartado 6.3 "Configuration layers", p. 244): **RAM** (volátil, la
configuración activa en cada instante), **BBR** (*Battery-Backed RAM*, requiere
pila de respaldo en `V_BCKP`), **Flash** (persistente) y **Default** (valores de
fábrica codificados en firmware más memoria OTP de personalización en
producción). Las tres primeras son modificables en tiempo de ejecución mediante
`CFG-VALSET`; **Default no lo es bajo ninguna circunstancia** —ni siquiera a
través de u-center—, por lo que cualquier configuración guardada mediante
software de u-blox se escribe siempre en BBR y/o Flash, nunca en esta capa.

Respecto a la disponibilidad de la capa Flash: el propio Interface Description
la condiciona a "que se use flash externa" [1], una salvedad razonable dado que
el documento es genérico para toda la plataforma F9 y no todos sus productos
incluyen flash integrada. El diagrama de bloques específico del ZED-F9P-15B [7]
sitúa un bloque de memoria flash dentro del propio módulo, lo que sugiere que en
este producto concreto sí está presente —aunque, con la información disponible
hasta ahora, no puede descartarse por completo cierta ambigüedad terminológica
entre "externa al chip" y "externa al módulo". Sobre la capa BBR, sigue sin
poder confirmarse si el H-RTK ZED-F9P Ultralight incluye pila de respaldo.

**Decisión de diseño**: dado que el firmware verifica el estado de configuración
del receptor en cada arranque mediante `UBX-CFG-VALGET` antes de decidir si
reconfigurar (apartado 3.3), la persistencia entre vuelos deja de ser una
dependencia crítica del sistema: si la configuración no sobrevivió al ciclo de
apagado/encendido (por ausencia de Flash, de BBR, o de ambas), el propio
mecanismo de verificación lo detecta y la restablece con un coste marginal
despreciable. En consecuencia, cuando es necesario reconfigurar, el firmware
escribe únicamente en la capa **RAM** (bitmask `layers = 0x01`), sin necesidad
de dirigirse también a Flash: esto evita depender de una capa cuya
disponibilidad no está completamente esclarecida, y elimina cualquier
preocupación sobre ciclos de escritura en memoria flash a lo largo de la vida
útil del proyecto.

#### 1.4.1 Actualización de firmware y limitación de recuperación

La actualización de firmware del ZED-F9P se realiza mediante u-center (`Tools -> Firmware Update`), conectando el módulo por USB o, en variantes solo-UART como la Ultralight, mediante un adaptador USB-UART, cargando una imagen `.bin` descargada del sitio de u-blox [2].

El pin `SAFEBOOT_N`, que permite forzar un modo de arranque seguro para recuperar el dispositivo si una actualización de firmware queda incompleta, **no está expuesto en el conector de 8 pines** de la unidad Ultralight (ausente de la lista VCC/RX1/TX1/SCL/SDA/RX2/TX2/GND verificada empíricamente). Esto implica que una actualización de firmware fallida podría dejar el módulo inoperativo sin posibilidad de recuperación sin intervención física de la placa. Se recomienda extremar la cautela antes de actualizar el firmware de esta unidad concreta, idealmente validando el procedimiento primero sobre una unidad de repuesto si estuviera disponible.

### 1.5 Ausencia de señal PPS y su implicación

El conector JST GH-1.25 de 8 pines del H-RTK ZED-F9P Ultralight (VCC, RX1, TX1, SCL, SDA, RX2, TX2, GND) [4] no expone la señal TIMEPULSE (PPS) del chip ZED-F9P, a diferencia de otras variantes de la familia H-RTK que sí incluyen esta señal en un conector UART2 independiente [5]. En consecuencia, la sincronización entre el reloj interno de la Teensy 4.1 y el tiempo GPS absoluto no puede basarse en la disciplina de reloj por flanco de PPS, y se resuelve mediante una **regresión lineal en post-proceso** entre el timestamp del reloj de la Teensy y los campos `iTOW`/`rcvTow` (tiempo GPS de semana) contenidos en los propios mensajes UBX (ver apartado 3.6).

## 2. Arquitectura del emulador GPS y validez de la emulación

### 2.1 Arquitectura de doble hilo

El script `emulador_gps.py`, ejecutado en la Raspberry Pi 4, implementa dos hilos de ejecución concurrentes sobre el mismo puerto serie:

- **Hilo de emisión (bucle principal):** genera y transmite periódicamente los mensajes `UBX-NAV-PVT` y `UBX-RXM-RAWX`, condicionado al estado de configuración activo en cada momento.
- **Hilo de escucha:** procesa de forma continua los bytes entrantes procedentes de la Teensy, buscando tramas `UBX-CFG-VALSET`.

Esta arquitectura es necesaria porque el receptor real atiende comandos de configuración y emite datos de navegación de forma concurrente, no secuencial; un emulador de un único hilo no podría replicar ese comportamiento sin introducir bloqueos artificiales. El acceso al estado de configuración compartido entre ambos hilos se protege mediante un `threading.Lock`.

### 2.2 Protocolo de negociación de configuración

El emulador arranca en el mismo estado de fábrica descrito en el apartado 1.2 (NMEA activo, UBX inactivo, 38400 baudios). Al recibir una trama `UBX-CFG-VALSET` con checksum válido, el hilo de escucha actualiza su estado interno (activación de mensajes, cambio de baud rate) y responde con `UBX-ACK-ACK`; si el checksum no es válido, responde con `UBX-ACK-NAK`. Este comportamiento replica fielmente el mecanismo de confirmación del protocolo UBX real ([1], apartado 3.9 "UBX-ACK (0x05)" y 3.9.1 "UBX-ACK-ACK (0x05 0x01)", p. 63), permitiendo validar contra el emulador la misma lógica de espera de confirmación que el firmware deberá implementar frente al receptor físico.

Adicionalmente, el emulador reconoce tramas `UBX-CFG-VALGET` (Class `0x06`, ID `0x8B`), devolviendo el valor actual de las claves solicitadas con el mismo formato que emplearía el receptor real ([1], apartado 3.10.24, p. 97), y respondiendo con `UBX-ACK-NAK` si se solicita una clave fuera del conjunto que el emulador conoce. Esto permite validar en banco la estrategia de "verificar antes de configurar" descrita en el apartado 3.3, sin necesidad de forzar siempre el camino de reconfiguración completa. El emulador no modela capas de persistencia diferenciadas (RAM/BBR/Flash) como valores independientes; su estado interno único se trata, a efectos de `VALGET`, como equivalente a la capa RAM.

### 2.3 Gestión del cambio de baud rate

Al procesar un cambio de baud rate, el emulador envía primero el `ACK-ACK` **al baud rate anterior**, y solo después de un breve margen conmuta su propia velocidad de puerto. Este orden es intencional: si la conmutación ocurriera antes de que el `ACK` hubiera salido físicamente por el cable, el host (la Teensy) no podría leer dicha confirmación, al estar ya escuchando a la nueva velocidad mientras la respuesta aún viaja a la antigua.

### 2.4 Simulación de interrupciones controladas (propuesta de trabajo futuro, no implementada)

Se ha diseñado, aunque **no está implementado en la versión actual de `emulador_gps.py`**, un mecanismo opcional para simular interrupciones controladas del servicio mediante parámetros adicionales (`--simular_corte_en`, `--duracion_corte`, `--tipo_corte`):

- **Corte de comunicación:** el emulador dejaría de transmitir durante el intervalo indicado, pero conservaría su estado de configuración interno, replicando una interrupción física del cableado sin pérdida de alimentación en el receptor.
- **Corte de alimentación:** además de interrumpir la transmisión, el emulador resetearía su estado de configuración a los valores de fábrica al finalizar el corte, replicando un reinicio real del receptor que exige una renegociación completa.

El propósito de esta funcionalidad, si se implementa, sería validar la **lógica** de la máquina de estados del firmware ante interrupciones del flujo de datos (correcta detección, reintento de configuración, ausencia de pérdida de datos del radar durante el evento), con independencia de los tiempos físicos reales de recuperación del receptor —que no pueden reproducirse mediante software en ningún caso, y quedan pendientes de validación con hardware real (véase apartado "Trabajo futuro")—. Se pospone su implementación para no incrementar la complejidad del script mientras no sea estrictamente necesaria para el desarrollo del firmware.

### 2.5 Límites conocidos de la emulación

- El parser de `UBX-CFG-VALSET` del emulador está simplificado a un conjunto fijo y conocido de claves de configuración (las tres empleadas por el firmware propio), no constituye un decodificador genérico del espacio completo de configuración de u-blox.
- Las observables sintéticas generadas para `UBX-RXM-RAWX` (pseudorange y fase de portadora calculadas con una fórmula simple, sin geometría satelital real) son válidas para verificar que el firmware extrae correctamente cada campo de cada sub-bloque, pero **no son aptas para un post-proceso PPK real con RTKLIB**: al no corresponder a mediciones físicas reales, cualquier solución de posición calculada a partir de ellas carecería de significado.
- Los tiempos de interrupción simulados (apartado 2.4) son arbitrarios y no reproducen el tiempo de primera fijación (TTFF) ni el tiempo de reconvergencia a solución RTK fija del receptor real.

Estas limitaciones no invalidan el emulador como herramienta de desarrollo de firmware; acotan su alcance a la validación funcional y de protocolo descrita en el apartado 1.3.

---

## 3. Máquina de estados del firmware y estrategia de captura en SD

### 3.1 Clasificación formal de la máquina de estados

La lógica de control del firmware de la Teensy 4.1 se implementa como una **máquina de estados finita (FSM) de tipo Mealy, jerárquica y dirigida por eventos**:

- **Mealy:** las acciones (envío de tramas, escritura en SD, inicio de temporizadores) se disparan en las transiciones, no como función exclusiva del estado activo.
- **Jerárquica:** el macro-estado `CONFIGURANDO_GPS` contiene una sub-máquina de estados propia para la secuencia de negociación, evitando una explosión combinatoria de estados en un diseño plano.
- **Dirigida por eventos:** las transiciones se disparan por interrupciones de recepción UART y temporizadores no bloqueantes, nunca mediante funciones de espera bloqueante (`delay()`), dado que el radar continúa transmitiendo a 100 Hz durante toda la fase de configuración del GPS; cualquier bloqueo del bucle principal provocaría pérdida de tramas de radar por desbordamiento del buffer de recepción.

### 3.2 Diagrama de estados (nivel macro)

```
[ARRANQUE]
    │
    ▼
INICIALIZACION_HW
    │ (hardware OK)
    ▼
VERIFICANDO_CONFIG_GPS ────────────────┐
    │ (config. ya correcta:            │ (falta o difiere alguna clave,
    │  todas las claves coinciden)     │  o timeout sin respuesta)
    │                                  ▼
    │                          CONFIGURANDO_GPS  ◄────────┐
    │                                  │ (config. completa)│ (reintentos agotados)
    │                                  ▼                   │
    └─────────────────────────► VERIFICANDO_FLUJO ─────────┘
                                       │ (primer NAV-PVT válido)
                                       ▼
                                  REGISTRANDO
                                       │ (señal de parada)
                                       ▼
                                  CIERRE_SEGURO
                                       │
                                       ▼
                                  [FIN / REPOSO]
```

### 3.3 Verificación previa mediante `UBX-CFG-VALGET`

Antes de comprometerse a la secuencia completa de negociación (que implica varias tramas `CFG-VALSET` y sus correspondientes `ACK`), el firmware realiza una **comprobación de bajo coste** del estado actual del receptor mediante una única petición `UBX-CFG-VALGET` (Class `0x06`, ID `0x8B`), consultando en un solo mensaje las cuatro claves relevantes (`CFG-MSGOUT-UBX_NAV_PVT_UART1`, `CFG-MSGOUT-UBX_RXM_RAWX_UART1`, `CFG-MSGOUT-UBX_RXM_SFRBX_UART1`, `CFG-UART1-BAUDRATE`) sobre la capa **RAM** (`layer = 0`), que refleja el valor efectivamente activo en el receptor en ese instante, con independencia de si procede de Flash, BBR o de una configuración de fábrica.

- **Si los tres valores devueltos coinciden** con los deseados (`NAV-PVT` activo, `RAWX` activo, baud rate `230400`), el firmware **omite por completo** la sub-máquina `CONFIGURANDO_GPS` y pasa directamente a `VERIFICANDO_FLUJO`. Dado que la decisión de diseño adoptada en el apartado 1.4 es escribir la configuración únicamente en la capa RAM (no en Flash), esta comprobación no protege frente a un ciclo completo de apagado/encendido del GPS —tras el cual la RAM siempre habrá vuelto a los valores de fábrica—, sino frente a un **reinicio de la Teensy que no implique un corte de alimentación del receptor GPS** (por ejemplo, un *watchdog reset* del microcontrolador, una recarga de firmware por USB, o un *brownout* que afecte solo al riel de alimentación de la Teensy): en ese escenario, la RAM del GPS conserva la configuración de la sesión anterior sin intervención de ninguna capa persistente, y renegociarla de todos modos sería un coste innecesario.
- **Si algún valor no coincide, el receptor responde `NAK`, o no hay respuesta dentro de un margen de tiempo** (p. ej. 300 ms), el firmware asume que no puede confiar en el estado actual y entra en `CONFIGURANDO_GPS` para fijarlo explícitamente, exactamente como en el diseño original.

Esta comprobación no sustituye a la política de recuperación en vuelo (apartado 3.7): esta última sigue disparándose por ausencia sostenida de mensajes UBX válidos durante `REGISTRANDO`, no por una re-consulta periódica de configuración.

**Estructura de la trama `UBX-CFG-VALGET` (petición)**, según [1], apartado 3.10.24.1, p. 97:

| Offset | Campo | Valor |
|---|---|---|
| 0 | `version` | `0x00` |
| 1 | `layer` | `0x00` (RAM) |
| 2-3 | `position` | `0x0000` |
| 4+ | `keys[]` | Las cuatro keyID de interés, 4 bytes cada una |

La respuesta reutiliza el mismo Class/ID, distinguible por `version = 0x01`, seguida de pares clave-valor concatenados con el tamaño de valor correspondiente a cada clave (1 byte para las claves de activación de mensaje, 4 bytes para el baud rate).

### 3.4 Sub-máquina de configuración del GPS

| Estado | Acción al entrar | Evento | Transición |
|---|---|---|---|
| `CFG_ENVIAR_PVT` | Enviar `CFG-VALSET` (activar NAV-PVT); iniciar timeout | ACK / NAK-timeout | → `CFG_ENVIAR_RAWX` / reintento (máx. 3) → `CFG_ERROR` |
| `CFG_ENVIAR_RAWX` | Enviar `CFG-VALSET` (activar RXM-RAWX); iniciar timeout | ACK / NAK-timeout | → `CFG_ENVIAR_SFRBX` / reintento (máx. 3) → `CFG_ERROR` |
| `CFG_ENVIAR_SFRBX` | Enviar `CFG-VALSET` (activar RXM-SFRBX); iniciar timeout | ACK / NAK-timeout | → `CFG_ENVIAR_BAUDRATE` / reintento (máx. 3) → `CFG_ERROR` |
| `CFG_ENVIAR_BAUDRATE` | Enviar `CFG-VALSET` (baud rate 230400); iniciar timeout | ACK (al baud antiguo) / NAK-timeout | → `CFG_CONMUTAR_BAUDRATE` / reintento → `CFG_ERROR` |
| `CFG_CONMUTAR_BAUDRATE` | Margen no bloqueante; conmutar puerto serie | Margen cumplido | → sale del macro-estado, entra en `VERIFICANDO_FLUJO` |
| `CFG_ERROR` | Señalización de fallo | — | Bloqueo hasta revisión manual |

### 3.5 Política de fallo en configuración inicial

Si el receptor no confirma alguno de los comandos de configuración tras agotar un número máximo de reintentos (3), el firmware transiciona a `CFG_ERROR`, donde señaliza el fallo mediante un indicador LED y **no permite el paso a `REGISTRANDO`**, obligando a una revisión manual antes de iniciar una misión. Esta política, más conservadora que una alternativa de modo degradado (continuar registrando solo el radar), se adopta por priorizar la detección temprana de fallos de configuración en tierra frente a la posibilidad de completar una misión con datos GPS ausentes desde el origen.

### 3.6 Estrategia de logging triple en SD

Dado que RTKLIB (mediante su conversor RTKCONV) requiere un fichero binario UBX continuo, sin fragmentar por trama, para su procesamiento, la estrategia de logging separa el contenido crudo del contenido de sincronización en tres ficheros independientes, todos ellos habilitados únicamente durante los estados `VERIFICANDO_FLUJO` y `REGISTRANDO`:

| Fichero | Contenido | Propósito |
|---|---|---|
| `gps_raw.ubx` | Copia binaria íntegra, byte a byte, de todo lo recibido del GPS tras completar la configuración, sin decodificar | Entrada directa y compatible con RTKCONV/RTKLIB para el cálculo PPK |
| `gps_sync.csv` | `timestamp_MCU_us`, `iTOW_ms` (de `NAV-PVT`), `rcvTow_s` (de `RXM-RAWX`), `tipo_mensaje` | Ancla de correlación entre el reloj de la Teensy y el tiempo GPS absoluto (regresión de deriva) |
| `radar_log.csv` | `timestamp_MCU_us`, `altitud_cm`, `snr`, `gps_estado` | Serie temporal de altura, en el mismo dominio de reloj que `gps_sync.csv` |

Se capturan **ambas** marcas de tiempo GPS, no solo `iTOW`: el campo `rcvTow` de `RXM-RAWX` ([1], apartado 3.17.6, p. 198) es nativo del propio flujo que se quiere sincronizar con precisión (el de las observables PPK), evitando cualquier desfase entre la generación interna de `NAV-PVT` y `RXM-RAWX` dentro del receptor. `iTOW` se conserva como referencia cruzada de validación, no como ancla principal. Nótese que `rcvTow` está descrito en la documentación como tiempo *local* del receptor "aproximadamente alineado" con GPS, sin la corrección de sesgo de reloj que sí incorpora la solución de navegación de `NAV-PVT` — un matiz a tener en cuenta si ambas marcas de tiempo llegaran a discrepar de forma sistemática en los ensayos de campo.

El campo `iTOW`/`rcvTow` se extrae mediante un reconocimiento ligero de cabecera, ejecutado en paralelo a la copia binaria sin alterarla, capturando el timestamp del MCU en el instante más temprano posible de la trama para minimizar el jitter de captura introducido por el propio firmware.

Toda trama NMEA o de cualquier otro tipo recibida **antes** de alcanzar `VERIFICANDO_FLUJO` (incluyendo la emisión de fábrica previa a la configuración) se descarta y no llega a escribirse en ningún fichero.

### 3.7 Política de recuperación en vuelo

Se distingue explícitamente entre dos situaciones que, en el diseño inicial, no estaban diferenciadas:

- **Corrupción transitoria de una trama** (ruido puntual): se resuelve mediante la resincronización normal del parser ante un checksum inválido, sin disparar ningún cambio de estado.
- **Pérdida sostenida del flujo de mensajes UBX válidos:** se adopta un **timeout de 3 segundos** sin recepción de ningún mensaje UBX válido como disparador de reconfiguración. Este valor se ha dimensionado a partir del tiempo de reafijación del ZED-F9P tras una interrupción breve, especificado por u-blox en 2 segundos bajo la categoría "Reacquisition" ([3], tabla de prestaciones "Features", campo "Acquisition → Reacquisition: 2 s"), añadiendo un margen que evite falsos positivos en el caso de recuperación normal.

El tiempo de reconvergencia a solución RTK fija (`carrSoln = fixed` en `UBX-NAV-PVT`) constituye una magnitud independiente de la reafijación básica, no acotada por una cifra única en la documentación consultada (el propio Product Summary indica un "Convergence time" de RTK "< 10 sec", dependiente de condiciones atmosféricas, longitud de línea base, multipath y geometría satelital [3]), y **no debe condicionar** la salida del estado de degradación ni bloquear la máquina de estados. Esta información de calidad se traslada al post-proceso mediante la columna `gps_estado` de `radar_log.csv` (`OK` / `DEGRADADO`), evitando que el firmware, con información limitada en tiempo real, deba decidir qué muestras son o no aprovechables.

Ante un evento de pérdida sostenida durante el estado `REGISTRANDO`, la reconfiguración del GPS se ejecuta **en paralelo, sin abandonar dicho estado ni interrumpir el registro del radar** —a diferencia de la política adoptada para la configuración inicial (apartado 3.5)—, dado que interrumpir una misión de vuelo activa por un fallo potencialmente transitorio del GPS tiene un coste de oportunidad mucho mayor que el de conservar datos de calidad incierta, cuya validez definitiva se evaluará en post-proceso.

### 3.8 Registro continuo del radar y ventanas de estabilidad

El registro de radar se mantiene de forma continua durante todo el estado `REGISTRANDO`, sin limitarse a los instantes correspondientes a puntos de interés ya conocidos. Esto permite, en la fase de post-proceso, identificar las ventanas de estabilidad propias de un perfil de vuelo estático (*stop-and-stare*) mediante análisis de la propia serie temporal (por ejemplo, detección de varianza baja de altitud en ventanas deslizantes), sin depender de una fuente externa de sincronización —como un registro de *waypoints* del propio dron— que introduciría una dependencia y una posible fuente adicional de desincronización.

---

## Referencias

[1] u-blox, *u-blox F9 HPG 1.51 Interface Description* (UBXDOC-963802114-13124, revisión R01, 8 de noviembre de 2024). https://content.u-blox.com/sites/default/files/documents/u-blox-F9-HPG-1.51_InterfaceDescription_UBXDOC-963802114-13124.pdf

[2] u-blox, *ZED-F9P Integration Manual* (UBX-18010802, revisión R16). https://content.u-blox.com/sites/default/files/ZED-F9P_IntegrationManual_UBX-18010802.pdf

[3] u-blox, *ZED-F9P Product Summary* (UBX-17005151, revisión R17). https://content.u-blox.com/sites/default/files/ZED-F9P_ProductSummary_UBX-17005151.pdf

[4] Holybro, *H-RTK ZED-F9P Series (IST8310/BMM150 Compass)*, familia de documentación a la que pertenece el Ultralight (confirmado por el compás IST8310, coincidente con la ficha de producto oficial, y por la presencia de un "Standard H-RTK F9P Ultralight STP File" en la página de descargas de esta familia). https://docs.holybro.com/gps-and-rtk-system/f9p-h-rtk-series **Nota:** esta familia no publica una tabla de pinout específica para el Ultralight (solo para Rover Lite, Helical y Base); el conector de 8 pines de esta unidad no coincide exactamente con ninguno de los conectores documentados en [5] (combina líneas del "2nd GPS Port" de 6 pines con las líneas RX2/TX2 del "UART 2 Port", pero sin el pin PPS que sí incluye este último). La configuración de pines de 8 vías asumida en este documento procede de verificación empírica directa sobre la unidad física, no de esta fuente documental.

[5] Holybro, *Standard F9P (UART)*, subfamilia dentro de [4] que documenta el pinout de "Standard GPS Port" (10 pines), "2nd GPS Port" (6 pines) y "UART 2 Port" (6 pines, con PPS, disponible en la versión Helical), y que incluye el fichero mecánico STEP del Ultralight en su página de descargas. https://docs.holybro.com/gps-and-rtk-system/f9p-h-rtk-series/standard-f9p-uart/pinout

[6] Paul Clark, *F9P_RAWX_Logger*, ejemplos de uso de `UBX-CFG-VALSET`. https://github.com/PaulZC/F9P_RAWX_Logger/blob/master/UBX.md

[7] u-blox, *ZED-F9P-15B Data Sheet* (UBX-23009090, revisión R04, 10 de enero de 2025) — fuente del diagrama de bloques (Figura 1) que confirma la presencia de memoria flash interna.

[8] rtklibexplorer, "Exploring kinematic single-receiver solutions with RTKLIB and the u-blox F9P" (fichero de datos crudos `rover.ubx` de ejemplo). https://rtklibexplorer.wordpress.com/2021/01/08/exploring-kinematic-single-receiver-solutions-with-rtklib-and-the-u-blox-f9p/

[9] Pan, L., Zhang, X., Li, X., Li, X., Lu, C., Liu, J., Wang, Q. (2019). "Satellite availability and point positioning accuracy evaluation on a global scale for integration of GPS, GLONASS, BeiDou and Galileo." *Advances in Space Research*, 63(9), 2696–2710. DOI: 10.1016/j.asr.2017.07.029.

[10] Mattos, P. G., Pisoni, F. (2018). "Quad-Constellation Receiver: GPS, GLONASS, Galileo, BeiDou." *GPS World*. https://www.gpsworld.com/quad-constellation-receiver-gps-glonass-galileo-beidou/

---

## Trabajo futuro / pendiente de validar

- **Obtener de Holybro una tabla de pinout oficial del conector de 8 pines del Ultralight** (no publicada actualmente; ni "2nd GPS Port" ni "UART 2 Port" documentados en [5] coinciden exactamente con esta configuración), para respaldar documentalmente la ausencia de PPS que por ahora se sustenta solo en verificación empírica directa sobre la unidad física.
- **Confirmar si el H-RTK ZED-F9P Ultralight incorpora pila de respaldo/supercondensador para la capa BBR** (la persistencia en Flash ya queda confirmada como interna al chip y no depende de esto).
- **Verificar disponibilidad comercial del ZED-F9P.** La ficha de producto oficial de u-blox marca las variantes 02B/04B/05B/15B como "no longer available" y al menos un datasheet indica "End-Of-Life", mientras que el *Product overview* de mayo de 2026 sigue listando la familia como activa. Confirmar directamente con Holybro/distribuidor antes de formalizar la compra del H-RTK ZED-F9P Ultralight.
- Confirmación del perfil de vuelo estático (*stop-and-stare*).
- Cierre del offset exacto de `UBX-RXM-RAWX` con el mismo rigor ya aplicado a `UBX-NAV-PVT`.
- Implementar (opcional) la simulación de interrupciones controladas en el emulador (apartado 2.4), actualmente solo diseñada sobre el papel.
- Validación empírica del timeout de 3 s (Reacquisition y convergencia RTK) sobre el H-RTK ZED-F9P Ultralight real, una vez disponible el hardware.

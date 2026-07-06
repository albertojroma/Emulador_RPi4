# Banco de pruebas Hardware-in-the-Loop (HIL): emulación del radar US-D1 y del GPS-PPK ZED-F9P

## 1. Requisitos para la emulación del comportamiento del GPS

### 1.1 Mensajes UBX necesarios para un flujo de trabajo PPK

El cálculo de posición de precisión centimétrica mediante PPK (*Post-Processed Kinematic*) no se basa en la solución de navegación en tiempo real del receptor, sino en las **observables crudas** de fase de portadora, pseudodistancia y Doppler, que un software de post-proceso ([RTKLIB](https://www.rtklib.com/)) combina con los datos de una estación base o servicio de corrección. De ello se derivan dos mensajes UBX de interés, con roles distintos:

| Mensaje | Rol |
|---|---|
| `UBX-RXM-RAWX` | **Imprescindible.** Contiene las observables crudas por satélite (pseudorange, fase de portadora, Doppler) que constituyen la materia prima del cálculo PPK [1]. |
| `UBX-NAV-PVT` | **Recomendable, no estrictamente obligatorio para el cálculo PPK en sí.** Aporta una solución de posición en tiempo real de menor precisión, útil como verificación en campo, y contiene el campo `iTOW` que se emplea como ancla de sincronización entre el reloj de la Teensy 4.1 y el tiempo GPS absoluto [1]. |

### 1.2 Estado de configuración de fábrica

El ZED-F9P, en su configuración de fábrica, emite únicamente mensajes NMEA estándar sobre UART1 a 38400 baudios; ni `UBX-NAV-PVT` ni `UBX-RXM-RAWX` están activados por defecto [2]. Este comportamiento debe replicarse fielmente en el emulador HIL, de forma que el firmware de la Teensy se vea obligado a ejercitar su secuencia completa de configuración, en lugar de asumir un receptor ya preparado —una asunción que no sería válida frente al hardware real.

### 1.3 Parámetros de configuración requeridos

La activación de los mensajes necesarios y el ajuste del baud rate se realizan mediante mensajes `UBX-CFG-VALSET`, dirigidos a las siguientes claves de configuración:

| Configuración | Key ID | Valor |
|---|---|---|
| Activar `NAV-PVT` en UART1 (cada época) | `0x20910007` | `0x01` |
| Activar `RXM-RAWX` en UART1 (cada época) | `0x209102A5` | `0x01` |
| Baud rate de UART1 | `0x40520001` | `230400` |

El incremento del baud rate por encima del valor de fábrica es necesario porque la documentación de u-blox recomienda entre 230400 y 460800 baudios cuando se activan mensajes UBX de datos crudos junto con la solución de navegación, para evitar saturar la interfaz serie [3].

### 1.4 Persistencia de configuración: incertidumbre y decisión de diseño

La configuración enviada mediante `CFG-VALSET` puede almacenarse en tres capas de persistencia distintas: RAM (volátil), BBR —Battery-Backed RAM, que requiere una pila de respaldo conectada al pin `V_BCKP`— o Flash externa, que depende de que la placa portadora incluya un chip de memoria dedicado, ya que el propio chip ZED-F9P no dispone de flash interna [1]. No se ha podido confirmar en la documentación pública de Holybro si el módulo H-RTK ZED-F9P Ultralight incorpora batería de respaldo o flash externa.

Ante esta incertidumbre, se adopta la decisión de diseño de **no depender de la persistencia de configuración del receptor**: el firmware de la Teensy 4.1 reenvía la secuencia completa de `CFG-VALSET` en cada arranque, asumiendo en todo momento que el GPS puede encontrarse en su estado de fábrica. Esta decisión es válida independientemente de si el hardware finalmente resulta tener persistencia o no, y es coherente con el objetivo de portabilidad del sistema.

### 1.5 Ausencia de señal PPS y su implicación

El conector JST GH-1.25 de 8 pines del H-RTK ZED-F9P Ultralight (VCC, RX1, TX1, SCL, SDA, RX2, TX2, GND) no expone la señal TIMEPULSE (PPS) del chip ZED-F9P, a diferencia de otras variantes de la familia H-RTK que sí incluyen esta señal en un conector UART2 independiente. En consecuencia, la sincronización entre el reloj interno de la Teensy 4.1 y el tiempo GPS absoluto no puede basarse en la disciplina de reloj por flanco de PPS, y se resuelve mediante una **regresión lineal en post-proceso** entre el timestamp del reloj de la Teensy y el campo `iTOW` (tiempo GPS de semana) contenido en los propios mensajes UBX.

### 1.6 Configuración de doble UART en la Raspberry Pi 4

El banco HIL emplea dos interfaces UART simultáneas en la Raspberry Pi 4 para emular radar y GPS de forma independiente:

| Función | GPIO (BCM) | Pines físicos | Dispositivo Linux |
|---|---|---|---|
| UART0 (radar) | GPIO14 (TX) / GPIO15 (RX) | 8 / 10 | `/dev/serial0` |
| UART3 (GPS) | GPIO4 (TX) / GPIO5 (RX) | 7 / 29 | `/dev/ttyAMA1` |

La activación de UART3 requiere añadir `dtoverlay=uart3` en `config.txt`, fichero que es procesado por el firmware de arranque de la Raspberry Pi —no por el kernel Linux— antes de fusionar el overlay correspondiente con el device tree base [6]. Es importante señalar que **el nombre de dispositivo asignado por Linux no coincide necesariamente con el número del overlay activado**: el kernel asigna los nombres `/dev/ttyAMAx` de forma secuencial según el orden de registro de los controladores PL011 activos, no según el número indicado en `dtoverlay=uartN`. En la configuración empleada en este proyecto, el overlay `uart3` resulta en el dispositivo `/dev/ttyAMA1` (siendo el segundo controlador PL011 registrado tras el UART0 primario), verificado empíricamente mediante `minicom` y `raspi-gpio get`.

---

## 2. Arquitectura del emulador GPS y validez de la emulación

### 2.1 Arquitectura de doble hilo

El script `emulador_gps.py`, ejecutado en la Raspberry Pi 4, implementa dos hilos de ejecución concurrentes sobre el mismo puerto serie:

- **Hilo de emisión (bucle principal):** genera y transmite periódicamente los mensajes `UBX-NAV-PVT` y `UBX-RXM-RAWX`, condicionado al estado de configuración activo en cada momento.
- **Hilo de escucha:** procesa de forma continua los bytes entrantes procedentes de la Teensy, buscando tramas `UBX-CFG-VALSET`.

Esta arquitectura es necesaria porque el receptor real atiende comandos de configuración y emite datos de navegación de forma concurrente, no secuencial; un emulador de un único hilo no podría replicar ese comportamiento sin introducir bloqueos artificiales. El acceso al estado de configuración compartido entre ambos hilos se protege mediante un `threading.Lock`.

### 2.2 Protocolo de negociación de configuración

El emulador arranca en el mismo estado de fábrica descrito en el apartado 1.2 (NMEA activo, UBX inactivo, 38400 baudios). Al recibir una trama `UBX-CFG-VALSET` con checksum válido, el hilo de escucha actualiza su estado interno (activación de mensajes, cambio de baud rate) y responde con `UBX-ACK-ACK`; si el checksum no es válido, responde con `UBX-ACK-NAK`. Este comportamiento replica fielmente el mecanismo de confirmación del protocolo UBX real [1], permitiendo validar contra el emulador la misma lógica de espera de confirmación que el firmware deberá implementar frente al receptor físico.

### 2.3 Gestión del cambio de baud rate

Al procesar un cambio de baud rate, el emulador envía primero el `ACK-ACK` **al baud rate anterior**, y solo después de un breve margen conmuta su propia velocidad de puerto. Este orden es intencional: si la conmutación ocurriera antes de que el `ACK` hubiera salido físicamente por el cable, el host (la Teensy) no podría leer dicha confirmación, al estar ya escuchando a la nueva velocidad mientras la respuesta aún viaja a la antigua.

### 2.4 Simulación de interrupciones controladas

El emulador incorpora la capacidad de simular dos tipos de interrupción del servicio, mediante los parámetros `--simular_corte_en`, `--duracion_corte` y `--tipo_corte`:

- **Corte de comunicación:** el emulador deja de transmitir durante el intervalo indicado, pero conserva su estado de configuración interno, replicando una interrupción física del cableado sin pérdida de alimentación en el receptor.
- **Corte de alimentación:** además de interrumpir la transmisión, el emulador resetea su estado de configuración a los valores de fábrica al finalizar el corte, replicando un reinicio real del receptor que exige una renegociación completa.

El propósito de esta funcionalidad es validar la **lógica** de la máquina de estados del firmware ante interrupciones del flujo de datos (correcta detección, reintento de configuración, ausencia de pérdida de datos del radar durante el evento), con independencia de los tiempos físicos reales de recuperación del receptor, que no pueden reproducirse mediante software y quedan pendientes de validación con hardware real (véase apartado "Trabajo futuro").

### 2.5 Límites conocidos de la emulación

- El parser de `UBX-CFG-VALSET` del emulador está simplificado a un conjunto fijo y conocido de claves de configuración (las tres empleadas por el firmware propio), no constituye un decodificador genérico del espacio completo de configuración de u-blox.
- Las observables sintéticas generadas para `UBX-RXM-RAWX` (pseudorange y fase de portadora calculadas con una fórmula simple, sin geometría satelital real) son válidas para verificar que el firmware extrae correctamente cada campo de cada sub-bloque, pero **no son aptas para un post-proceso PPK real con RTKLIB**: al no corresponder a mediciones físicas reales, cualquier solución de posición calculada a partir de ellas carecería de significado.
- Los tiempos de interrupción simulados (apartado 2.4) son arbitrarios y no reproducen el tiempo de primera fijación (TTFF) ni el tiempo de reconvergencia a solución RTK fija del receptor real.

Estas limitaciones no invalidan el emulador como herramienta de desarrollo de firmware; acotan su alcance a la validación funcional y de protocolo descrita en el apartado 1.3.

---

## 4. Máquina de estados del firmware y estrategia de captura en SD

### 4.1 Clasificación formal de la máquina de estados

La lógica de control del firmware de la Teensy 4.1 se implementa como una **máquina de estados finita (FSM) de tipo Mealy, jerárquica y dirigida por eventos**:

- **Mealy:** las acciones (envío de tramas, escritura en SD, inicio de temporizadores) se disparan en las transiciones, no como función exclusiva del estado activo.
- **Jerárquica:** el macro-estado `CONFIGURANDO_GPS` contiene una sub-máquina de estados propia para la secuencia de negociación, evitando una explosión combinatoria de estados en un diseño plano.
- **Dirigida por eventos:** las transiciones se disparan por interrupciones de recepción UART y temporizadores no bloqueantes, nunca mediante funciones de espera bloqueante (`delay()`), dado que el radar continúa transmitiendo a 100 Hz durante toda la fase de configuración del GPS; cualquier bloqueo del bucle principal provocaría pérdida de tramas de radar por desbordamiento del buffer de recepción.

### 4.2 Diagrama de estados (nivel macro)

```
[ARRANQUE]
    │
    ▼
INICIALIZACION_HW
    │ (hardware OK)
    ▼
CONFIGURANDO_GPS  ◄────────────┐
    │ (config. completa)       │ (reintentos agotados)
    ▼                          │
VERIFICANDO_FLUJO ──────────────┘
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

### 4.3 Sub-máquina de configuración del GPS

| Estado | Acción al entrar | Evento | Transición |
|---|---|---|---|
| `CFG_ENVIAR_PVT` | Enviar `CFG-VALSET` (activar NAV-PVT); iniciar timeout | ACK / NAK-timeout | → `CFG_ENVIAR_RAWX` / reintento (máx. 3) → `CFG_ERROR` |
| `CFG_ENVIAR_RAWX` | Enviar `CFG-VALSET` (activar RXM-RAWX); iniciar timeout | ACK / NAK-timeout | → `CFG_ENVIAR_BAUDRATE` / reintento → `CFG_ERROR` |
| `CFG_ENVIAR_BAUDRATE` | Enviar `CFG-VALSET` (baud rate 230400); iniciar timeout | ACK (al baud antiguo) / NAK-timeout | → `CFG_CONMUTAR_BAUDRATE` / reintento → `CFG_ERROR` |
| `CFG_CONMUTAR_BAUDRATE` | Margen no bloqueante; conmutar puerto serie | Margen cumplido | → sale del macro-estado, entra en `VERIFICANDO_FLUJO` |
| `CFG_ERROR` | Señalización de fallo | — | Bloqueo hasta revisión manual |

### 4.4 Política de fallo en configuración inicial

Si el receptor no confirma alguno de los comandos de configuración tras agotar un número máximo de reintentos (3), el firmware transiciona a `CFG_ERROR`, donde señaliza el fallo mediante un indicador LED y **no permite el paso a `REGISTRANDO`**, obligando a una revisión manual antes de iniciar una misión. Esta política, más conservadora que una alternativa de modo degradado (continuar registrando solo el radar), se adopta por priorizar la detección temprana de fallos de configuración en tierra frente a la posibilidad de completar una misión con datos GPS ausentes desde el origen.

### 4.5 Estrategia de logging triple en SD

Dado que RTKLIB (mediante su conversor RTKCONV) requiere un fichero binario UBX continuo, sin fragmentar por trama, para su procesamiento, la estrategia de logging separa el contenido crudo del contenido de sincronización en tres ficheros independientes, todos ellos habilitados únicamente durante los estados `VERIFICANDO_FLUJO` y `REGISTRANDO`:

| Fichero | Contenido | Propósito |
|---|---|---|
| `gps_raw.ubx` | Copia binaria íntegra, byte a byte, de todo lo recibido del GPS tras completar la configuración, sin decodificar | Entrada directa y compatible con RTKCONV/RTKLIB para el cálculo PPK |
| `gps_sync.csv` | `timestamp_MCU_us`, `iTOW_ms`, `tipo_mensaje` | Ancla de correlación entre el reloj de la Teensy y el tiempo GPS absoluto (regresión de deriva) |
| `radar_log.csv` | `timestamp_MCU_us`, `altitud_cm`, `snr`, `gps_estado` | Serie temporal de altura, en el mismo dominio de reloj que `gps_sync.csv` |

El campo `iTOW` se extrae mediante un reconocimiento ligero de cabecera, ejecutado en paralelo a la copia binaria sin alterarla, capturando el timestamp del MCU en el instante más temprano posible de la trama para minimizar el jitter de captura introducido por el propio firmware.

Toda trama NMEA o de cualquier otro tipo recibida **antes** de alcanzar `VERIFICANDO_FLUJO` (incluyendo la emisión de fábrica previa a la configuración) se descarta y no llega a escribirse en ningún fichero.

### 4.6 Política de recuperación en vuelo

Se distingue explícitamente entre dos situaciones que, en el diseño inicial, no estaban diferenciadas:

- **Corrupción transitoria de una trama** (ruido puntual): se resuelve mediante la resincronización normal del parser ante un checksum inválido, sin disparar ningún cambio de estado.
- **Pérdida sostenida del flujo de mensajes UBX válidos:** se adopta un **timeout de 3 segundos** sin recepción de ningún mensaje UBX válido como disparador de reconfiguración. Este valor se ha dimensionado a partir del tiempo de primera fijación (TTFF) en *hot start* especificado por u-blox para el ZED-F9P, de aproximadamente 2 segundos [3], añadiendo un margen que evite falsos positivos en el caso de recuperación normal.

El tiempo de reconvergencia a solución RTK fija (`carrSoln = fixed` en `UBX-NAV-PVT`) constituye una magnitud independiente del TTFF básico, no acotada por una cifra única en la documentación consultada, y **no debe condicionar** la salida del estado de degradación ni bloquear la máquina de estados. Esta información de calidad se traslada al post-proceso mediante la columna `gps_estado` de `radar_log.csv` (`OK` / `DEGRADADO`), evitando que el firmware, con información limitada en tiempo real, deba decidir qué muestras son o no aprovechables.

Ante un evento de pérdida sostenida durante el estado `REGISTRANDO`, la reconfiguración del GPS se ejecuta **en paralelo, sin abandonar dicho estado ni interrumpir el registro del radar** —a diferencia de la política adoptada para la configuración inicial (apartado 4.4)—, dado que interrumpir una misión de vuelo activa por un fallo potencialmente transitorio del GPS tiene un coste de oportunidad mucho mayor que el de conservar datos de calidad incierta, cuya validez definitiva se evaluará en post-proceso.

### 4.7 Registro continuo del radar y ventanas de estabilidad

El registro de radar se mantiene de forma continua durante todo el estado `REGISTRANDO`, sin limitarse a los instantes correspondientes a puntos de interés ya conocidos. Esto permite, en la fase de post-proceso, identificar las ventanas de estabilidad propias de un perfil de vuelo estático (*stop-and-stare*) mediante análisis de la propia serie temporal (por ejemplo, detección de varianza baja de altitud en ventanas deslizantes), sin depender de una fuente externa de sincronización —como un registro de *waypoints* del propio dron— que introduciría una dependencia y una posible fuente adicional de desincronización.

---

## Referencias

[1] u-blox, *ZED-F9P Interface Description* (UBX-18010854).

[2] u-blox, *ZED-F9P Integration Manual* (UBX-18010802). https://content.u-blox.com/sites/default/files/ZED-F9P_IntegrationManual_UBX-18010802.pdf

[3] u-blox, *ZED-F9P Data Sheet* (especificación de TTFF hot/cold start). https://cdn.sparkfun.com/assets/8/3/2/b/8/ZED-F9P_Data_Sheet.pdf

[4] Holybro, documentación de la serie H-RTK ZED-F9P (especificaciones y pinout). https://docs.holybro.com/gps-and-rtk-system/zed-f9p-h-rtk-series

[5] Holybro, documentación de la serie Standard F9P (UART) (pinout UART1/UART2). https://docs.holybro.com/gps-and-rtk-system/f9p-h-rtk-series/standard-f9p-uart

[6] Raspberry Pi, README de overlays de device tree (`dtoverlay=uartN`), `/boot/firmware/overlays/README` (documentación local del sistema operativo).

[7] Paul Clark, *F9P_RAWX_Logger*, ejemplos de uso de `UBX-CFG-VALSET`. https://github.com/PaulZC/F9P_RAWX_Logger/blob/master/UBX.md

---

## Trabajo futuro / pendiente de validar

- Confirmación del perfil de vuelo estático (*stop-and-stare*).
- Verificación física de batería de respaldo / memoria flash en el módulo Holybro Ultralight.
- Cierre del offset exacto de `UBX-RXM-RAWX` con el mismo rigor ya aplicado a `UBX-NAV-PVT`.
- Validación empírica del timeout de 3 s (TTFF y reconvergencia RTK) sobre el H-RTK ZED-F9P Ultralight real, una vez disponible el hardware.

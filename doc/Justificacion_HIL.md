## 1. Justificación del banco HIL

### 1.1 Motivaciones originales

El desarrollo del firmware de la Teensy 4.1 —encargado de leer, sincronizar y registrar en tarjeta SD los flujos de datos del radar altimétrico US-D1 (Ainstein) y del receptor GNSS H-RTK ZED-F9P Ultralight (Holybro)— se apoya en un banco de pruebas Hardware-in-the-Loop (HIL) por dos motivos principales:

1. **Protección de hardware de coste elevado.** Tanto el módulo GNSS multibanda como el radar FMCW son componentes costosos cuya integridad no debe arriesgarse durante las fases iniciales de desarrollo y depuración de firmware, en las que los errores de programación (bucles de escritura descontrolados, configuraciones de voltaje incorrectas, cortocircuitos accidentales durante el cableado) son más probables.
2. **Portabilidad del desarrollo.** Al sustituir los sensores reales por un emulador ejecutado en una Raspberry Pi 4 Model B, el desarrollo del firmware puede realizarse fuera del laboratorio, llevando únicamente la Raspberry Pi y la propia Teensy 4.1.

### 1.2 Ausencia actual de hardware real como justificación adicional

A las dos motivaciones anteriores se añade una circunstancia práctica y muy concreta del estado actual del proyecto: **el módulo GPS-PPK real (H-RTK ZED-F9P Ultralight) todavía no ha sido adquirido (06/07/26)**. En consecuencia, el banco HIL no es únicamente una medida de precaución frente a un hardware disponible pero delicado, sino la única vía posible para avanzar en el diseño y la validación funcional del firmware mientras dicha adquisición se resuelve. Esto refuerza el propio planteamiento metodológico del HIL: cualquier decisión de diseño que dependa de la disponibilidad física del receptor (por ejemplo, la caracterización de tiempos de reafijación tras un corte de alimentación) queda necesariamente pospuesta y debe documentarse como tal, sin que ello bloquee el resto del desarrollo.

### 1.3 Alcance y límites de la validación mediante HIL

Conviene distinguir explícitamente dos niveles de validación que el HIL cubre de forma desigual:

- **Validación funcional y de protocolo del firmware** (parseo correcto de tramas, gestión de la máquina de estados, escritura en SD, negociación de configuración UBX): el banco HIL es, en este nivel, una herramienta suficiente y adecuada. La fidelidad temporal del generador de estímulos (jitter del emulador) es irrelevante para este propósito, ya que la detección de tramas se realiza mediante interrupciones de recepción UART, indiferentes a la puntualidad de origen de cada byte.
- **Validación de precisión de sincronización final y de tiempos físicos del receptor** (deriva del oscilador de la Teensy en vuelos de larga duración, tiempo de primera fijación tras un corte de alimentación, tiempo de reconvergencia a solución RTK fija): esta validación depende de fenómenos físicos del hardware real (comportamiento de un oscilador de cristal concreto, adquisición de señal satelital, resolución de ambigüedades de fase de portadora) que ningún emulador software puede reproducir con validez. Este nivel de validación queda, por definición, fuera del alcance del HIL y debe abordarse posteriormente con el hardware físico disponible.

### 1.4 Elección de la Raspberry Pi 4 Model B frente a un MCU dedicado

Para la generación de los estímulos del banco HIL se ha optado por una Raspberry Pi 4 Model B, ya disponible en el proyecto, en lugar de un segundo microcontrolador dedicado (por ejemplo, una segunda unidad Teensy 4.1). La Raspberry Pi 4, al ejecutar Linux —un sistema operativo de propósito general—, introduce **jitter no determinista** en la temporización de los mensajes generados, frente al jitter de orden microsegundo o inferior que ofrecería un MCU con temporizadores hardware dedicados.

Esta limitación es aceptable en la fase actual del proyecto porque, como se ha razonado en el apartado 1.3, la validación que se persigue con el HIL es de tipo funcional/protocolar, no de precisión temporal fina. La alternativa de un segundo MCU debería reconsiderarse únicamente si, en una fase posterior, fuera necesario **caracterizar cuantitativamente** el jitter propio del firmware de la Teensy frente a una referencia de temporización independiente y fiable —objetivo para el que un generador basado en Linux no resulta adecuado, al contaminar la medida con su propio jitter de planificación.
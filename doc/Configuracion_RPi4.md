# Configuración previa en la Rapsberry Pi 4 model B

Para usar el puerto serie hay que configurarlo previamente. Se recomienda ver el siguiente [vídeo](https://www.youtube.com/watch?v=oevxqPk78sM) donde se explica como configurar el puerto serie en la Rapsberry Pi 4.

Además, para activar las UARTs de forma manual hay que ir al archivo `config.txt` (está en `/boot/config.txt` o en `/boot/firmware/config.txt`). Este archivo permite realizar modificaciones en el *device tree*. Hay que añadir 2 líneas en este archivo:
* `enable_uart=1`: permite *mapear* la UART a los GPIOs correspondientes
* `dtoverlay=uartX`: donde `X` representa el número de la UART que se quiere activar. En este caso se ha activado el 3

**Nota**: Hay que tener en cuenta que cuando se activa el puerto serie siguiendo las indicaciones del vídeo hay 2 formas de acceder a ese dispositivo: `/dev/serial0` o `/dev/ttyAMA0`. En la RPi4 la notación va en orden, no en función del dispositivo activo, es decir, que para hacer referencia al puerto serie sobre el que está mapeada la UART3, si solo hay 2 UARTs activas se accede mediante `/dev/ttyAMA1`.

## Configuración de doble UART

El banco HIL emplea dos interfaces UART simultáneas en la Raspberry Pi 4 para emular radar y GPS de forma independiente:

| Función | GPIO (BCM) | Pines físicos | Dispositivo Linux |
|---|---|---|---|
| UART0 (radar) | GPIO14 (TX) / GPIO15 (RX) | 8 / 10 | `/dev/serial0` |
| UART3 (GPS) | GPIO4 (TX) / GPIO5 (RX) | 7 / 29 | `/dev/ttyAMA1` |

La activación de UART3 requiere añadir `dtoverlay=uart3` en `config.txt`, fichero que es procesado por el firmware de arranque de la Raspberry Pi —no por el kernel Linux— antes de fusionar el overlay correspondiente con el device tree base [1]. Es importante señalar que **el nombre de dispositivo asignado por Linux no coincide necesariamente con el número del overlay activado**: el kernel asigna los nombres `/dev/ttyAMAx` de forma secuencial según el orden de registro de los controladores PL011 activos, no según el número indicado en `dtoverlay=uartN`. En la configuración empleada en este proyecto, el overlay `uart3` resulta en el dispositivo `/dev/ttyAMA1` (siendo el segundo controlador PL011 registrado tras el UART0 primario), verificado empíricamente mediante `minicom` y `raspi-gpio get`.

[1] Raspberry Pi, README de overlays de device tree (`dtoverlay=uartN`), `/boot/firmware/overlays/README` (documentación local del sistema operativo).
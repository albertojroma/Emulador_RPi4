# Configuración previa en la Rapsberry Pi 4 model B

Para usar el puerto serie hay que configurarlo previamente. Se recomienda ver el siguiente [vídeo](https://www.youtube.com/watch?v=oevxqPk78sM) donde se explica como configurar el puerto serie en la Rapsberry Pi 4.

Además, para activar las UARTs de forma manual hay que ir al archivo `config.txt` (está en `/boot/config.txt` o en `/boot/firmware/config.txt`). Este archivo permite realizar modificaciones en el *device tree*. Hay que añadir 2 líneas en este archivo:
* `enable_uart=1`: permite *mapear* la UART a los GPIOs correspondientes
* `dtoverlay=uartX`: donde `X` representa el número de la UART que se quiere activar. En este caso se ha activado el 3

**Nota**: Hay que tener en cuenta que cuando se activa el puerto serie siguiendo las indicaciones del vídeo hay 2 formas de acceder a ese dispositivo: `/dev/serial0` o `/dev/ttyAMA0`. En la RPi4 la notación va en orden, no en función del dispositivo activo, es decir, que para hacer referencia al puerto serie sobre el que está mapeada la UART3, si solo hay 2 UARTs activas se accede mediante `/dev/ttyAMA1`.
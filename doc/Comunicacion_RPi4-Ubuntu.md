# Comunicación entre la RPi4 y la máquina Ubuntu

Esta parte de la documentación se centra en explicar como se comunica la RPi4 y la máquina Ubuntu para diferentes propósitos. 
1. Lo primero es la conexión `ssh` para poder trabajar en la RPi4 desde nuestra máquina Ubuntu. Esto nos dará más comodidad a la hora de realizar el proyecto.
2. Lo segundo es el uso del puerto serie de la RPi4 y como realizar comprobaciones usando el conversor UART-USB

# Conexión `ssh`

Para trabajar cómodamente con la Raspberry y transmitir información como si de 2 ordenadores en red se tratase se propone usar `ssh`. A continuación, se detallan cosas a tener en cuenta. 

## Establecer conexión `ssh` entre la Raspberry y la máquina Ubuntu. 

Hay muchas maneras de realizar este proyecto. Se podría hacer todo desde la propia Raspberry como si de un ordenador normal se tratase. Sin embargo, lo más cómodo en este caso es conectarse desde otra máquina más potente a la Raspberry mediante ssh (utilizando un cable ethernet entre ambos dispositivos). Para ello hay que seguir 3 pasos sencillos:
* Configurar la conexión por ethernet de forma correcta (ver imagen inferior)
![ajustes_IPv4](imgs/ajustes_IPv4.png)

* Conectar el cable de red entre los dispositivos

* Abrir un terminal y escribir `ssh NOMBRE_USUARIO_RASPBERRY@raspberrypi.local`. A continuación, poner la contraseña que se estableció para ese sistema y ya debería dejarnos entrar:
![conexion_ssh](imgs/conexion_ssh.png)

## Envío de archivos entre portátil y raspberry pi mediante `ssh`

Hay varios métodos, pero se pueden resumir en:
* Terminal (usar `scp` o `sftp`)
* Método gráfico. Básicamente conectarse a la RPi4 como si fuese un maquina externa a través del explorador de archivos. Los pasos a seguir son:
  1. Abre tu explorador de archivos normal.
  2. En la barra lateral izquierda, haz clic en "+ Otras ubicaciones" (Other Locations).
  3. Abajo del todo, verás una barra que dice "Conectar al servidor".
  4. Escribe la dirección en este formato: `sftp://NOMBRE_USUARIO_RASPBERRY@raspberrypi.local`
  5. Haz clic en Conectar. Te pedirá el usuario y la contraseña.
  6. ¡Listo! Verás los archivos de la Raspberry Pi como si fuera un pendrive conectado a tu portátil y podrás copiar, pegar y borrar con el ratón.

# Uso del puerto serie

Para realizar la emulación de este proyecto se van a utilizar los pies conectados a la UART de la Raspberry. A continuación, se explicarán varias cosas a tener en cuenta antes de comenzar a usar el puerto serie.

### Envío sencillo de datos entre el portátil y la Raspberry

Antes de emular nada, es conveniente realizar una transmisión, utilizando el puerto serie, entre máquinas. De esta manera, podemos comprobar que los cables están correctamente conectados y que todo funciona correctamente.

Para ello usaremos la herramienta *minicom*. Se instala mediante el siguiente comando en ambas máquinas `sudo apt install minicom`.

Para usar correctamente los pines UART de la Raspberry se recomienda usar el proyecto [Raspberry Pi Pinout](https://pinout.xyz/). 

|Pinout del la RPi4 | Pinout de la RPi4 destacando las UARTs|
| ----------------- | --------------------------------------|
|![pinout_RPi4](imgs/pinout_RPi4.png)|![pinout_UARTs_RPi4](imgs/pinout_UARTs_RPi4.png)|

En este caso se usarán los siguientes pines para la UART0:
* 9: *Ground* (Cable gris)
* 8: *GPIO 14 (UART0 TX)* (Cable morado)
* 10: *GPIO 15 (UART0 RX)* (Cable verde). Como nos interesa solo la transmisión este pin es irrelevante

Para la UART3 (se ha escogido esta porque los pines **TX** están cerca de la UART0):
* 9: *Ground* (Cable gris)
* 7: *GPIO 4 (UART3 TX)* (Cable morado)
* 29: *GPIO 5 (UART3 RX)* (Cable verde). Como nos interesa solo la transmisión este pin es irrelevante

Teniendo claros los pines de la Raspberry, ahora hay que realizar la correcta conexión con el adaptador de USB a UART como se muestra en la imagen inferior:

![Conexionado_adaptador_RPi4](imgs/Conexionado_adaptador_RPi4.jpg)

A continuación, lanzamos `minicom` en cada máquina ejecutando el siguiente comando:

`minicom -D /dev/PUERTO_QUE_CORRESPONDA -b 115200` donde los argumentos indican:
* `-D /dev/PUERTO_QUE_CORRESPONDA`: ruta al puerto serie (recordar que en linux, todos los dispositivos se tratan como archivos)
* `-b 115200`: se indican los baudios

En el caso del ordenador Ubuntu se usó `minicom -D /dev/ttyUSB0 -b 115200` y en el caso de la RPi4 se usó `minicom -D /dev/serial0 -b 115200`. 

En la imagen inferior tenemos 2 terminales en Ubuntu que están usando `minicom`. En el terminal de la izquierda es Ubuntu y el de la derecha la RPi4. 

![minicom_1](imgs/minicom_1.png)

En la siguiente imagen se observa que lo que se escribe en un terminal se ve en el otro, confirmando la correcta transmisión de datos entre máquinas mediante puerto serie.

![minicom_2](imgs/minicom_2.png)



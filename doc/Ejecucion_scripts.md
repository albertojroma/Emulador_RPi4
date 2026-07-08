# Ejecucion de scripts

En la carpeta `scripts` hay 4 archivos de python. 2 son para ejecutar desde la máquina Ubuntu y los otros 2 desde la RPi4:
* Ubuntu: [cap_data.py](../scripts/cap_data.py), [cap_raw.py](../scripts/cap_raw.py)  
* RPi4: [emulador_radar.py](../scripts/emulador_radar.py), [emulador_gps.py](../scripts/emulador_gps.py) 

# [cap_data.py](../scripts/cap_data.py)

*Script* encargado de capturar los datos que llegan por puerto serie y guardarlos en un archivo con extensión `.csv` 

La ejecución de este script debe ser desde la carpeta raíz del repositorio (`EMULADOR_RPi4`) en la máquina Ubuntu y se debe ejecutar el siguiente comando: 

`sudo python3 scripts/cap_data.py NOMBRE_ARCHIVO_A_GENERAR` donde `NOMBRE_ARCHIVO_A_GENERAR` corresponde con el nombre que se le quiera dar al archivo.

Es importante ejecutarlo siempre con permisos de administrador. **DE MOMENTO SOLO ESTA PENSADO PARA LA CAPTURA DE DATOS DEL RADAR**

# [cap_raw.py](../scripts/cap_raw.py) 

*Script* encargado de capturar los datos **crudos** que llegan por puerto serie y guardarlos en un archivo con extensión `.bin` 

La ejecución de este script debe ser desde la carpeta raíz del repositorio (`EMULADOR_RPi4`) en la máquina Ubuntu y se debe ejecutar el siguiente comando: 

`sudo python3 scripts/cap_raw.py NOMBRE_ARCHIVO_A_GENERAR SENSOR_A_CAPTURAR` donde `NOMBRE_ARCHIVO_A_GENERAR` corresponde con el nombre que se le quiera dar al archivo y `SENSOR_A_CAPTURAR` solo puede tener 2 valores en función del dispositivo del que se quieran capturar los datos: `radar` o `gps`.

# [emulador_radar.py](../scripts/emulador_radar.py)

*Script* encargado de emular las tramas de datos del radar desde la RPi4. Para ello, **desde la RPi4** se ejecuta el siguiente comando: `python3 emulador_radar.py NOMBRE_PUERTO_USADO_EN_RPi4` donde `NOMBRE_PUERTO_USADO_EN_RPi4` corresponde con el nombre del puerto que se usa en la RPi4. La RPi4 debería estar configurada para usar 2 puertos:
* `ttyAMA0` o `serial0` (son el mismo puerto): UART0
* `ttyAMA1`: UART3 (si se configura como se especifica en el documento [Configuracion_RPi4](Configuracion_RPi4.md)) 

# [emulador_gps.py](../scripts/emulador_gps.py) o [emulador_gps_NEW.py](../scripts/emulador_gps_NEW.py)

*DE MOMENTO ESTÁ LA VERSION NEW EN LA RPi4, YA SE ACTUALIZARÁ*

*Script* encargado de emular las tramas de datos del gps desde la RPi4. Para ello, **desde la RPi4** se ejecuta el siguiente comando: `python3 emulador_gps_NEW.py`

# Ejecución de 2 scripts a la vez

Para ejecutar 2 scripts a la vez se tiene que usar el operador `&&` de la siguiente manera:

`python3 emulador_radar
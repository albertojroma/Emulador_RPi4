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

*Script* encargado de emular las tramas de datos del radar desde la RPi4. Para ello, **desde la RPi4** se ejecuta el siguiente comando: `python3 emulador_radar.py`

# [emulador_gps.py](../scripts/emulador_gps.py)


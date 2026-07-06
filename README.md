# EMULADOR_RPi4

Este repositorio contiene la documentación y scripts necesarios para usar una [Rapsberry Pi 4 Model B](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/) (RPi4) como HIL, permitiendo la emulación de: 
* Radar [US-D1 de Ainstein](https://ainstein.ai/us-d1-all-weather-radar-altimeter/)
* GPS + Antena [H-RTK ZED-F9P Ultralight](https://holybro.com/products/h-rtk-f9p-ultralight?variant=45785783009469)

A continuación se explicará el contenido de este repositorio junto a su documentación:
* [Justificación de la realización de un HIL](doc/Justificacion_HIL.md): En este documento se justifica la realización de un *Hardware-in-the-loop* para este proyecto
* [Configuración previa de la RPi4](doc/Configuracion_RPi4.md): Se explica que configuraciones previas son necesarias en la RPi4
* [Comunicación entre la RPi4 y la máquina Ubuntu](doc/Comunicacion_RPi4-Ubuntu.md): Se explica como realizar diferentes tipos de comunicaciones entre la RPi4 y la máquina Ubuntu (intercambio de archivos, como comprobar los scripts, pines a usar en la RPi4...)
* [Ejecución de scripts](doc/Ejecucion_scripts.md): Breve guión de como usar los scripts creados
* [Emulación del GPS](doc/hil_gps_emulacion.md): La emulación del GPS es más compleja que la emulación del radar. Por lo tanto, se dedica una documentación específica para su explicación

**Nota**: Todo este guión está pensado para realizar la comunicación entre una máquina *Ubuntu 24.04.4 LTS* y una *Raspberry Pi 4 Model B* con el [sistema operativo oficial](https://www.raspberrypi.com/documentation/computers/getting-started.html) de esta plataforma.



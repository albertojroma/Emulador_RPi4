import serial
import sys # permite extraer el argumento del terminal

PUERTO = '/dev/ttyUSB0'
BAUD_RATE = 115200
TAMANYO_TRAMA = 6 # Cada trama son 6 bytes
TRAMAS_A_CAPTURAR = 20000
DATOS_A_CAPTURAR = TRAMAS_A_CAPTURAR * TAMANYO_TRAMA

try:
    print(f"Se abre el puerto: \"{PUERTO}\" para captura de datos binarios")
    radar = serial.Serial(PUERTO, BAUD_RATE, timeout=5)
    
    # Leemos un bloque de bytes directos del buffer
    datos_crudos = radar.read(DATOS_A_CAPTURAR)
    
    if (sys.argv[2] == "gps" or sys.argv[2] == "radar"):
        if datos_crudos:
            # Guardamos en un archivo binario (modo 'wb')
            with open("data/" + sys.argv[2] + "/raw/" + sys.argv[1] + ".bin", "wb") as f:
                f.write(datos_crudos)

            print("¡Captura completada con éxito!")
            print(f"Bytes guardados en '{sys.argv[1]}.bin'")
        else:
            print("No se recibieron datos. Revisa la conexión del radar.")
    else:
        print ("El segundo dato tiene que tener el nombre de los directorios ya existentes...")

except Exception as e:
    print(f"Error: {e}")
finally:
    if 'radar' in locals() and radar.is_open:
        radar.close()
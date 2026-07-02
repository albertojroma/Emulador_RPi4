import serial # permite leer el puerto serie
import csv # para crear el archivo .csv
import sys # permite extraer el argumento del terminal
from datetime import datetime # permite anyadir el tiempo 

# Puerto al que esta conectado el radar
PUERTO = 'ttyUSB0'
# Configuracion del puerto
DIR_DISPS = '/dev/' 
BAUD_RATE = 115200       

try:

  radar = serial.Serial(DIR_DISPS + PUERTO, BAUD_RATE, timeout=1)
  
  with open("data/radar/csv_s/" + sys.argv[1] + ".csv", "w", newline='') as archivo_csv:
    fila_csv = csv.writer(archivo_csv)
    
    # Se escriben las cabeceras del .csv
    fila_csv.writerow([
        "Fila", 
        "Tiempo", 
        "Altitud_cm", 
        "SNR", 
        "Checksum_byte", 
        "Validez",
        "Paquete_completo_hex"
    ])
    
    print(f"Conectado a {PUERTO} a {BAUD_RATE} baudios.")
    print("Ctrl+C --> Salir.")
    
    #variable para definir el numero de fila
    fila_actual = 1
    
    while True:
      # La captura comienza cuando se detectan los bytes:
      #* - 0xFE
      #* - 0x02
      header_byte = radar.read(1)
      
      if (header_byte == b'\xfe'): 
        
        version_ID_byte = radar.read(1)

        if (version_ID_byte == b'\x02'):

          data_bytes = radar.read(4)

          if len(data_bytes) == 4:
            altitud_lsb = data_bytes[0]
            altitud_msb = data_bytes[1]
            snr = data_bytes[2]
            checksum_data = data_bytes[3]

            #* --- 1. CÁLCULO CHECKSUM ---
            # checksum = (Version_ID + Altitude_H + Altitude_L + SNR) & 0xFF
            # checksum = 1, check passed
            # checksum = 0, check failed
            checksum_calc = (int.from_bytes(version_ID_byte, "big") + 
                             altitud_msb + 
                             altitud_lsb + 
                             snr) & 0xFF
            es_valido = (checksum_calc == checksum_data)

            #* --- 2. ALTITUD (en cm) ---
            altitud_cm = (altitud_msb << 8) + altitud_lsb

            #* --- 3. RECONSTRUCCIÓN Y GUARDADO ---
            paquete_completo = header_byte + version_ID_byte + data_bytes
            paquete_hex = paquete_completo.hex(' ').upper()

            tiempo = datetime.now().strftime('%H:%M:%S.%f')[:-3]

            #* Se escribe la fila en el .csv
            fila_csv.writerow([
              fila_actual, 
              tiempo, 
              altitud_cm, 
              snr, 
              f"0x{checksum_data:02X}", 
              es_valido,
              paquete_hex
            ])
            archivo_csv.flush() 

            # Mostramos en pantalla con un indicador visual rápido
            estado = "CKSUM_OK" if es_valido else "ERROR_CKSUM"
            print(f"Fila {fila_actual} | "
                  f"Tiempo: {tiempo} | " +
                  f"Altitud (cm): {altitud_cm} | " +
                  f"SNR: {snr} | " +
                  f"[{estado}]")

            fila_actual += 1

# Excepcion que indica si ha habido algun error. Sirve tambien como indicador
# de lo que ha pasado
except serial.SerialException as e:
  print(f"Error de conexión: {e}")
# Excepcion que ocurre al pulsar "Ctrl+C"
except KeyboardInterrupt:
  print("\nDatos almacenados en 'datos_radar.csv'.")
# Para cualquier otra excepción
except Exception as e:
  print("Error:", e)

#* finally se ejecuta siempre, haya excepcion o no
finally:
  if 'radar' in locals() and radar.is_open:
    radar.close()
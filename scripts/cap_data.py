import serial   # permite leer el puerto serie
import csv      # para crear el archivo .csv
import sys      # permite extraer el argumento del terminal
import time     # reloj monótono de alta resolución para medir jitter
from datetime import datetime  # marca de tiempo de calendario, solo informativa

# Puerto al que está conectado el radar
PUERTO = 'ttyUSB0'
# Configuración del puerto
DIR_DISPS = '/dev/'
BAUD_RATE = 115200

try:
    radar = serial.Serial(DIR_DISPS + PUERTO, BAUD_RATE, timeout=1)

    with open("data/radar/csv_s/" + sys.argv[1] + ".csv", "w", newline='') as archivo_csv:
        fila_csv = csv.writer(archivo_csv)

        # Se escriben las cabeceras del .csv
        fila_csv.writerow([
            "Fila",
            "Tiempo_calendario",
            "Timestamp_monotono_s",
            "Intervalo_ms",
            "Altitud_cm",
            "SNR",
            "Checksum_byte",
            "Validez",
            "Paquete_completo_hex"
        ])

        print(f"Conectado a {PUERTO} a {BAUD_RATE} baudios.")
        print("Ctrl+C --> Salir.")

        # Variable para definir el número de fila
        fila_actual = 1
        timestamp_anterior = None  # para calcular el intervalo entre tramas

        while True:
            # La captura comienza cuando se detectan los bytes:
            # * - 0xFE
            # * - 0x02
            header_byte = radar.read(1)

            if header_byte == b'\xfe':

                version_ID_byte = radar.read(1)

                if version_ID_byte == b'\x02':

                    data_bytes = radar.read(4)

                    # El timestamp se captura inmediatamente tras completar
                    # la lectura de la trama
                    timestamp_monotono = time.perf_counter()

                    if len(data_bytes) == 4:
                        altitud_lsb = data_bytes[0]
                        altitud_msb = data_bytes[1]
                        snr = data_bytes[2]
                        checksum_data = data_bytes[3]

                        # --- 1. CÁLCULO CHECKSUM ---
                        # checksum = (Version_ID + Altitude_MSB + Altitude_LSB + SNR) & 0xFF
                        checksum_calc = (int.from_bytes(version_ID_byte, "big") +
                                         altitud_msb +
                                         altitud_lsb +
                                         snr) & 0xFF
                        es_valido = (checksum_calc == checksum_data)

                        # --- 2. ALTITUD (en cm) ---
                        altitud_cm = (altitud_msb << 8) + altitud_lsb

                        # --- 3. INTERVALO ENTRE TRAMAS (jitter) ---
                        if timestamp_anterior is not None:
                            intervalo_ms = (
                                timestamp_monotono - timestamp_anterior) * 1000.0
                        else:
                            intervalo_ms = 0.0  # primera trama, sin referencia previa
                        timestamp_anterior = timestamp_monotono

                        # --- 4. RECONSTRUCCIÓN Y GUARDADO ---
                        paquete_completo = header_byte + version_ID_byte + data_bytes
                        paquete_hex = paquete_completo.hex(' ').upper()

                        tiempo_calendario = datetime.now().strftime(
                            '%H:%M:%S.%f')[:-3]

                        # Se escribe la fila en el .csv
                        fila_csv.writerow([
                            fila_actual,
                            tiempo_calendario,
                            f"{timestamp_monotono:.6f}",
                            f"{intervalo_ms:.3f}",
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
                              f"Tiempo: {tiempo_calendario} | "
                              f"Intervalo: {intervalo_ms:.3f} ms | "
                              f"Altitud (cm): {altitud_cm} | "
                              f"SNR: {snr} | "
                              f"[{estado}]")

                        fila_actual += 1

# Excepción que indica si ha habido algún error. Sirve también como indicador
# de lo que ha pasado
except serial.SerialException as e:
    print(f"Error de conexión: {e}")
# Excepción que ocurre al pulsar "Ctrl+C"
except KeyboardInterrupt:
    print("\nDatos almacenados en 'datos_radar.csv'.")
# Para cualquier otra excepción
except Exception as e:
    print("Error:", e)

# finally se ejecuta siempre, haya excepción o no
finally:
    if 'radar' in locals() and radar.is_open:
        radar.close()

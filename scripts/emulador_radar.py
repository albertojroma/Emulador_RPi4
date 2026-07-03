import serial
import time
import math

# Configuración del puerto de la Raspberry Pi 4 (/dev/serial0)
try:
    ser = serial.Serial('/dev/serial0', 115200, timeout=1)
except serial.SerialException as e:
    print(f"Error crítico abriendo el puerto serie: {e}")
    exit()

def enviar_trama_radar(distancia_m, snr, forzar_error=False):
    """
    Construye y envía la trama binaria estricta de 6 bytes del Ainstein US-D1.
    Formato: [0xFE] [Version] [Alt_LSB] [Alt_MSB] [SNR] [Checksum]
    """
    header = 0xFE
    version = 0x02
    
    if forzar_error:
        header = 0x00 # Provoca un fallo intencionado de sincronismo de cabecera
    
    # Conversión métrica a centímetros para el payload de 16 bits del radar
    distancia_raw = int(distancia_m * 100)
    alt_lsb = distancia_raw & 0xFF
    alt_msb = (distancia_raw >> 8) & 0xFF
    
    # Algoritmo de Checksum: Suma aritmetica de los primeros 5 bytes acotada a 8 bits
    checksum = (version + alt_lsb + alt_msb + snr) & 0xFF
    
    # Empaquetado en array de bytes puros (Formato binario)
    trama = bytearray([header, version, alt_lsb, alt_msb, snr, checksum])
    
    # Transmisión física por el bus
    ser.write(trama)

# --- CONFIGURACIÓN DEL BUCLE DE ALTA PRECISIÓN (100 Hz) ---
frecuencia = 100.0  
intervalo = 1.0 / frecuencia  # 10 milisegundos
proxima_ejecucion = time.perf_counter() + intervalo

print("====================================================")
print(" Emulador HIL - Radar Ainstein US-D1 (100 Hz) Activo")
print(" Transmitiendo en UART0: GPIO 0 (Pin 8)")
print("====================================================")

try:
    while True:
        t_actual = time.perf_counter()
        
        # Perfil de vuelo simulado: Oscilación sinusoidal entre 2 y 8 metros
        altitud_simulada = 5.0 + 3.0 * math.sin(t_actual * 0.5)
        snr_simulado = 35.0 + 5.0 * math.sin(t_actual * 0.5)
        
        # INTERFAZ DE INYECCIÓN DE FALLOS (Test de Robustez)
        # Cada ciclo de 30 segundos, durante 3 segundos se corrompe la cabecera
        #segundo_actual = int(t_actual) % 30
        error_activo = 0#(15 <= segundo_actual <= 18)
        
        if error_activo:
            enviar_trama_radar(altitud_simulada, snr=0, forzar_error=True)
        else:
            enviar_trama_radar(altitud_simulada, int(snr_simulado), forzar_error=False)
            
        # Control estricto del jitter del kernel de Linux
        tiempo_espera = proxima_ejecucion - time.perf_counter()
        if tiempo_espera > 0:
            time.sleep(tiempo_espera)
        
        proxima_ejecucion += intervalo

except KeyboardInterrupt:
    print("\n[INFO] Deteniendo emulador HIL...")
    ser.close()
    print("[OK] Puerto serie /dev/serial0 cerrado correctamente.")

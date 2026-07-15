"""
@file emulador_gps_NEW.py
@brief Emulador HIL de un receptor GNSS u-blox ZED-F9P sobre puerto serie.

@details
Ejecutado en la Raspberry Pi 4 y conectado por UART a la Teensy 4.1. Inicia con la configuracion de fabrica para los mensajes de salida (solo NMEA, UBX desactivado, 38400 baudios), atiende peticiones UBX-CFG-VALSET/VALGET de la Teensy, y emite UBX-RXM-RAWX y UBX-RXM-SFRBX sinteticas una vez configurado. RAWX+SFRBX ya aportan observables crudas + efemerides. Parte del HIL esta documentado en hil_gps_emulacion.md.

@note 
Hay que destacar varios aspectos a la hora de formar paquetes:
1. Se usa `struct.pack(formato, v1, v2 ...)`. La informacion esta en https://docs.python.org/3/library/struct.html.
2. Las referencias en este documento pueden ser principalmente a 2 documentos (si hay más referencias se especifica el enlace):
  * u-blox F9 HPG 1.51 Interface Description: https://content.u-blox.com/sites/default/files/documents/u-blox-F9-HPG-1.51_InterfaceDescription_UBXDOC-963802114-13124.pdf
  * "ZED-F9P Integration manual": https://content.u-blox.com/sites/default/files/ZED-F9P_IntegrationManual_UBX-18010802.pdf 
3. El campo `version` de cada tipo de paquete siempre tiene un valor fijo. Este esta especificado en el documento "Interface Description" de u-blox.
4. Los campos `reservedX`, como son mensajes de salida da igual que valor tengan (ver 3.3.2 del "Interface Description" de u-blox).
5. Los tipos de datos UBX estan especificados en el apartado 3.3.5 del "Interface Description" de u-blox.
"""
import serial
import time
import struct
import argparse
import threading


#*==============================================================================
#*                  Configuracion de argumentos y puerto serie
#*==============================================================================

# --puerto: UART3 de la RPi4 (/dev/ttyAMA1). 
# --baudrate_inicial: 38400, baudrate de fabrica (Integration Manual, apartado 3.1.3, p. 13).
# --num_sats: satelites simulados en RAWX/SFRBX.
parser = argparse.ArgumentParser(description="Emulador HIL - GPS UBX (ZED-F9P) con handshake de configuración")
parser.add_argument("--puerto", default="/dev/ttyAMA1")
parser.add_argument("--baudrate_inicial", type=int, default=38400,
                     help="Baud rate de arranque, replicando el comportamiento real de fábrica del ZED-F9P")
parser.add_argument("--num_sats", type=int, default=10)
args = parser.parse_args()

try:
    ser = serial.Serial(args.puerto, args.baudrate_inicial, timeout=0.05)
except serial.SerialException as e:
    print(f"Error crítico abriendo el puerto serie: {e}")
    exit()


#*==============================================================================
#*                            Valores de tramas
#*==============================================================================

# Numero de bytes hasta el payload (Apartado 3.2 "Interface Description")
bytes_PrePayload = 6

#* ----------------------- PREAMBLES, CLASSES & IDs ----------------------------

# Preamble sync characters (Apartado 3.2 "Interface Description")
UBX_SYNC1, UBX_SYNC2 = 0xB5, 0x62
# UBX-RXM (Apartado 3.17 "Interface Description")
CLASS_RXM, ID_RAWX, ID_SFRBX  = 0x02, 0x15, 0x13
# UBX-CFG (Apartado 3.10 "Interface Description") 
CLASS_CFG, ID_VALSET = 0x06, 0x8A
CLASS_CFG_GET, ID_VALGET = 0x06, 0x8B
# UBX_ACK (Apartado 3.9 "Interface Description")
CLASS_ACK, ID_ACK, ID_NAK = 0x05, 0x01, 0x00

#* ---------------- "Key IDs" de mensajes de configuracion ---------------------

# Tabla 87 y 19 de "u-blox F9 HPG 1.51 Interface Description"
KEY_MSGOUT_RXM_RAWX_UART1 = 0x209102A5
KEY_MSGOUT_RXM_SFRBX_UART1 = 0x20910232
# Tabla 61 y 107 "u-blox F9 HPG 1.51 Interface Description"
KEY_UART1_BAUDRATE        = 0x40520001

# diccionario de tamanyo en bytes de cada valor de configuracion
TAMANYO_VALOR = {
    KEY_MSGOUT_RXM_RAWX_UART1:  1,  # U1: 1 byte unsigned
    KEY_MSGOUT_RXM_SFRBX_UART1: 1,  # U1: 1 byte unsigned
    KEY_UART1_BAUDRATE:         4,  # U4: 4 bytes unsigned
}

#* ------------------ Estado de configuracion del emulador ---------------------

#* Estos diccionarios son recursos compartidos gestinado por un mutex
# Por defecto, replica el comportamiento de fabrica.
estado_config = {
    "rawx_activo": False,
    "sfrbx_activo": False,
    "baudrate_actual": args.baudrate_inicial,
}
solicitud_cambio_baud = {"pendiente": False, "nuevo_valor": None}

# protege estado_config entre hilo_escucha_configuracion() y el bucle principal
lock_estado = threading.Lock()  



#*==============================================================================
#*                                  Funciones
#*==============================================================================

#* ------------------------- Construccion de tramas ----------------------------

def construir_rawx(rcv_tow, week, num_meas):
    """
    @brief Construye el payload de UBX-RXM-RAWX: cabecera de 16 bytes + num_meas bloques de 32 bytes.
    @param rcv_tow Tiempo de recepcion (s, GPS), campo rcvTow.
    @param week Semana GPS.
    @param num_meas Numero de senyales simuladas (numMeas), un bloque de 32 bytes cada una.
    @return bytes: payload completo, listo para construir_trama_ubx().
    @details Estructura definida en "u-blox F9 HPG 1.51 Interface Description", apartado 3.17.6.
    @note Los valores de prMes/cpMes son sinteticos (formula lineal, no
    geometria satelital real): validos para probar el parser del firmware,
    no para un post-proceso PPK real con RTKLIB (ver hil_gps_emulacion.md,
    apartado 2.5).
    """
    # leapS: desfase GPS-UTC vigente (https://www.mobatime.com/es/tecnologia/comprender-la-diferencia-entre-utc-y-gps-para-la-sincronizacion-horaria/)
    leapS     = 18
    # recStat: 
        # bit 0 (leapSec): indica si `leapS` se ha definido
        # bit 1 (clkReset): indica que se ha aplicado un reset al reloj
    recStat   = 0x01 
    version   = 0x01 
    reserved0 = 0x0000

    # La cabecera tiene un tamanyo de 16 bytes
    cabecera = struct.pack(
        '<dHbBBBH', # Se indica que el orden es "little-endian" '<' y como 
                    # interpretar cada argumento
        rcv_tow,  # R8: d (double --> 8 bytes)
        week,     # U2: H (unsigned short --> 2 bytes)
        leapS,    # I1: b (signed char --> 1 byte)
        num_meas, # U1: B (unsigned char --> 1 byte)
        recStat,  # X1: B (unsigned char --> 1 byte)
        version,  # U1: B (unsigned char --> 1 byte)
        reserved0 # U1[2]: H (unsigned char --> 2 bytes)
    )

    bloques = b''
    for i in range(num_meas):
        # Medida del pseudorango (Distancia) en m. En este caso > 22000 Km 
        # ("i * 1000.0" para que haya variacion)
        prMes = 2.2e7 + i * 1000.0
        # Fase de la portadora (ciclos) = distancia / longitud de onda L1 C/A
        cpMes = prMes / 0.1902937
        # Medida doppler (Hz)
        doMes = 0.0
        # Identificador gnss
        gnssId = 0
        # Identificador de satelite
        svId = i + 1
        # Identificador de senyal 
        sigId = 0
        # Solo para GLONASS (slot de frecuencia + 7). De 0-13
        freqId = 0
        # Timeout de fase de la portadora (ms). Maximo de 64500 ms
        locktime = 5000
        # SNR (dBHz) de una senyal medianamente buena
        cno = 35 + (i % 5)
        prStdev = 2
        cpStdev = 4
        doStdev = 2
        # Bits de estado de seguimiento
            # bit 0 (prValid): 1 => validez del pseudorango/distancia
            # bit 1 (cpValid): 1 => validez de la fase de la portadora    
            # bit 2 (halfCyc): 1 => validez de medio ciclo
            # bit 3 (subHalfCyc): 1 => validez de medio ciclo extraido de la fase   
        trkStat = 0x0F
        reserved1 = 0x00
        

        bloque = struct.pack(
            '<ddfBBBBHBBBBBB', # '<' => "little-endian" 
            prMes,    # R8: d (double --> 8 bytes)
            cpMes,    # R8: d (double --> 8 bytes)
            doMes,    # R4: f (float --> 4 bytes)
            gnssId,   # U1: B (unsigned char --> 1 byte)
            svId,     # U1: B (unsigned char --> 1 byte)
            sigId,    # U1: B (unsigned char --> 1 byte) 
            freqId,   # U1: B (unsigned char --> 1 byte)
            locktime, # U2: H (unsigned short --> 2 bytes)
            cno,      # U1: B (unsigned char --> 1 byte)
            prStdev,  # X1: B (unsigned char --> 1 byte)
            cpStdev,  # X1: B (unsigned char --> 1 byte)
            doStdev,  # X1: B (unsigned char --> 1 byte)
            trkStat,  # X1: B (unsigned char --> 1 byte)
            reserved1 # U1: B (unsigned char --> 1 byte)
        )
        bloques += bloque

    return cabecera + bloques

def construir_sfrbx(gnssId, svId, sigId, freqId, num_words=8):
    """
    @brief Construye el payload de UBX-RXM-SFRBX: cabecera de 8 bytes + num_words palabras de 4 bytes.
    @param gnssId, svId, sigId, freqId Identificadores de la señal simulada.
    @param num_words Numero de palabras de subtrama (dwrd) a generar.
    @return bytes: payload completo, listo para construir_trama_ubx().
    @details Estructura definida en "u-blox F9 HPG 1.51 Interface Description", apartado 3.17.9, p. 201.
    @note 'dwrd' es sintetico. Sirve para validar que el firmware parsea correctamente un numero variable de palabras segun 'numWords', no para post-proceso PPK (ver hil_gps_emulacion.md, apartado 2.5).
    """
    #todo Buscar otra forma de generar ese valor con mas sentido
    # Canal en el que se recibio el mensaje. Para que vaya variando se asigna la operacion de modulo de forma arbitraria.
    chn       = svId % 32
    version   = 0x02 
    reserved0 = 0x00

    cabecera = struct.pack(
        '<BBBBBBBB', # '<' => "little-endian" 
        gnssId,      # U1: B (unsigned char --> 1 byte)
        svId,        # U1: B (unsigned char --> 1 byte)
        sigId,       # U1: B (unsigned char --> 1 byte)
        freqId,      # U1: B (unsigned char --> 1 byte)
        num_words,   # U1: B (unsigned char --> 1 byte)
        chn,         # U1: B (unsigned char --> 1 byte)
        version,     # U1: B (unsigned char --> 1 byte)
        reserved0    # U1: B (unsigned char --> 1 byte)
    )
    
    # Palabras de datos de la trama. Se asigna un dato inventado reconocible
    dwrd = b''.join(struct.pack('<I',          # '<' => "little-endian" 
                                0xABCD0000+i # U4: I (unsigned int --> 4 bytes)
            ) for i in range(num_words))
    return cabecera + dwrd

def checksum_ubx(datos):
    """
    @brief Calcula el checksum de 2 bytes (CK_A, CK_B) de una trama UBX.
    @param datos bytes sobre los que calcular el checksum (Class+ID+Length+Payload).
    @return tuple(int, int): (CK_A, CK_B).
    @details El algoritmo de checksum usado es el Fletcher de 8 bits. Definido en "u-blox F9 HPG 1.51 Interface Description", apartado 3.4
    """
    ck_a = ck_b = 0 # U1
    for b in datos:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return ck_a, ck_b

def construir_trama_ubx(msg_class, msg_id, payload):
    """
    @brief Genera trama UBX completa (sync + cabecera + payload + checksum).
    @param msg_class Campo `Class` del mensaje UBX.
    @param msg_id Campo `ID` del mensaje UBX.
    @param payload bytes del cuerpo del mensaje.
    @return bytes: trama UBX completa (Preamble+class+ID+Length+Payload+Checksum), lista para enviar por el puerto serie.
    """
    # Se convierte a bytes `class` y `ID` y se concatena (como objeto de tipo 
    # byte) con el campo `Length`. Este campo es tipo U2
    cabecera = bytes([msg_class, msg_id]) + struct.pack('<H', len(payload))
    cuerpo = cabecera + payload
    ck_a, ck_b = checksum_ubx(cuerpo)
    return bytes([UBX_SYNC1, UBX_SYNC2]) + cuerpo + bytes([ck_a, ck_b])

def enviar_ack(clsID, msgID, positivo=True):
    """
    @brief Envia UBX-ACK-ACK o UBX-ACK-NAK confirmando/rechazando un mensaje recibido.
    @param clsID Identificador de clase del mensaje que se quiere confirmar
    @param msgID Identificador del mensaje que se quiere confirmar
    @param positivo True para ACK, False para NAK.
    @details Estructura definida en "u-blox F9 HPG 1.51 Interface Description", apartado 3.9
    """
    payload = bytes([clsID, msgID])
    trama = construir_trama_ubx(CLASS_ACK, ID_ACK if positivo else ID_NAK, payload)
    ser.write(trama)

def procesar_valset(payload):
    """
    @brief Analiza el payload para comprobar si es UBX-CFG-VALSET y actualiza estado_config en consecuencia.
    @param payload bytes del `payload` del mensaje (version+layers+reserved0+cfgData).
    @return bool: True si se proceso correctamente; False si el payload es invalido (< 4 bytes).
    @details Estructura definida en "u-blox F9 HPG 1.51 Interface Description", apartado 3.10.25
    @note Recorre los pares (keyID, valor) del payload; una keyID no reconocida
    en TAMANYO_VALOR corta el procesado del resto del mensaje, al no poder
    saber cuantos bytes ocupa su valor.
    """
    # La cabecera minima (version+layers+reserved) ya ocupa 4 bytes
    if len(payload) < 4:
        return False

    # Puntero de lectura. Empieza despues del 4 byte. A partir de aqui empiezan 
    # los pares (keyID, valor).
    idx = 4
    
     # Se repite mientras queden al menos 4 bytes sin leer
    while idx + 4 <= len(payload):

        # Lee los 4 bytes en la posicion actual y los interpreta como
        # un entero de 32 bits sin signo, little-endian ('<I').
        key_id = struct.unpack('<I', payload[idx:idx+4])[0]

        # Avanza el puntero el tamanyo fijo de los keyID (4 bytes)
        idx += 4

        # Busca el numero de bytes que ocupa el valor de la clave recibida
        tam = TAMANYO_VALOR.get(key_id)

        # Se comprueba si la clave no esta en el diccionario TAMANYO_VALOR
        if tam is None:
            # Si la clave no esta => Se identifica que se ha recibido y se sale # de la funcion devolviendo `False`
            print(f"[AVISO] KeyID desconocido 0x{key_id:08X}, ignorando resto de VALSET.")
            return False

        # Se extraen los datos de la clave asociada 
        valor_bytes = payload[idx:idx+tam]
        
        # Avanza el puntero (donde empezaria la siguiente keyID)
        idx += tam

        # Adquiere el candado (mutex) para acceder a estado_config sin que el
        # otro hilo lo modifique a la vez; se libera solo al salir del bloque.
        with lock_estado:

            if key_id == KEY_MSGOUT_RXM_RAWX_UART1:
                estado_config["rawx_activo"] = (valor_bytes[0] > 0)
                # valor_bytes tiene 1 byte aqui (tam=1); > 0 -> activado.
                print(f"[CFG] RXM-RAWX {'activado' if estado_config['rawx_activo'] else 'desactivado'}")

            elif key_id == KEY_MSGOUT_RXM_SFRBX_UART1:
                estado_config["sfrbx_activo"] = (valor_bytes[0] > 0)
                # Misma logica que RAWX, para la clave de SFRBX.
                print(f"[CFG] RXM-SFRBX {'activado' if estado_config['sfrbx_activo'] else 'desactivado'}")

            elif key_id == KEY_UART1_BAUDRATE:
                # Valor de 4 bytes => se reinterpreta
                nuevo_baud = struct.unpack('<I', valor_bytes)[0]
                print(f"[CFG] Solicitud de cambio de baud rate a {nuevo_baud}")
                solicitud_cambio_baud["pendiente"] = True
                solicitud_cambio_baud["nuevo_valor"] = nuevo_baud
                # No se aplica el baudrate inmediatamente. Se aplica despues de 
                # enviar el ACK porque se tiene que confirmar el baudrate 
                # antiguo

    return True

def valor_actual_clave(key_id):
    """
    @brief Devuelve el valor binario UBX actualmente activo de una keyID.
    @param key_id Clave de configuracion consultada.
    @return bytes con el valor, o None si la clave no esta en TAMANYO_VALOR.
    @details Se asume equivalente a la capa RAM (u-blox, Interface
    Description citado en construir_rawx(), apartado 6.3, p. 244): es el
    valor que "veria" un CFG-VALGET con layer=RAM en el receptor real, la
    capa relevante para que la Teensy decida si necesita reconfigurar.
    """
    with lock_estado:
        if key_id == KEY_MSGOUT_RXM_RAWX_UART1:
            return bytes([1 if estado_config["rawx_activo"] else 0])
        elif key_id == KEY_MSGOUT_RXM_SFRBX_UART1:
            return bytes([1 if estado_config["sfrbx_activo"] else 0])
        elif key_id == KEY_UART1_BAUDRATE:
            return struct.pack('<I', estado_config["baudrate_actual"])
    return None

def procesar_valget(payload):
    """
    @brief Analiza una trama UBX-CFG-VALGET (peticion) y construye su respuesta.
    @param payload bytes del payload de la peticion (version+layer+position+keys[]).
    @return bytes con el payload de respuesta, o None si hay una keyID desconocida o el payload es invalido.
    @details Definido en "u-blox F9 HPG 1.51 Interface Description", apartado 3.10.24
    """
    # La cabecera minima (version+layers+position) ya ocupa 4 bytes
    if len(payload) < 4:
        # trama mal formada -> se responderá con NAK
        return None  

    # El byte 1 del payload corresponde a la capa de configuracion y puede 
    # tener los siguiente valores:
      # 0 - RAM layer
      # 1 - BBR 
      # 2 - Flash
      # 7 - Default
    layer = payload[1]
    # Los 2 siguientes bytes corresponden al numero de elementos de 
    # configuracion omitidos en los resultados antes de generar el mensaje
    # Tipo U2
    position = struct.unpack('<H', payload[2:4])[0]
    
    # Puntero de lectura. Empieza despues del 4 byte. A partir de aqui empiezan 
    # los pares (keyID, valor).
    idx = 4
    
    # Se define la variable como objeto de bytes. Tipo U1.
    cfgData = b''

    while idx + 4 <= len(payload):
        
        # Lee los 4 bytes en la posicion actual y los interpreta como un entero 
        # de 32 bits sin signo, little-endian ('<I').
        key_id = struct.unpack('<I', payload[idx:idx+4])[0]
        
        # Avanza el puntero el tamanyo fijo de los keyID (4 bytes)
        idx += 4

        # Se comprueba que valor tiene la keyID recibida 
        valor = valor_actual_clave(key_id)
        
        if valor is None:
            # KeyID no reconocido por este emulador
            print(f"[AVISO] VALGET solicita KeyID desconocido 0x{key_id:08X}")
            return None
        
        # Empaqueta en `cfgData` el keyID+valor_acual
        cfgData += struct.pack('<I', key_id) + valor

    # version=0x01 (respuesta), se ecoa la capa y la posición solicitadas
    respuesta_payload = bytes([0x01, layer]) + struct.pack('<H', position) + cfgData
    return respuesta_payload

def hilo_escucha_configuracion():
    """
    @brief Hilo que escucha el puerto serie y procesa peticiones de configuracion.
    @details Se ejecuta en paralelo al bucle principal de emision (ver el bloque try/while final del fichero): mientras este hilo atiende UBX-CFG-VALSET/VALGET entrantes, el bucle principal emite RAWX/SFRBX -- replica que un receptor real atiende configuracion y datos de forma concurrente. Reensambla tramas UBX byte a byte desde un buffer acumulado (los datos pueden llegar fragmentados entre llamadas a ser.read()), verifica el checksum, y despacha VALSET/VALGET al parser correspondiente.
    """
    
    buffer = bytearray()
    while True:
        try:
            #todo averiguar el tamanyo maximo de las tramas que se pueden recibir
            datos = ser.read(64)
        except serial.SerialException:
            break
        if datos:
            buffer.extend(datos)

        # Búsqueda de tramas UBX completas dentro del buffer acumulado
        while True:
            # Se busca la posicion de los preambulos 0xB562 de las tramas UBX
            idx_sync = buffer.find(bytes([UBX_SYNC1, UBX_SYNC2]))
            
            #todo Terminar de decidir si lo de < 8 es valido
            # Si el indice es -1 o el tamanyo del buffer - indice es menor a 8 
            # se sale del bucle
            if idx_sync == -1 or len(buffer) - idx_sync < 8:
                break
            
            # Si el indice es > a 0 se limpia lo que haya antes del indice
            if idx_sync > 0:
                del buffer[:idx_sync]

            # todo Averiguar si tengo que borrar esta trama
            # Si el tamanyo es menor a 6 se sale del bucle
            if len(buffer) < bytes_PrePayload:
                break
            
            # Localizados los preambulos, se identifica la clase e 
            # identificador recibidos asi como la ongitud
            msg_class, msg_id = buffer[2], buffer[3]
            length = struct.unpack('<H', buffer[4:6])[0]
            
            # Trama = 6 bytes antes de Payload + N bytes Payload + 2 bytes de checksum 
            trama_total = bytes_PrePayload + length + 2

            # Si la trama esta incompleta se sale del bucle
            if len(buffer) < trama_total:
                break  # trama incompleta, esperar más bytes

            payload = bytes(buffer[6:6+length])
            
            ck_a_calc, ck_b_calc = checksum_ubx(buffer[2:6+length])
            ck_a_rx, ck_b_rx = buffer[6+length], buffer[7+length]
            # Se comprueba si el checksum es correcto
            if ck_a_calc == ck_a_rx and ck_b_calc == ck_b_rx:
                # Se comprueba que mensaje se ha recibido. En este emulador 
                # solo hay 2 posibilidades: UBX-CFG-VALSET o UBX-CFG-VALGET
                if msg_class == CLASS_CFG and msg_id == ID_VALSET:
                    # ok = procesar_valset(payload)
                    enviar_ack(msg_class, msg_id, positivo=procesar_valset(payload))

                    # El cambio de baud rate se aplica DESPUÉS de enviar el ACK,
                    # replicando el comportamiento real: el receptor confirma
                    # con el baud rate antiguo antes de cambiar.
                    if solicitud_cambio_baud["pendiente"]:
                        # margen arbitrario para que el ACK salga por el puerto
                        time.sleep(0.05)
                        
                        # Se toma el mutex
                        with lock_estado:
                            # Se extrae el nuevo baudrate
                            nuevo_baudrate = solicitud_cambio_baud["nuevo_valor"]
                            # Se asigna el nuevo baudrate
                            estado_config["baudrate_actual"] = nuevo_baudrate
                            # Se confirma el cambio
                            solicitud_cambio_baud["pendiente"] = False
                        ser.baudrate = nuevo_baudrate
                        print(f"[CFG] Baud rate del emulador conmutado a {nuevo_baudrate}")

                elif msg_class == CLASS_CFG_GET and msg_id == ID_VALGET:
                    respuesta = procesar_valget(payload)
                    if respuesta is not None:
                        # Se envia la configuracion del gps emulado
                        ser.write(construir_trama_ubx(CLASS_CFG_GET, ID_VALGET, respuesta))
                        print("[CFG] VALGET respondido")
                    else:
                        enviar_ack(msg_class, msg_id, positivo=False)
            else:
                enviar_ack(msg_class, msg_id, positivo=False)
            
            # Se elimina el contenido del buffer porque ya se ha procesado
            del buffer[:trama_total]

#*==============================================================================
#*                            Ejecucion del script
#*==============================================================================

#* ------ Lanzamiento del hilo de escucha en paralelo al bucle de emision ------
hilo = threading.Thread(target=hilo_escucha_configuracion, daemon=True)
hilo.start()

#* -------------------------- Mensaje del terminal -----------------------------
print("=======================================================================")
print("      Emulador HIL - GPS ZED-F9P con handshake de configuración        ")
print(f"       Inicio: {args.baudrate_inicial} baud, UBX desactivado          ")
print("=======================================================================")

# t_inicio con perf_counter() en vez de time().
t_inicio = time.perf_counter()
# datos inventados
semana_gps = 2320
itow_inicial_ms = 300_000_000
#todo habria que tener en cuenta tambien el tema de que el gps tarda en arrancar, y cuando se alimente el sistema todo se va a alimentar a la vez pero el gps tarda un tiempo en tomar bien los datos si no estoy equivocado


try:
    while True:
        t_actual = time.perf_counter()
        t_transcurrido = t_actual - t_inicio
        itow_actual = itow_inicial_ms + int(t_transcurrido * 1000)

        # Se toman los valores que definen el estado de la configuracion a 
        # traves de un mutex/candado
        with lock_estado:
            rawx_activo = estado_config["rawx_activo"]
            sfrbx_activo = estado_config["sfrbx_activo"]

        if rawx_activo:
            payload_rawx = construir_rawx(itow_actual / 1000.0, semana_gps, args.num_sats)
            # Se envia la trama construida
            ser.write(construir_trama_ubx(CLASS_RXM, ID_RAWX, payload_rawx))

        if sfrbx_activo:
            # Una trama SFRBX por satélite simulado, replicando que cada subtrama de navegación procede de una única señal (a diferencia de RAWX, que agrupa todas las señales en un solo mensaje). 
            # Simplificación de la emulación: en el receptor real, las subtramas llegan a un ritmo mucho más lento que la tasa de navegación (segundos, no cada época); aquí se emiten a la misma cadencia que RAWX por simplicidad, suficiente para validar el parseo del firmware (ver apartado 2.5 del documento).
            for i in range(args.num_sats):
                payload_sfrbx = construir_sfrbx(gnssId=0, svId=i + 1, sigId=0, freqId=0, num_words=8)
                ser.write(construir_trama_ubx(CLASS_RXM, ID_SFRBX, payload_sfrbx))

        if not rawx_activo and not sfrbx_activo:
            # Comportamiento de fábrica: emisión de NMEA simulado a baja frecuencia,
            # útil para validar que el firmware ignora correctamente tramas no-UBX
            # mientras espera a que su propia secuencia de configuración surta efecto.
            ser.write(b"$GPGGA,120000.00,,,,,0,00,99.99,,,,,,*76\r\n")

        # tasa de emision de 5 Hz una vez configurado
        # @todo: justificar por que 5 Hz concretamente (no 1 Hz, 10 Hz...)
        time.sleep(0.2)

except KeyboardInterrupt:
    print("\n[INFO] Deteniendo emulador GPS...")
    ser.close()
import serial
import time
import math
import struct
import argparse
import threading

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

UBX_SYNC1, UBX_SYNC2 = 0xB5, 0x62
CLASS_NAV, ID_PVT = 0x01, 0x07
CLASS_RXM, ID_RAWX = 0x02, 0x15
CLASS_CFG, ID_VALSET = 0x06, 0x8A
CLASS_ACK, ID_ACK, ID_NAK = 0x05, 0x01, 0x00

# --- Tabla de keyID relevantes (limitada a lo que el firmware real va a enviar) ---
KEY_MSGOUT_NAV_PVT_UART1  = 0x20910007
KEY_MSGOUT_RXM_RAWX_UART1 = 0x209102A5
KEY_UART1_BAUDRATE        = 0x40520001

TAMANO_VALOR = {
    KEY_MSGOUT_NAV_PVT_UART1:  1,  # U1
    KEY_MSGOUT_RXM_RAWX_UART1: 1,  # U1
    KEY_UART1_BAUDRATE:        4,  # U4
}

# --- Estado interno de configuración del "receptor" emulado ---
# Por defecto, replica el comportamiento real de fábrica: NAV-PVT y RAWX desactivados
estado_config = {
    "nav_pvt_activo": False,
    "rawx_activo": False,
    "baudrate_actual": args.baudrate_inicial,
}
lock_estado = threading.Lock()
solicitud_cambio_baud = {"pendiente": False, "nuevo_valor": None}

def construir_nav_pvt(itow_ms, lat_deg, lon_deg, height_m, fix_type=3, num_sv=10):
    """
    Payload EXACTO de 92 bytes de UBX-NAV-PVT, offsets verificados contra el
    Interface Description de u-blox (receptores serie 8/9).
    """
    year, month, day, hour, minute, sec = 2026, 7, 3, 12, 0, 0
    valid_flags = 0x07
    t_acc = 20
    nano = 0
    flags = 0xC1 if fix_type >= 4 else 0x01
    flags2 = 0x00
    lon_scaled = int(lon_deg * 1e7)
    lat_scaled = int(lat_deg * 1e7)
    height_mm = int(height_m * 1000)
    h_msl_mm = height_mm - 40000
    h_acc, v_acc = 15, 20
    vel_n = vel_e = vel_d = 0
    g_speed = 0
    head_mot = 0
    s_acc = 500
    head_acc = 1800000
    p_dop = 120
    flags3 = 0x00
    reserved1 = b'\x00' * 5
    head_veh = 0
    mag_dec = 0
    mag_acc = 0

    payload = struct.pack(
        '<IHBBBBBBIiBBBBiiiiIIiiiiIIHB5sihH',
        itow_ms, year, month, day, hour, minute, sec, valid_flags,
        t_acc, nano,
        fix_type, flags, flags2, num_sv,
        lon_scaled, lat_scaled, height_mm, h_msl_mm,
        h_acc, v_acc,
        vel_n, vel_e, vel_d, g_speed, head_mot,
        s_acc, head_acc,
        p_dop, flags3, reserved1,
        head_veh, mag_dec, mag_acc
    )
    assert len(payload) == 92, f"Payload NAV-PVT mal formado: {len(payload)} bytes (esperados 92)"
    return payload


def construir_rawx(rcv_tow, week, num_meas):
    """
    Payload simplificado de UBX-RXM-RAWX: cabecera fija (16 bytes) +
    N bloques de 32 bytes (uno por satélite simulado).
    """
    leap_s = 18
    rec_status = 0x01
    version = 0x01

    cabecera = struct.pack(
        '<dHbBBBH',
        rcv_tow, week, leap_s, num_meas, rec_status, version, 0
    )

    bloques = b''
    for i in range(num_meas):
        gnss_id = 0
        sv_id = i + 1
        sig_id = 0
        freq_id = 0
        pr_mes = 2.2e7 + i * 1000.0
        cp_mes = pr_mes / 0.1902937
        do_mes = 0.0
        locktime = 5000
        cno = 35 + (i % 5)
        pr_std = 2
        cp_std = 4
        do_std = 2
        trk_stat = 0x0F

        bloque = struct.pack(
            '<ddfBBBBHBBBBBB',
            pr_mes, cp_mes, do_mes,
            gnss_id, sv_id, sig_id, freq_id,
            locktime, cno,
            pr_std, cp_std, do_std,
            trk_stat, 0
        )
        bloques += bloque

    return cabecera + bloques

def checksum_ubx(datos):
    ck_a = ck_b = 0
    for b in datos:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return ck_a, ck_b

def construir_trama_ubx(msg_class, msg_id, payload):
    cabecera = bytes([msg_class, msg_id]) + struct.pack('<H', len(payload))
    cuerpo = cabecera + payload
    ck_a, ck_b = checksum_ubx(cuerpo)
    return bytes([UBX_SYNC1, UBX_SYNC2]) + cuerpo + bytes([ck_a, ck_b])

def enviar_ack(msg_id_confirmado_class, msg_id_confirmado_id, positivo=True):
    payload = bytes([msg_id_confirmado_class, msg_id_confirmado_id])
    trama = construir_trama_ubx(CLASS_ACK, ID_ACK if positivo else ID_NAK, payload)
    ser.write(trama)

def procesar_valset(payload):
    """
    Parsea un UBX-CFG-VALSET y actualiza el estado interno del emulador,
    replicando el efecto que tendría sobre un ZED-F9P real.
    """
    if len(payload) < 4:
        return False
    version, layers = payload[0], payload[1]
    idx = 4  # tras version(1) + layers(1) + reserved(2)

    while idx + 4 <= len(payload):
        key_id = struct.unpack('<I', payload[idx:idx+4])[0]
        idx += 4
        tam = TAMANO_VALOR.get(key_id)
        if tam is None:
            # KeyID no reconocido por este emulador simplificado: se descarta
            # el resto del mensaje, ya que no sabemos su longitud de valor.
            print(f"[AVISO] KeyID desconocido 0x{key_id:08X}, ignorando resto de VALSET.")
            break

        valor_bytes = payload[idx:idx+tam]
        idx += tam

        with lock_estado:
            if key_id == KEY_MSGOUT_NAV_PVT_UART1:
                estado_config["nav_pvt_activo"] = (valor_bytes[0] > 0)
                print(f"[CFG] NAV-PVT {'activado' if estado_config['nav_pvt_activo'] else 'desactivado'}")
            elif key_id == KEY_MSGOUT_RXM_RAWX_UART1:
                estado_config["rawx_activo"] = (valor_bytes[0] > 0)
                print(f"[CFG] RXM-RAWX {'activado' if estado_config['rawx_activo'] else 'desactivado'}")
            elif key_id == KEY_UART1_BAUDRATE:
                nuevo_baud = struct.unpack('<I', valor_bytes)[0]
                print(f"[CFG] Solicitud de cambio de baud rate a {nuevo_baud}")
                solicitud_cambio_baud["pendiente"] = True
                solicitud_cambio_baud["nuevo_valor"] = nuevo_baud

    return True

def hilo_escucha_configuracion():
    """
    Hilo dedicado a escuchar la UART en busca de comandos UBX-CFG-VALSET
    enviados por la Teensy, replicando el comportamiento de un receptor
    real que atiende configuración y datos de forma concurrente.
    """
    buffer = bytearray()
    while True:
        try:
            datos = ser.read(64)
        except serial.SerialException:
            break
        if datos:
            buffer.extend(datos)

        # Búsqueda de tramas UBX completas dentro del buffer acumulado
        while True:
            idx_sync = buffer.find(bytes([UBX_SYNC1, UBX_SYNC2]))
            if idx_sync == -1 or len(buffer) - idx_sync < 8:
                break
            if idx_sync > 0:
                del buffer[:idx_sync]

            if len(buffer) < 6:
                break
            msg_class, msg_id = buffer[2], buffer[3]
            length = struct.unpack('<H', buffer[4:6])[0]
            trama_total = 6 + length + 2

            if len(buffer) < trama_total:
                break  # trama incompleta, esperar más bytes

            payload = bytes(buffer[6:6+length])
            ck_a_calc, ck_b_calc = checksum_ubx(buffer[2:6+length])
            ck_a_rx, ck_b_rx = buffer[6+length], buffer[7+length]

            if ck_a_calc == ck_a_rx and ck_b_calc == ck_b_rx:
                if msg_class == CLASS_CFG and msg_id == ID_VALSET:
                    ok = procesar_valset(payload)
                    enviar_ack(msg_class, msg_id, positivo=ok)

                    # El cambio de baud rate se aplica DESPUÉS de enviar el ACK,
                    # replicando el comportamiento real: el receptor confirma
                    # con el baud rate antiguo antes de conmutar.
                    if solicitud_cambio_baud["pendiente"]:
                        time.sleep(0.05)  # margen para que el ACK salga por el puerto
                        with lock_estado:
                            nuevo = solicitud_cambio_baud["nuevo_valor"]
                            estado_config["baudrate_actual"] = nuevo
                            solicitud_cambio_baud["pendiente"] = False
                        ser.baudrate = nuevo
                        print(f"[CFG] Baud rate del emulador conmutado a {nuevo}")
            else:
                enviar_ack(msg_class, msg_id, positivo=False)

            del buffer[:trama_total]

# --- Lanzamiento del hilo de escucha en paralelo al bucle de emisión ---
hilo = threading.Thread(target=hilo_escucha_configuracion, daemon=True)
hilo.start()

print("====================================================")
print(" Emulador HIL - GPS ZED-F9P con handshake de configuración")
print(f" Arranca en modo fábrica: {args.baudrate_inicial} baud, UBX desactivado")
print("====================================================")

t_inicio = time.perf_counter()
semana_gps = 2320
itow_inicial_ms = 300_000_000
lat0, lon0, altura0 = 39.2833, -0.3167, 5.0

try:
    while True:
        t_actual = time.perf_counter()
        t_transcurrido = t_actual - t_inicio
        itow_actual = itow_inicial_ms + int(t_transcurrido * 1000)

        with lock_estado:
            pvt_activo = estado_config["nav_pvt_activo"]
            rawx_activo = estado_config["rawx_activo"]

        if pvt_activo:
            lat_sim = lat0 + 0.0000005 * math.sin(t_transcurrido * 0.2)
            lon_sim = lon0 + 0.0000005 * math.cos(t_transcurrido * 0.2)
            payload_pvt = construir_nav_pvt(itow_actual, lat_sim, lon_sim, altura0,
                                             fix_type=4, num_sv=args.num_sats)
            ser.write(construir_trama_ubx(CLASS_NAV, ID_PVT, payload_pvt))

        if rawx_activo:
            payload_rawx = construir_rawx(itow_actual / 1000.0, semana_gps, args.num_sats)
            ser.write(construir_trama_ubx(CLASS_RXM, ID_RAWX, payload_rawx))

        if not pvt_activo and not rawx_activo:
            # Comportamiento de fábrica: emisión de NMEA simulado a baja frecuencia,
            # útil para validar que el firmware ignora correctamente tramas no-UBX
            # mientras espera a que su propia secuencia de configuración surta efecto.
            ser.write(b"$GPGGA,120000.00,,,,,0,00,99.99,,,,,,*76\r\n")

        time.sleep(0.2)  # tasa de emisión de 5 Hz una vez configurado

except KeyboardInterrupt:
    print("\n[INFO] Deteniendo emulador GPS...")
    ser.close()
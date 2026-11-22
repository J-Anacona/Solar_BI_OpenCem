#!/usr/bin/env python3
"""
simulator/simulador.py
Inserta lecturas nuevas (1 por inversor) en gold.fact_telemetria con la hora actual.
 * LOOP_S = 0 : una sola inserción y termina (modo CronJob).
 * LOOP_S > 0 : repite cada LOOP_S segundos (pruebas locales).
Perfil solar simplificado, con una anomalia ocasional de SOC bajo para disparar la alerta.
Parametros por variables de entorno; credenciales PG* (no van en la imagen).
"""
import math
import os
import random
import time

import psycopg2

TZ = os.getenv("TZ_SITIO", "Asia/Shanghai")
LOOP_S = int(os.getenv("LOOP_S", "0"))
PROB_ANOMALIA = float(os.getenv("PROB_ANOMALIA", "0.05"))   # prob. de SOC bajo por lectura
SOC_ANOMALO = float(os.getenv("SOC_ANOMALO", "8"))          # % que dispara la alerta
PICO_W = {1: float(os.getenv("PICO_W_INV1", "600")),
          2: float(os.getenv("PICO_W_INV2", "900"))}


def ov(cur):
    cur.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='gold' "
                "AND table_name='fact_telemetria' AND is_identity='YES' LIMIT 1")
    return " OVERRIDING SYSTEM VALUE " if cur.fetchone() else " "


def pot_solar(hora_decimal, pico):
    if hora_decimal < 7 or hora_decimal > 18:
        return 0.0
    base = pico * math.sin(math.pi * (hora_decimal - 7) / 11)
    return max(0.0, base * random.uniform(0.6, 1.0))


def una_ronda(conn):
    cur = conn.cursor()
    cur.execute("SELECT now() AT TIME ZONE %s", (TZ,))
    local = cur.fetchone()[0]
    hora_dec = local.hour + local.minute / 60
    fecha_key = int(local.strftime("%Y%m%d"))
    hora_key = local.hour * 100 + (local.minute // 5) * 5
    o = ov(cur)

    for inv in (1, 2):
        pv = pot_solar(hora_dec, PICO_W[inv])
        carga = random.uniform(300, 700)

        cur.execute(
            "SELECT battsoc FROM gold.fact_telemetria t "
            "JOIN gold.dim_inversor i USING (inversor_key) "
            "WHERE i.inverter_origen = %s AND battsoc IS NOT NULL "
            "ORDER BY fecha_hora DESC LIMIT 1", (inv,))
        fila = cur.fetchone()
        soc = float(fila[0]) if fila and fila[0] is not None else 60.0
        if soc < 30:
            soc = 60.0                       # recuperacion tras una anomalia
        soc += random.uniform(0, 1.5) if pv > 0 else -random.uniform(0, 0.8)
        soc = min(100.0, max(30.0, soc))
        anomalia = random.random() < PROB_ANOMALIA
        if anomalia:
            soc = SOC_ANOMALO

        red = max(0.0, carga - pv) * 0.3
        bat = max(-500.0, min(500.0, pv - carga))
        temp = 30 + pv / 60 + random.uniform(-1, 1)

        cur.execute(
            "INSERT INTO gold.fact_telemetria (telemetria_key, fecha_key, hora_key, inversor_key, "
            "calidad_key, fecha_hora, pv1power_w, battsoc, battchgpower, outsumw, gridpowerw_a, "
            "linepowerw_a, temper1) " + o +
            "SELECT (SELECT COALESCE(MAX(telemetria_key),0)+1 FROM gold.fact_telemetria), %s, %s, "
            "i.inversor_key, 1, now(), %s, %s, %s, %s, %s, %s, %s "
            "FROM gold.dim_inversor i WHERE i.inverter_origen = %s",
            (fecha_key, hora_key, round(pv, 1), round(soc, 1), round(bat, 1),
             round(carga, 1), round(red, 1), round(red, 1), round(temp, 1), inv))
        print(f"[sim] inv={inv} pv={pv:6.1f} W  soc={soc:5.1f} %  carga={carga:5.1f} W"
              + ("  <-- ANOMALIA" if anomalia else ""), flush=True)
    conn.commit()
    cur.close()


def main():
    conn = psycopg2.connect()
    try:
        una_ronda(conn)
        while LOOP_S > 0:
            time.sleep(LOOP_S)
            una_ronda(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
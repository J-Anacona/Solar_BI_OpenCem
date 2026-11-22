#!/usr/bin/env python3
"""
etl/03_silver_gold.py
Bronze (PostgreSQL) -> Silver (telemetria_5min) -> Gold (dimensiones y hechos).

 * Limpieza R1..R7 con conteos antes / afectadas / despues (en pantalla y en silver.etl_log).
 * Silver: bloques de 5 min por inversor.
 * Gold: energia solar = integracion de pv1power (contador solo para validar).
 * Conciliacion: filas limpias == suma de lecturas en Silver.
 * Idempotente: cada corrida vacia Silver y Gold (salvo dim_factor_emision) y reconstruye.

Credenciales: variables PG* o archivo .env (no se versiona).
"""
import os
import time
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2

TZ = os.getenv("TZ_SITIO", "Asia/Shanghai")          # SUPUESTO: confirmar en support.zip
BLOQUE_S = 300                                       # 5 minutos
TOPE_KWH = 200                                       # contadores diarios fuera de 0..TOPE = invalidos
UMBRAL_HUECO_S = int(os.getenv("UMBRAL_HUECO_S", "900"))   # hueco de datos > 15 min
TARIFA = os.getenv("TARIFA_COP_KWH")                 # COP/kWh, la eliges y justificas

# VERIFICAR contra la fuente oficial (UPME) antes de citarlos en el informe
FACTORES = [
    (2023, 0.177, "UPME - Factores de emision del SIN 2023 (inventarios GEI)", None, "2023-01-01"),
    (2024, 0.220, "UPME - Factores de emision del SIN 2024 (inventarios GEI)", None, "2024-01-01"),
]


def ov(cur, esquema, tabla):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s AND is_identity='YES' LIMIT 1",
        (esquema, tabla),
    )
    return " OVERRIDING SYSTEM VALUE " if cur.fetchone() else " "


def contar(cur, tabla):
    cur.execute(f"SELECT COUNT(*) FROM {tabla}")
    return cur.fetchone()[0]


def log(cur, proceso, leidos, insertados, rechazados, detalle, t0):
    o = ov(cur, "silver", "etl_log")
    cur.execute(
        "INSERT INTO silver.etl_log (etl_id, proceso, fecha_inicio, fecha_fin, estado, "
        "registros_leidos, registros_insertados, registros_rechazados, detalle) " + o +
        "VALUES ((SELECT COALESCE(MAX(etl_id),0)+1 FROM silver.etl_log), %s, %s, now(), 'EXITOSO', %s, %s, %s, %s)",
        (proceso, t0, leidos, insertados, rechazados, detalle),
    )


REGLAS = [
    ("R1_lectura_vacia",
     "DELETE FROM stg_analog WHERE pv1power IS NULL AND battsoc IS NULL "
     "AND outsumw IS NULL AND linepowerw_a IS NULL",
     "Filas sin ninguna variable principal: falla de lectura, no evento operativo. Se eliminan."),
    ("R2_duplicados",
     "DELETE FROM stg_analog WHERE rid IN ("
     " SELECT rid FROM (SELECT rid, ROW_NUMBER() OVER ("
     "   PARTITION BY inverter, ROUND(read_ts::numeric, 3) ORDER BY read_ts, rid) AS rn "
     "  FROM stg_analog) d WHERE rn > 1)",
     "Duplicados por (inverter, read_ts al ms). Se conserva la primera lectura."),
    ("R3_battvolt_cero",
     "UPDATE stg_analog SET battvolt = NULL WHERE battvolt = 0",
     "0 V es imposible en un banco de bateria. Se anula el valor, la fila se conserva."),
    ("R4_soc_fuera_rango",
     "UPDATE stg_analog SET battsoc = NULL WHERE battsoc < 0 OR battsoc > 100",
     "SoC fuera de 0-100 %. Se anula el valor."),
    ("R5_pv_negativa",
     "UPDATE stg_analog SET pv1power = NULL WHERE pv1power < 0",
     "Potencia solar negativa es imposible. Se anula el valor."),
    ("R6_linea_negativa",
     "UPDATE stg_analog SET linepowerw_a = 0 WHERE linepowerw_a < 0",
     "Negativos pequenos de potencia de linea: ruido de medicion. Se fijan en 0."),
    ("R7_temper1_implausible",
     "UPDATE stg_analog SET temper1 = NULL WHERE temper1 < -10",
     "Minimo -20,3 identico en ambos inversores: posible valor centinela. Se anula."),
]


def main():
    t_global = time.time()
    conn = psycopg2.connect()
    cur = conn.cursor()

    # ---------------------------------------------------------------- A
    print("[A] Preparando estructura ...")
    cur.execute("TRUNCATE silver.telemetria_5min")
    for sql in [
        "ALTER TABLE silver.telemetria_5min "
        "ADD COLUMN IF NOT EXISTS n_lecturas integer, ADD COLUMN IF NOT EXISTS battsoc numeric, "
        "ADD COLUMN IF NOT EXISTS battvolt numeric, ADD COLUMN IF NOT EXISTS battcurr numeric, "
        "ADD COLUMN IF NOT EXISTS battchgpower numeric, ADD COLUMN IF NOT EXISTS outsumw numeric, "
        "ADD COLUMN IF NOT EXISTS gridpowerw_a numeric, ADD COLUMN IF NOT EXISTS linepowerw_a numeric, "
        "ADD COLUMN IF NOT EXISTS temper1 numeric",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tel5_inv_ts ON silver.telemetria_5min (inverter, fecha_hora)",
    ]:
        cur.execute(sql)
    conn.commit()

    # ---------------------------------------------------------------- B
    print("[B] Cargando dimensiones ...")
    cur.execute(
        "TRUNCATE gold.fact_telemetria, gold.fact_energia_diaria, gold.fact_eventos, "
        "gold.dim_fecha, gold.dim_hora, gold.dim_inversor, gold.dim_tipo_evento, gold.dim_calidad_dato"
    )

    o = ov(cur, "gold", "dim_calidad_dato")
    cur.execute(
        "INSERT INTO gold.dim_calidad_dato (calidad_key, codigo, descripcion) " + o + "VALUES "
        "(1,'OK','Bloque de 5 min con 15 o mas lecturas (cobertura completa)'),"
        "(2,'PARCIAL','Bloque de 5 min con 5 a 14 lecturas (cobertura parcial)'),"
        "(3,'ESCASO','Bloque de 5 min con menos de 5 lecturas (cobertura escasa)')"
    )
    o = ov(cur, "gold", "dim_inversor")
    cur.execute(
        "INSERT INTO gold.dim_inversor (inversor_key, inverter_origen, nombre, descripcion, activo) " + o + "VALUES "
        "(1,1,'Inversor 1','Subsistema 1 de la microrred hibrida OpenCEM',true),"
        "(2,2,'Inversor 2','Subsistema 2 de la microrred hibrida OpenCEM',true)"
    )
    o = ov(cur, "gold", "dim_tipo_evento")
    cur.execute(
        "INSERT INTO gold.dim_tipo_evento (tipo_evento_key, codigo, nombre, descripcion, nivel) " + o + "VALUES "
        "(1,'ANOTACION_CONTEXTO','Anotacion de contexto','Nota manual o de estacion de trabajo sobre una tarea o evento del sitio','INFO'),"
        f"(2,'HUECO_DATOS','Hueco de datos','Intervalo de mas de {UMBRAL_HUECO_S // 60} min sin lecturas (falla de captura, no evento fisico confirmado)','ADVERTENCIA')"
    )
    o = ov(cur, "gold", "dim_fecha")
    cur.execute(
        "INSERT INTO gold.dim_fecha (fecha_key, fecha, anio, trimestre, mes, nombre_mes, dia, dia_semana, nombre_dia, es_fin_semana) "
        + o +
        "SELECT to_char(d,'YYYYMMDD')::int, d::date, extract(year FROM d)::smallint, "
        "extract(quarter FROM d)::smallint, extract(month FROM d)::smallint, "
        "(ARRAY['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'])[extract(month FROM d)::int], "
        "extract(day FROM d)::smallint, extract(isodow FROM d)::smallint, "
        "(ARRAY['Lunes','Martes','Miercoles','Jueves','Viernes','Sabado','Domingo'])[extract(isodow FROM d)::int], "
        "extract(isodow FROM d) IN (6,7) "
        "FROM generate_series(date '2024-01-01', date '2026-12-31', interval '1 day') AS g(d)"
    )
    o = ov(cur, "gold", "dim_hora")
    cur.execute(
        "INSERT INTO gold.dim_hora (hora_key, hora, hora_numero, minuto, segundo, franja_horaria) " + o +
        "SELECT (m/60)*100 + (m%60), make_time(m/60, m%60, 0), (m/60)::smallint, (m%60)::smallint, 0::smallint, "
        "CASE WHEN m/60 < 6 THEN 'Madrugada' WHEN m/60 < 12 THEN 'Manana' WHEN m/60 < 18 THEN 'Tarde' ELSE 'Noche' END "
        "FROM (SELECT i*5 AS m FROM generate_series(0, 287) AS s(i)) x"
    )

    o = ov(cur, "gold", "dim_factor_emision")
    for anio, factor, fuente, resol, vig in FACTORES:
        cur.execute(
            "INSERT INTO gold.dim_factor_emision (factor_emision_key, anio, pais, sistema_electrico, tipo_factor, "
            "factor_kgco2e_kwh, unidad, fuente, resolucion, vigencia, es_actual) " + o +
            "SELECT k.n, %s, 'Colombia', 'SIN', 'INVENTARIO_GEI', %s, 'kgCO2e/kWh', %s, %s, %s::date, false "
            "FROM (SELECT COALESCE(MAX(factor_emision_key),0)+1 AS n FROM gold.dim_factor_emision) k "
            "WHERE NOT EXISTS (SELECT 1 FROM gold.dim_factor_emision WHERE anio = %s AND tipo_factor = 'INVENTARIO_GEI')",
            (anio, factor, fuente, resol, vig, anio),
        )
    cur.execute(
        "UPDATE gold.dim_factor_emision SET es_actual = (anio = (SELECT MAX(anio) FROM gold.dim_factor_emision "
        "WHERE tipo_factor='INVENTARIO_GEI')) WHERE tipo_factor = 'INVENTARIO_GEI'"
    )
    conn.commit()

    # ---------------------------------------------------------------- C
    print("[C] Limpieza Bronze -> staging (reglas con conteos) ...")
    t0 = datetime.now()
    cur.execute("DROP TABLE IF EXISTS stg_analog")
    cur.execute(
        "CREATE TEMP TABLE stg_analog AS "
        "SELECT ROW_NUMBER() OVER () AS rid, inverter, read_ts, pv1power, battsoc, battvolt, battcurr, "
        "battchgpower, outsumw, gridpowerw_a, linepowerw_a, temper1 FROM bronze.analog_measurements"
    )
    cur.execute("CREATE INDEX ON stg_analog (rid)")
    cur.execute("ANALYZE stg_analog")
    n_bronze = contar(cur, "stg_analog")
    log(cur, "silver:R0_carga_staging", n_bronze, n_bronze, 0, "Copia de analog_measurements (bronze) a staging", t0)
    conn.commit()

    resumen = [("R0_carga_staging", n_bronze, 0, n_bronze)]
    for nombre, sql, detalle in REGLAS:
        t0 = datetime.now()
        antes = contar(cur, "stg_analog")
        cur.execute(sql)
        afectadas = cur.rowcount
        despues = contar(cur, "stg_analog")
        log(cur, "silver:" + nombre, antes, despues, afectadas, detalle, t0)
        resumen.append((nombre, antes, afectadas, despues))
        print(f"    {nombre:<24} antes={antes:>10,}  afectadas={afectadas:>9,}  despues={despues:>10,}")
        conn.commit()
    cur.execute("ANALYZE stg_analog")

    # ---------------------------------------------------------------- D
    print("[D] Silver: agregacion a 5 minutos ...")
    t0 = datetime.now()
    o = ov(cur, "silver", "telemetria_5min")
    b = str(BLOQUE_S)
    cur.execute(
        "INSERT INTO silver.telemetria_5min (telemetria_id, inverter, read_ts_epoch, fecha_hora, pv1power_w, "
        "pvgeneratenergytoday_kwh, linechgenergytday_kwh, calidad_registro, source_record_hash, loaded_at, "
        "n_lecturas, battsoc, battvolt, battcurr, battchgpower, outsumw, gridpowerw_a, linepowerw_a, temper1) " + o +
        "SELECT ROW_NUMBER() OVER (ORDER BY a.inverter, a.bin), a.inverter, a.bin, to_timestamp(a.bin), "
        "a.pv1power_w, c.pv_kwh, c.linechg_kwh, "
        "CASE WHEN a.n >= 15 THEN 'OK' WHEN a.n >= 5 THEN 'PARCIAL' ELSE 'ESCASO' END, "
        "md5(a.inverter::text || '|' || a.bin::text), now(), a.n, a.battsoc, a.battvolt, a.battcurr, "
        "a.battchgpower, a.outsumw, a.gridpowerw_a, a.linepowerw_a, a.temper1 "
        "FROM (SELECT inverter, (floor(read_ts / " + b + ") * " + b + ")::bigint AS bin, COUNT(*) AS n, "
        "  ROUND(AVG(pv1power)::numeric, 2) AS pv1power_w, ROUND(AVG(battsoc)::numeric, 2) AS battsoc, "
        "  ROUND(AVG(battvolt)::numeric, 2) AS battvolt, ROUND(AVG(battcurr)::numeric, 2) AS battcurr, "
        "  ROUND(AVG(battchgpower)::numeric, 2) AS battchgpower, ROUND(AVG(outsumw)::numeric, 2) AS outsumw, "
        "  ROUND(AVG(gridpowerw_a)::numeric, 2) AS gridpowerw_a, ROUND(AVG(linepowerw_a)::numeric, 2) AS linepowerw_a, "
        "  ROUND(AVG(temper1)::numeric, 2) AS temper1 "
        "  FROM stg_analog GROUP BY 1, 2) a "
        "LEFT JOIN (SELECT inverter, (floor(read_ts / " + b + ") * " + b + ")::bigint AS bin, "
        f"  MAX(pvgeneratenergytoday) FILTER (WHERE pvgeneratenergytoday BETWEEN 0 AND {TOPE_KWH}) AS pv_kwh, "
        f"  MAX(linechgenergytday) FILTER (WHERE linechgenergytday BETWEEN 0 AND {TOPE_KWH}) AS linechg_kwh "
        "  FROM bronze.statistics GROUP BY 1, 2) c USING (inverter, bin)"
    )
    n_silver = contar(cur, "silver.telemetria_5min")
    cur.execute("SELECT COALESCE(SUM(n_lecturas), 0) FROM silver.telemetria_5min")
    suma_lecturas = cur.fetchone()[0]
    limpias = contar(cur, "stg_analog")
    if suma_lecturas != limpias:
        conn.rollback()
        raise RuntimeError(f"Conciliacion Silver fallida: limpias={limpias:,} vs suma lecturas={suma_lecturas:,}")
    log(cur, "silver:agregacion_5min", limpias, n_silver, 0,
        "Bloques de 5 min por inversor; conciliacion: filas limpias == suma de n_lecturas", t0)
    conn.commit()
    print(f"    bloques: {n_silver:,} | filas limpias: {limpias:,} == suma de lecturas: {suma_lecturas:,}  OK")

    # ---------------------------------------------------------------- E
    print("[E] Gold: hechos ...")
    t0 = datetime.now()
    l_ts = f"(t.fecha_hora AT TIME ZONE '{TZ}')"
    o = ov(cur, "gold", "fact_telemetria")
    cur.execute(
        "INSERT INTO gold.fact_telemetria (telemetria_key, fecha_key, hora_key, inversor_key, calidad_key, fecha_hora, "
        "pv1power_w, pvgeneratenergytoday_kwh, linechgenergytday_kwh, battsoc, battchgpower, outsumw, "
        "gridpowerw_a, linepowerw_a, temper1) " + o +
        f"SELECT t.telemetria_id, to_char({l_ts}, 'YYYYMMDD')::int, "
        f"(extract(hour FROM {l_ts})::int * 100 + extract(minute FROM {l_ts})::int), "
        "i.inversor_key, q.calidad_key, t.fecha_hora, t.pv1power_w, t.pvgeneratenergytoday_kwh, "
        "t.linechgenergytday_kwh, t.battsoc, t.battchgpower, t.outsumw, t.gridpowerw_a, t.linepowerw_a, t.temper1 "
        "FROM silver.telemetria_5min t "
        "JOIN gold.dim_inversor i ON i.inverter_origen = t.inverter "
        "JOIN gold.dim_calidad_dato q ON q.codigo = t.calidad_registro"
    )
    n_ft = contar(cur, "gold.fact_telemetria")
    log(cur, "gold:fact_telemetria", n_silver, n_ft, n_silver - n_ft, "Silver 5 min -> hecho de telemetria", t0)

    # ---- energia diaria: solar por integracion de pv1power; resto desde contadores
    t0 = datetime.now()
    rng = f"BETWEEN 0 AND {TOPE_KWH}"
    cur.execute("DROP TABLE IF EXISTS tmp_dia")
    cur.execute(
        "CREATE TEMP TABLE tmp_dia AS "
        "WITH cont AS ("
        f" SELECT inverter, (to_timestamp(read_ts) AT TIME ZONE '{TZ}')::date AS dia, "
        f"  MAX(pvgeneratenergytoday) FILTER (WHERE pvgeneratenergytoday {rng}) AS solar_cnt, "
        f"  MAX(usedenergytoday) FILTER (WHERE usedenergytoday {rng}) AS usada, "
        f"  MAX(batchgenergytoday) FILTER (WHERE batchgenergytoday {rng}) AS bat_chg, "
        f"  MAX(batdischgenergytoday) FILTER (WHERE batdischgenergytoday {rng}) AS bat_dis, "
        f"  MAX(loadconsumlinetday) FILTER (WHERE loadconsumlinetday {rng}) AS carga_linea, "
        f"  MAX(linechgenergytday) FILTER (WHERE linechgenergytday {rng}) AS linea_chg "
        " FROM bronze.statistics GROUP BY 1, 2), "
        "disp AS ("
        f" SELECT inverter, (fecha_hora AT TIME ZONE '{TZ}')::date AS dia, SUM(n_lecturas) AS n, "
        "  COUNT(*) AS bloques, COUNT(*) FILTER (WHERE calidad_registro = 'OK') AS bloques_ok, "
        "  MIN(battsoc) AS soc_min, AVG(battsoc) AS soc_prom, MAX(battsoc) AS soc_max, "
        f"  SUM(pv1power_w) * ({BLOQUE_S} / 3600.0) / 1000.0 AS solar_int "
        " FROM silver.telemetria_5min GROUP BY 1, 2), "
        "llaves AS (SELECT inverter, dia FROM cont UNION SELECT inverter, dia FROM disp) "
        "SELECT k.inverter, k.dia, c.solar_cnt, c.usada, c.bat_chg, c.bat_dis, c.carga_linea, c.linea_chg, "
        "       d.n, d.bloques, d.bloques_ok, d.soc_min, d.soc_prom, d.soc_max, d.solar_int "
        "FROM llaves k "
        "LEFT JOIN cont c ON c.inverter = k.inverter AND c.dia = k.dia "
        "LEFT JOIN disp d ON d.inverter = k.inverter AND d.dia = k.dia"
    )

    o = ov(cur, "gold", "fact_energia_diaria")
    cur.execute(
        "INSERT INTO gold.fact_energia_diaria (energia_diaria_key, fecha_key, inversor_key, factor_emision_key, "
        "energia_solar_kwh, energia_consumida_kwh, energia_carga_bateria_kwh, energia_descarga_bateria_kwh, "
        "energia_red_kwh, co2_evitado_kg, cantidad_mediciones, calidad_registro, disponibilidad_pct, "
        "datos_validos_pct, soc_min, soc_prom, soc_max, autosuficiencia_pct) " + o +
        "SELECT ROW_NUMBER() OVER (ORDER BY t.dia, t.inverter), to_char(t.dia, 'YYYYMMDD')::int, i.inversor_key, "
        "f.factor_emision_key, ROUND(t.solar_int::numeric, 3), t.usada, t.bat_chg, t.bat_dis, "
        "CASE WHEN t.carga_linea IS NULL AND t.linea_chg IS NULL THEN NULL "
        "     ELSE COALESCE(t.carga_linea, 0) + COALESCE(t.linea_chg, 0) END, "
        "ROUND((t.solar_int * f.factor)::numeric, 3), t.n, "
        "CASE WHEN t.bloques IS NULL THEN 'ESCASO' WHEN 100.0 * t.bloques / 288 >= 90 THEN 'OK' "
        "     WHEN 100.0 * t.bloques / 288 >= 50 THEN 'PARCIAL' ELSE 'ESCASO' END, "
        "ROUND((100.0 * t.bloques / 288)::numeric, 1), ROUND((100.0 * t.bloques_ok / 288)::numeric, 1), "
        "ROUND(t.soc_min::numeric, 1), ROUND(t.soc_prom::numeric, 1), ROUND(t.soc_max::numeric, 1), "
        "CASE WHEN t.usada > 0 AND (t.carga_linea IS NOT NULL OR t.linea_chg IS NOT NULL) "
        "     THEN LEAST(100, GREATEST(0, ROUND((100.0 * (1 - (COALESCE(t.carga_linea,0) + COALESCE(t.linea_chg,0)) / t.usada))::numeric, 1))) END "
        "FROM tmp_dia t "
        "JOIN gold.dim_inversor i ON i.inverter_origen = t.inverter "
        "LEFT JOIN LATERAL (SELECT factor_emision_key, factor_kgco2e_kwh AS factor FROM gold.dim_factor_emision "
        "  WHERE tipo_factor = 'INVENTARIO_GEI' ORDER BY ABS(anio - extract(year FROM t.dia)), anio DESC LIMIT 1) f ON true"
    )
    n_fe = contar(cur, "gold.fact_energia_diaria")

    if TARIFA:
        tar = float(TARIFA)
        cur.execute(
            "UPDATE gold.fact_energia_diaria SET tarifa_cop_kwh = %s, "
            "ahorro_solar_cop = ROUND((energia_solar_kwh * %s)::numeric, 2), "
            "costo_red_cop = ROUND((energia_red_kwh * %s)::numeric, 2)",
            (tar, tar, tar),
        )
    else:
        print("    AVISO: TARIFA_COP_KWH no definida; ahorro_solar_cop y costo_red_cop quedan nulos.")

    log(cur, "gold:fact_energia_diaria", n_ft, n_fe, 0,
        "Energia solar = integracion de pv1power (5 min); CO2 = solar x factor SIN; resto desde contadores", t0)

    # ---- eventos: anotaciones de contexto + huecos de datos
    t0 = datetime.now()
    o = ov(cur, "gold", "fact_eventos")
    cur.execute(
        "WITH g AS (SELECT inverter, read_ts, LAG(read_ts) OVER (PARTITION BY inverter ORDER BY read_ts) AS prev_ts "
        "           FROM stg_analog), "
        "ev AS ("
        " SELECT CASE WHEN \"value\"::jsonb->>'inverter' ~ '^[0-9]+$' THEN (\"value\"::jsonb->>'inverter')::int END AS inverter, "
        "  'ANOTACION_CONTEXTO'::text AS tipo, to_timestamp(\"start\") AS fecha_hora, "
        "  LEFT(\"value\"::jsonb->>'textual_description', 300) AS descripcion, 'INFO'::text AS nivel, "
        "  ROUND((\"end\" - \"start\") / 3600.0, 2) AS valor, 'h'::text AS unidad "
        " FROM bronze.context WHERE \"value\"::jsonb ? 'inverter' AND \"start\" BETWEEN 1704000000 AND 1798761600 "
        " UNION ALL "
        " SELECT inverter, 'HUECO_DATOS', to_timestamp(prev_ts), "
        "  'Sin lecturas durante ' || ROUND(((read_ts - prev_ts) / 3600.0)::numeric, 2)::text || ' h', "
        "  CASE WHEN read_ts - prev_ts > 86400 THEN 'CRITICO' ELSE 'ADVERTENCIA' END, "
        "  ROUND(((read_ts - prev_ts) / 3600.0)::numeric, 2), 'h' "
        f" FROM g WHERE read_ts - prev_ts > {UMBRAL_HUECO_S}), "
        f"ev2 AS (SELECT e.*, e.fecha_hora AT TIME ZONE '{TZ}' AS ts FROM ev e) "
        "INSERT INTO gold.fact_eventos (evento_key, fecha_key, hora_key, inversor_key, tipo_evento_key, fecha_hora, "
        "descripcion, nivel_severidad, valor, unidad) " + o +
        "SELECT ROW_NUMBER() OVER (ORDER BY e.fecha_hora, e.inverter, e.tipo), to_char(e.ts, 'YYYYMMDD')::int, "
        "(extract(hour FROM e.ts)::int * 100 + (extract(minute FROM e.ts)::int / 5) * 5), "
        "i.inversor_key, t.tipo_evento_key, e.fecha_hora, e.descripcion, e.nivel, e.valor, e.unidad "
        "FROM ev2 e JOIN gold.dim_inversor i ON i.inverter_origen = e.inverter "
        "JOIN gold.dim_tipo_evento t ON t.codigo = e.tipo"
    )
    n_ev = contar(cur, "gold.fact_eventos")
    log(cur, "gold:fact_eventos", None, n_ev, 0,
        f"Anotaciones de contexto (con inversor) + huecos de datos > {UMBRAL_HUECO_S // 60} min", t0)
    conn.commit()

    # ---------------------------------------------------------------- F
    print("\n" + "=" * 74)
    print("RESUMEN DE LIMPIEZA (analog_measurements)")
    print(f"{'regla':<26}{'antes':>13}{'afectadas':>13}{'despues':>13}")
    for nombre, antes, afect, desp in resumen:
        print(f"{nombre:<26}{antes:>13,}{afect:>13,}{desp:>13,}")
    print("-" * 74)
    print(f"silver.telemetria_5min   : {n_silver:>10,} bloques")
    print(f"gold.fact_telemetria     : {n_ft:>10,}")
    print(f"gold.fact_energia_diaria : {n_fe:>10,}")
    print(f"gold.fact_eventos        : {n_ev:>10,}")

    cur.execute(
        "SELECT i.nombre, COUNT(*), ROUND(MIN(f.energia_solar_kwh),2), ROUND(AVG(f.energia_solar_kwh),2), "
        "ROUND(MAX(f.energia_solar_kwh),2), ROUND(SUM(f.co2_evitado_kg),1) "
        "FROM gold.fact_energia_diaria f JOIN gold.dim_inversor i USING (inversor_key) GROUP BY 1 ORDER BY 1"
    )
    print("\nEnergia solar diaria (kWh) por inversor: dias | min | prom | max | CO2 evitado total (kg)")
    for fila in cur.fetchall():
        print("  ", fila)

    cur.execute(
        "SELECT inverter, COUNT(*), ROUND(SUM(solar_int)::numeric,1), ROUND(SUM(solar_cnt)::numeric,1), "
        "ROUND(AVG(ABS(solar_int - solar_cnt))::numeric,2) "
        "FROM tmp_dia WHERE 100.0 * bloques / 288 >= 90 AND solar_int IS NOT NULL AND solar_cnt IS NOT NULL "
        "GROUP BY inverter ORDER BY inverter"
    )
    print("\nValidacion cruzada (dias con >= 90 % de cobertura): inversor | dias | kWh integrados | kWh contador | error medio diario")
    for fila in cur.fetchall():
        print("  ", fila)
    print("=" * 74)
    print(f"Listo en {round(time.time() - t_global)} s")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
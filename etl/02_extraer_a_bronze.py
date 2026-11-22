#!/usr/bin/env python3
"""
02_extraer_a_bronze.py
----------------------
Extrae tablas del SQLite de OpenCEM (capa Bronze de origen, SOLO LECTURA) y las
copia sin transformar al esquema `bronze` de PostgreSQL.

Propiedades:
  * Idempotente: cada tabla se recrea (DROP + CREATE + COPY) dentro de UNA
    transaccion. Correrlo dos veces deja exactamente el mismo resultado.
  * Conciliacion: compara filas del origen vs filas cargadas; si difieren,
    revierte esa tabla y falla.
  * Evidencia: escribe una fila por tabla en bronze.etl_log.
  * Credenciales fuera del codigo: se leen de variables de entorno PG* o de un
    archivo .env (que NO se versiona).

Variables de entorno:
  PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD   (las lee libpq/psycopg2)
  OPENCEM_SQLITE   ruta al archivo opencem-v1.0.0.sqlite (ya descomprimido)

Uso:
  python etl/02_extraer_a_bronze.py --tablas context          # prueba rapida
  python etl/02_extraer_a_bronze.py                            # tablas por defecto
  python etl/02_extraer_a_bronze.py --incluir-fault-history    # agrega fault_history
"""
import argparse
import csv
import io
import os
import sqlite3
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2

TABLAS_DEFECTO = ["context", "analog_measurements", "totals", "status", "statistics"]
LOTE = 100_000
NULO = r"\N"  # marcador de NULL para COPY ... FORMAT csv


def tipo_pg(origen, tabla, col, declarado):
    """Elige el tipo de PostgreSQL segun los tipos REALES que hay en SQLite
    (SQLite es de tipado flexible: una columna INTEGER puede traer reales o texto)."""
    obs = {t for (t,) in origen.execute(f'SELECT DISTINCT typeof("{col}") FROM "{tabla}"')}
    obs.discard("null")
    por_defecto = {"INTEGER": "bigint", "REAL": "double precision"}.get(declarado, "text")

    if not obs:
        return por_defecto
    if "text" in obs or "blob" in obs:
        tipo = "text"
    elif "real" in obs:
        tipo = "double precision"
    else:  # solo enteros
        tipo = "double precision" if declarado == "REAL" else "bigint"

    if tipo != por_defecto:
        print(f"    AVISO {tabla}.{col}: declarado {declarado or '(vacio)'}, "
              f"tipos observados {sorted(obs)} -> {tipo}")
    return tipo


def cargar_tabla(origen, destino, tabla):
    t0 = time.time()
    cols = [(r[1], (r[2] or "").upper()) for r in origen.execute(f'PRAGMA table_info("{tabla}")')]
    if not cols:
        raise ValueError(f"La tabla '{tabla}' no existe en el SQLite")
    nombres = [c for c, _ in cols]

    n_origen = origen.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone()[0]
    print(f"\n[{tabla}] filas en origen: {n_origen:,}")
    tipos = {c: tipo_pg(origen, tabla, c, d) for c, d in cols}

    cur = destino.cursor()
    try:
        cur.execute(f'DROP TABLE IF EXISTS bronze."{tabla}"')
        cur.execute(
            f'CREATE TABLE bronze."{tabla}" ('
            + ", ".join(f'"{c}" {tipos[c]}' for c in nombres) + ")"
        )
        copy_sql = (
            f'COPY bronze."{tabla}" (' + ", ".join(f'"{c}"' for c in nombres) + ") "
            "FROM STDIN WITH (FORMAT csv, NULL '\\N')"
        )

        cursor = origen.execute(
            "SELECT " + ", ".join(f'"{c}"' for c in nombres) + f' FROM "{tabla}"'
        )
        cargadas = 0
        while True:
            lote = cursor.fetchmany(LOTE)
            if not lote:
                break
            buf = io.StringIO()
            escritor = csv.writer(buf, lineterminator="\n")
            escritor.writerows([[NULO if v is None else v for v in fila] for fila in lote])
            buf.seek(0)
            cur.copy_expert(copy_sql, buf)
            cargadas += len(lote)
            print(f"    cargadas {cargadas:,} / {n_origen:,}", end="\r")
        print()

        if "read_ts" in nombres and "inverter" in nombres:
            cur.execute(
                f'CREATE INDEX ix_{tabla}_inv_ts ON bronze."{tabla}" (inverter, read_ts)'
            )
        cur.execute(f'ANALYZE bronze."{tabla}"')

        cur.execute(f'SELECT COUNT(*) FROM bronze."{tabla}"')
        n_destino = cur.fetchone()[0]
        if n_destino != n_origen:
            raise RuntimeError(
                f"Conciliacion fallida en {tabla}: origen={n_origen:,} destino={n_destino:,}"
            )

        segundos = round(time.time() - t0, 1)
        cur.execute(
            "INSERT INTO bronze.etl_log (tabla, filas_origen, filas_bronce, segundos, estado) "
            "VALUES (%s, %s, %s, %s, 'OK')",
            (tabla, n_origen, n_destino, segundos),
        )
        destino.commit()
        print(f"[{tabla}] OK  origen={n_origen:,}  bronze={n_destino:,}  ({segundos} s)")
        return n_origen, n_destino, segundos
    except Exception:
        destino.rollback()
        raise
    finally:
        cur.close()


def main():
    ap = argparse.ArgumentParser(description="Carga OpenCEM (SQLite) -> PostgreSQL bronze")
    ap.add_argument("--sqlite", default=os.getenv("OPENCEM_SQLITE"),
                    help="ruta al .sqlite (o variable OPENCEM_SQLITE)")
    ap.add_argument("--tablas", nargs="+", default=None, help="tablas a cargar")
    ap.add_argument("--incluir-fault-history", action="store_true",
                    help="agrega fault_history (2,1 M de filas, 66 columnas)")
    args = ap.parse_args()

    if not args.sqlite or not Path(args.sqlite).is_file():
        sys.exit("No encuentro el .sqlite. Define OPENCEM_SQLITE o usa --sqlite RUTA")

    tablas = args.tablas or (TABLAS_DEFECTO + (["fault_history"] if args.incluir_fault_history else []))

    # Origen en modo solo lectura: el .sqlite (Bronze de origen) no se modifica.
    origen = sqlite3.connect(Path(args.sqlite).resolve().as_uri() + "?mode=ro", uri=True)
    origen.text_factory = lambda b: b.decode("utf-8", errors="replace")

    destino = psycopg2.connect()  # usa PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
    with destino.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS bronze")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS bronze.etl_log ("
            " corrida_ts timestamptz NOT NULL DEFAULT now(),"
            " tabla text NOT NULL,"
            " filas_origen bigint,"
            " filas_bronce bigint,"
            " segundos numeric,"
            " estado text)"
        )
    destino.commit()

    resumen = []
    for t in tablas:
        resumen.append((t, *cargar_tabla(origen, destino, t)))

    print("\n" + "=" * 60)
    print(f"{'tabla':<22}{'origen':>12}{'bronze':>12}{'seg':>8}")
    for t, a, b, s in resumen:
        print(f"{t:<22}{a:>12,}{b:>12,}{s:>8}")
    print("=" * 60)
    origen.close()
    destino.close()


if __name__ == "__main__":
    main()
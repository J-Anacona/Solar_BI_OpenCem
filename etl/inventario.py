import sqlite3

RUTA = r"C:\Users\John\Downloads\OpenCem-descargas\opencem-v1.0.0.sqlite"
con = sqlite3.connect(f"file:{RUTA}?mode=ro", uri=True)
cur = con.cursor()

tablas = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]

print("| Tabla | Columnas | Filas | Columna tiempo | Inicio | Fin |")
print("|---|---|---|---|---|---|")
for t in tablas:
    cols = cur.execute(f'PRAGMA table_info("{t}")').fetchall()
    nombres = [c[1] for c in cols]
    n = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    tcol = next((c for c in nombres if any(k in c.lower()
                 for k in ("time", "ts", "date", "fecha"))), None)
    ini = fin = "-"
    if tcol:
        ini, fin = cur.execute(
            f'SELECT MIN("{tcol}"), MAX("{tcol}") FROM "{t}"').fetchone()
    print(f"| {t} | {len(cols)} | {n} | {tcol} | {ini} | {fin} |")

print("\n--- Detalle de columnas ---")
for t in tablas:
    print(f"\n{t}")
    for c in cur.execute(f'PRAGMA table_info("{t}")'):
        print(f"  {c[1]} ({c[2]})")
con.close()
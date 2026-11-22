
import sqlite3

RUTA_DB = r"C:\Users\John\Downloads\OpenCem-descargas\opencem-v1.0.0.sqlite"

conexion = sqlite3.connect(RUTA_DB)
cursor = conexion.cursor()

print("=" * 60)
print("INSPECCION DE LA BASE DE DATOS OPENCEM")
print("=" * 60)

# Consultar todas las tablas
cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    ORDER BY name;
""")

tablas = cursor.fetchall()

print(f"\nCantidad de tablas: {len(tablas)}")

for (tabla,) in tablas:
    print(f"\n{'-' * 50}")
    print(f"TABLA: {tabla}")
    print("-" * 50)

    cursor.execute(f'PRAGMA table_info("{tabla}")')

    columnas = cursor.fetchall()

    for columna in columnas:
        print(
            f"Campo: {columna[1]} | "
            f"Tipo: {columna[2]} | "
            f"Not Null: {columna[3]}"
        )

    cursor.execute(f'SELECT COUNT(*) FROM "{tabla}"')
    cantidad = cursor.fetchone()[0]

    print(f"Total de registros: {cantidad}")

conexion.close()
print("\nInspeccion finalizada.")

# SolarBI: inteligencia de negocios para una microrred híbrida (OpenCEM)

Taller 6 · Inteligencia de Negocios 2026-II · Docente: Ramiro Grisales Montoya
Línea de profundización: **8. Emisiones de CO₂ evitadas por la generación solar con el factor del SIN**

Solución de BI de extremo a extremo que lleva la telemetría real de una microrred híbrida (solar + batería + red) a un modelo dimensional en PostgreSQL, mediante un ETL reproducible con validación de calidad de datos. Tiene dos capas de consumo: un tablero analítico en Power BI y un tablero operativo en Grafana con alertas. Todos los servicios corren en contenedores y se orquestan en un clúster local de Kubernetes.

## Contenido

1. [Arquitectura](#arquitectura)
2. [Modelo dimensional](#modelo-dimensional)
3. [Estructura del repositorio](#estructura-del-repositorio)
4. [Requisitos del equipo anfitrión](#requisitos-del-equipo-anfitrión)
5. [Datos: descarga y verificación](#datos-descarga-y-verificación)
6. [Reproducir la solución desde cero](#reproducir-la-solución-desde-cero)
7. [Configuración y credenciales](#configuración-y-credenciales)
8. [Calidad de datos y resultados del ETL](#calidad-de-datos-y-resultados-del-etl)
9. [Supuestos y limitaciones](#supuestos-y-limitaciones)
10. [Cita de los datos y licencia](#cita-de-los-datos-y-licencia)

## Arquitectura

![Arquitectura](docs/arquitectura_solarbi.png)

| Componente | Objeto de Kubernetes | Imagen |
|---|---|---|
| Aislamiento | Namespace `solarbi` | n/a |
| PostgreSQL con datos persistentes | StatefulSet `postgres` + PVC de 10 Gi | `postgres:16.4` |
| Carga histórica (ETL) | Job `etl-historico` | `solarbi-etl:1.0` (propia) |
| Datos nuevos periódicos | CronJob `simulador` (cada minuto) | `solarbi-simulator:1.0` (propia) |
| Tablero operativo y alertas | Deployment `grafana` | `grafana/grafana:11.2.0` |
| Configuración no sensible | ConfigMap `solarbi-config` y ConfigMaps de Grafana | n/a |
| Credenciales | Secret `solarbi-secrets` | n/a |
| Acceso interno por nombre | Service `postgres` (ClusterIP) | n/a |
| Acceso desde el anfitrión | Services NodePort: `postgres-externo` (30432) y `grafana` (30300) | n/a |

Las capas de datos son:

- **Bronze:** copia fiel de las tablas del SQLite de OpenCEM (el archivo original no se modifica).
- **Silver:** telemetría limpia y agregada a bloques de 5 minutos por inversor.
- **Gold:** modelo dimensional en estrella para el consumo.

## Modelo dimensional

![Modelo dimensional](docs/modelo_dimensional.png)

| Tabla de hechos | Grano |
|---|---|
| `gold.fact_energia_diaria` | 1 fila por inversor y por día |
| `gold.fact_telemetria` | 1 fila por inversor y por bloque de 5 minutos |
| `gold.fact_eventos` | 1 fila por evento (anotación de contexto o hueco de datos) |

Dimensiones: `dim_fecha`, `dim_hora`, `dim_inversor`, `dim_calidad_dato`, `dim_factor_emision` y `dim_tipo_evento`. Las dimensiones `dim_calidad_dato` y `dim_factor_emision` fueron construidas por el equipo y no existen en la fuente.

## Estructura del repositorio

```
.
├── README.md
├── docker-compose.yml        Desarrollo local (PostgreSQL, ETL, simulador, Grafana)
├── .env.example              Plantilla de variables (el .env real no se versiona)
├── etl/
│   ├── 01_inspeccionar_sqlite.py
│   ├── 02_extraer_a_bronze.py
│   ├── 03_silver_gold.py     Limpieza, Silver, Gold, conciliación
│   ├── inventario.py
│   ├── requirements.txt
│   └── Dockerfile
├── simulator/
│   ├── simulador.py          Genera lecturas nuevas para Grafana
│   └── Dockerfile
├── sql/                      DDL y consultas de negocio (ventanas, JSON)
├── k8s/
│   ├── 00-namespace.yaml
│   ├── secrets.example.yaml  Plantilla del Secret (el real no se versiona)
│   ├── 02-configmap.yaml
│   ├── 03-postgres.yaml
│   ├── 04-grafana.yaml       Datasource, tablero y alertas por provisioning
│   ├── 05-etl-job.yaml
│   ├── 06-simulator-cronjob.yaml
│   ├── up.ps1                Levanta toda la solución
│   └── down.ps1              La elimina
├── Grafana/                  Tablero exportado
├── Power BI/                 Proyecto en formato .pbip
└── docs/                     Diagramas y evidencias
```

## Requisitos del equipo anfitrión

- Windows 10/11 con PowerShell.
- **Docker Desktop** con Kubernetes activado (distribución de un solo nodo `docker-desktop`).
- `kubectl` en el PATH.
- **Memoria:** se recomiendan 8 GB de RAM o más. Con 4 GB el clúster se vuelve inestable (cortes del API, reinicios de pods). Si es tu caso, limita WSL con un `.wslconfig` y cierra otros programas.
- Python 3.12 y PostgreSQL (cliente y servidor local) solo para preparar los datos (ver más abajo).
- `zstd` para descomprimir la base.
- DBeaver y Power BI Desktop para consultar y construir el tablero analítico.

## Datos: descarga y verificación

Los datos **no** están en este repositorio (la base descomprimida pesa unos 4,4 GB).

1. Descarga desde el registro oficial de Zenodo: <https://zenodo.org/records/21436223> (DOI [10.5281/zenodo.21436223](https://doi.org/10.5281/zenodo.21436223)). Solo se necesitan:
   - `opencem-v1.0.0.sqlite.zst` (302 MB)
   - `opencem-v1.0.0-support.zip` (10 MB)
   - `opencem-v1.0.0-SHA256SUMS.txt`
   - `README.md` y `LICENSE-DATA.txt`
2. Verifica la integridad:
   ```powershell
   Get-FileHash .\opencem-v1.0.0.sqlite.zst -Algorithm SHA256
   Get-Content .\opencem-v1.0.0-SHA256SUMS.txt
   ```
   Los hashes deben coincidir.
3. Descomprime la base (herramienta: Zstandard 1.5.7, instalada con `winget install --id Meta.Zstandard -e`):
   ```powershell
   zstd -d opencem-v1.0.0.sqlite.zst -o opencem-v1.0.0.sqlite
   ```
4. Inventario del contenido (tablas, columnas, filas y periodo):
   ```powershell
   python etl/inventario.py
   ```

El archivo `.sqlite` es la capa Bronze de origen y no se modifica.

## Reproducir la solución desde cero

### 1. Preparar Bronze en un PostgreSQL local (una sola vez)

1. Crea un archivo `.env` en la raíz a partir de `.env.example` y completa las variables `PG*` de tu PostgreSQL local.
2. Crea las tablas con el DDL de `sql/`.
3. Carga Bronze desde el SQLite:
   ```powershell
   pip install -r etl/requirements.txt
   python etl/02_extraer_a_bronze.py
   ```

### 2. Generar el volcado (`data/solarbi.dump`)

El volcado se usa para cargar los datos en el PostgreSQL del clúster. No se sube a GitHub por su tamaño (la carpeta `data/` está en el `.gitignore`).

Si tienes Bronze en tu PostgreSQL local:

```powershell
New-Item -ItemType Directory -Force data | Out-Null
pg_dump -h localhost -U <usuario> -d <base> -Fc -f data/solarbi.dump
```

Si ya tienes un clúster cargado, puedes extraerlo del pod:

```powershell
cmd /c "kubectl exec -n solarbi postgres-0 -- pg_dump -U solarbi -d solarbi -Fc > data\solarbi.dump"
```

El `up.ps1` restaura el volcado dentro del pod de PostgreSQL 16, así que **el volcado debe haberse generado con `pg_dump` de la versión 16** (o inferior). Un volcado de una versión mayor no se puede restaurar.

### 3. Crear las credenciales del clúster

```powershell
copy k8s\secrets.example.yaml k8s\secrets.local.yaml
```

Edita `k8s/secrets.local.yaml` y cambia las claves por las tuyas. Este archivo está en el `.gitignore` y no debe subirse.

### 4. Construir las imágenes propias

```powershell
docker compose --profile etl build etl
docker compose --profile sim build simulator
```

Las imágenes se construyen en el mismo Docker que usa el clúster de Docker Desktop, así que el clúster las ve sin necesidad de un registro. Los manifiestos usan `imagePullPolicy: IfNotPresent`.

### 5. Levantar y eliminar (un solo comando cada uno)

```powershell
powershell -ExecutionPolicy Bypass -File k8s/up.ps1
powershell -ExecutionPolicy Bypass -File k8s/down.ps1
```

`up.ps1` aplica los manifiestos en orden, espera a PostgreSQL, restaura los datos, espera a que termine el Job del ETL y activa el simulador. Tarda entre 15 y 20 minutos. `down.ps1` elimina el namespace, y con él el volumen de PostgreSQL.

### 6. Acceso desde el anfitrión

| Servicio | Dirección |
|---|---|
| Grafana | <http://localhost:30300> (usuario `admin` y la clave de `GRAFANA_ADMIN_PASSWORD`) |
| PostgreSQL (DBeaver y Power BI) | `localhost:30432`, base `solarbi`, usuario `solarbi` |

Si el NodePort no responde en tu equipo, usa un túnel:

```powershell
kubectl port-forward -n solarbi svc/grafana 3000:3000
kubectl port-forward -n solarbi svc/postgres 5433:5432
```

### 7. Demostración de resiliencia

```powershell
# PostgreSQL: los datos siguen después de borrar el pod
kubectl delete pod postgres-0 -n solarbi
kubectl exec -n solarbi postgres-0 -- psql -U solarbi -d solarbi -c "SELECT COUNT(*) FROM bronze.analog_measurements;"

# Grafana: vuelve con su tablero, su fuente de datos y sus alertas
kubectl delete pod -n solarbi -l app=grafana
```

### Desarrollo local sin Kubernetes

`docker-compose.yml` define PostgreSQL, el ETL, el simulador y Grafana con versiones fijas. Los servicios se ejecutan por perfiles (`etl`, `sim`, `grafana`) para no arrancar todo a la vez:

```powershell
docker compose --profile etl run --rm etl
docker compose --profile sim run --rm simulator
```

Ojo: el servicio `postgres` del compose usa el puerto 5432 y choca con un PostgreSQL local que ya lo ocupe.

## Configuración y credenciales

- **Credenciales:** nunca van en las imágenes ni en el repositorio. En Kubernetes viven en el Secret `solarbi-secrets`, que se crea desde `k8s/secrets.local.yaml` (ignorado por Git). Se versiona solo la plantilla `k8s/secrets.example.yaml`. En desarrollo local se usa un `.env` ignorado por Git.
- **Parámetros no sensibles** (`k8s/02-configmap.yaml`), que se pueden cambiar sin reconstruir imágenes:

| Variable | Uso |
|---|---|
| `TZ_SITIO` | Zona horaria usada para definir el día y la hora del sitio |
| `TARIFA_COP_KWH` | Tarifa en COP/kWh para el ahorro y el costo de la red |
| `UMBRAL_HUECO_S` | Segundos sin lecturas a partir de los cuales se registra un hueco de datos |
| `LOOP_S`, `PROB_ANOMALIA`, `SOC_ANOMALO` | Comportamiento del simulador |
| `PICO_W_INV1`, `PICO_W_INV2` | Potencia pico simulada de cada inversor |

- Grafana carga por provisioning su fuente de datos, su tablero y sus reglas de alerta, sin configuración manual en la interfaz.

## Calidad de datos y resultados del ETL

Fuente: 2.989.759 filas en `analog_measurements`, de dos inversores, del 12 de julio de 2025 al 13 de julio de 2026.

| Regla | Antes | Afectadas | Después |
|---|---:|---:|---:|
| R1 lectura vacía (se elimina) | 2.989.759 | 55.661 | 2.934.098 |
| R2 duplicados al milisegundo (se conserva la primera) | 2.934.098 | 20.356 | 2.913.742 |
| R3 voltaje de batería en 0 (se anula el valor) | 2.913.742 | 3 | 2.913.742 |
| R4 SoC fuera de 0-100 % | 2.913.742 | 0 | 2.913.742 |
| R5 potencia solar negativa | 2.913.742 | 0 | 2.913.742 |
| R6 potencia de línea negativa (se fija en 0) | 2.913.742 | 9 | 2.913.742 |
| R7 temperatura implausible | 2.913.742 | 38 | 2.913.742 |

- **Conciliación:** las 2.913.742 filas limpias coinciden con la suma de lecturas de Silver (166.758 bloques de 5 minutos).
- **Gold:** 642 filas en `fact_energia_diaria` y 25.205 en `fact_eventos`.
- **Idempotencia:** el ETL vacía y reconstruye Silver y Gold en cada ejecución. Se ejecutó varias veces, en el equipo local, en Docker y como Job de Kubernetes, con resultados idénticos.
- **Energía solar diaria:** se calcula integrando la potencia (`pv1power`) por bloques de 5 minutos. El contador `pvgeneratenergytoday` se usa solo como validación cruzada, porque se reinicia a horas irregulares y repite valores entre días.
- **CO₂ evitado (kg)** = energía solar (kWh) × factor de emisión del SIN (kgCO₂e/kWh).

## Supuestos y limitaciones

- **Zona horaria:** el valor por defecto (`Asia/Shanghai`) es un supuesto deducido del perfil de producción solar. Debe confirmarse con la documentación de soporte de OpenCEM.
- **Factor de emisión del SIN:** los valores de `dim_factor_emision` están sin verificar contra la fuente oficial (UPME). La telemetría es de 2025 y 2026 y se usa el factor del año más cercano disponible.
- **Tarifa:** se usa una sola tarifa en COP/kWh para todo el periodo.
- **Integración contra contador:** en los días con cobertura casi completa, la energía integrada difiere del contador (error medio diario de 1,02 kWh en el inversor 1 y 0,76 kWh en el inversor 2).
- **Eventos:** `fact_eventos` contiene anotaciones de contexto y huecos de datos. No incluye alarmas, apagados ni batería baja, porque no se cargó `fault_history`.
- **Performance Ratio:** no se puede calcular, porque la fuente no trae irradiancia ni variables meteorológicas.
- **Inversores:** el inversor 2 deja de producir casi por completo desde abril de 2026, mientras el 1 aumenta. Con esta fuente no se puede saber la causa. No se deben sumar los dos sin más.
- **Datos simulados:** las lecturas del simulador son sintéticas y solo sirven para demostrar el tablero y las alertas. Un nuevo ciclo del ETL las elimina.

## Cita de los datos y licencia

Los datos provienen de **OpenCEM v1.0.0** y se publican bajo licencia **Creative Commons Attribution 4.0 (CC BY 4.0)**. Cita:

> **[AUTORES: copiar del registro de Zenodo]**. *OpenCEM v1.0.0* [conjunto de datos]. Zenodo. <https://doi.org/10.5281/zenodo.21436223>

Artículo de los autores: arXiv:2604.05429. Repositorio complementario: <https://github.com/OpenCEM-platform/opencem-dataset>.

Los datos se transformaron en este proyecto (limpieza, agregación a bloques de 5 minutos y modelado dimensional). Esos cambios son responsabilidad de este equipo y no de los autores de OpenCEM.

El código de este repositorio es de uso académico para el Taller 6.
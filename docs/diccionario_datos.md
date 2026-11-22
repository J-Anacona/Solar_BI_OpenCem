## Unidades (con evidencia)

| Variable | Unidad | Evidencia |
|---|---|---|
| `pv1power` | W | La integración (W × h / 1000) coincide con `pvgeneratenergytoday` en días con cobertura completa (ej. 11,37 vs 11,3 kWh). |
| `pvgeneratenergytoday` | kWh | Misma comparación. |
| `battsoc` | % | Rango esperado 0-100 **(confirmar)**. |
| `outsumw`, `gridpowerw_a` | W | Sufijo `w` y magnitudes similares a `pv1power` **(confirmar)**. |
| `linevolta` | V | Magnitud típica de red **(confirmar)**. |
| `linefreq` | Hz | Magnitud típica ~50/60 **(confirmar)**. |

### `gold.fact_telemetria`

**Grano:** inversor × intervalo de 5 min.  
**Proceso:** monitoreo operativo.

| Columna | Tipo | Llave | Regla de transformación | Origen |
|---|---|---|---|---|
| `fecha_key` | INTEGER | PK, FK dim_fecha | yyyymmdd del intervalo según `TZ_OFFSET_HORAS` | `analog_measurements.read_ts` |
| `hora_key` | SMALLINT | PK, FK dim_hora | hora × 60 + minuto del intervalo | `read_ts` |
| `inversor_key` | SMALLINT | PK, FK dim_inversor | Igual a `inverter` | `inverter` |
| `calidad_key` | SMALLINT | FK dim_calidad_dato | VALIDO / NULO / SIN_TELEMETRIA / FUERA_RANGO | Regla de calidad |
| `pot_solar_w` | REAL | | Promedio en 5 min | `pv1power` |
| `pot_carga_w` | REAL | | Promedio en 5 min | `outsumw` |
| `pot_red_w` | REAL | | Promedio en 5 min | `gridpowerw_a`  |
| `soc_pct` | REAL | | Promedio en 5 min | `battsoc` |
| `volt_red_v` | REAL | | Promedio en 5 min | `linevolta` |
| `freq_red_hz` | REAL | | Promedio en 5 min | `linefreq` |
| `n_lecturas` | INTEGER | | Conteo de lecturas del intervalo | Calculado |

### `gold.fact_energia_diaria`

**Grano:** inversor × día.  
**Procesos:** balance energético y CO₂.

| Columna | Tipo | Llave | Regla de transformación | Origen |
|---|---|---|---|---|
| `fecha_key` | INTEGER | PK, FK | Día según `TZ_OFFSET_HORAS` | `read_ts` |
| `inversor_key` | SMALLINT | PK, FK | | `inverter` |
| `factor_emision_key` | INTEGER | FK | Factor vigente del año de la fecha | `dim_factor_emision` |
| `calidad_key` | SMALLINT | FK | Peor calidad del día | Regla de calidad |
| `energia_solar_kwh` | NUMERIC(10,3) | | Σ `pv1power` × Δt / 1000, con Δt máximo 5 min | `pv1power` |
| `energia_carga_kwh` | NUMERIC(10,3) | | Σ potencia de carga × Δt / 1000 | `outsumw`  |
| `energia_red_kwh` | NUMERIC(10,3) | | Σ potencia de red × Δt / 1000 | `gridpowerw_a`  |
| `bateria_carga_kwh` / `bateria_descarga_kwh` | NUMERIC(10,3) | | Integración de la potencia de batería, separando signo | `battsumpower` / `battchgpower` |
| `co2_evitado_kg` | NUMERIC(10,3) | | `energia_solar_kwh` × `factor_kgco2_kwh` | Calculado |
| `ahorro_cop` | NUMERIC(14,2) | | `energia_solar_kwh` × tarifa COP/kWh | Calculado (tarifa en ConfigMap) |
| `pct_datos_validos` | NUMERIC(5,2) | | Lecturas válidas / lecturas totales × 100 | Calculado |
| `disponibilidad_pct` | NUMERIC(5,2) | | Intervalos de 5 min con datos / intervalos esperados × 100 | Calculado |
| `n_lecturas` | INTEGER | | Conteo de lecturas del día | Calculado |

### `gold.fact_eventos`

**Grano:** un evento por inversor.  
**Proceso:** alarmas, apagados, batería baja.

| Columna | Tipo | Llave | Regla de transformación | Origen |
|---|---|---|---|---|
| `evento_id` | BIGSERIAL | PK | Autogenerado | |
| `fecha_key`, `hora_key` | INTEGER, SMALLINT | FK | Del inicio del evento | `fault_history` / `status` |
| `inversor_key` | SMALLINT | FK | | `inverter` |
| `tipo_evento_key` | SMALLINT | FK | Clasificación según código de falla, estado o SOC bajo el umbral | `fault_history`, `status`, `battsoc` |
| `inicio_ts` | TIMESTAMPTZ | UNIQUE con inversor y tipo | Instante de inicio | `faulthistoryrecordNN_time` |
| `duracion_min` | NUMERIC(10,2) | | Fin menos inicio (nulo si no hay fin) | Calculado |
| `detalle` | JSONB | | Texto original del registro | `faulthistoryrecordNN` |

### Dimensiones

| Tabla | Columnas | Llave | Origen / regla |
|---|---|---|---|
| `dim_fecha` | fecha_key, fecha, anio, trimestre, mes, nombre_mes, semana, dia, dia_semana | PK fecha_key | Generada con `generate_series` (no existe en la fuente). |
| `dim_hora` | hora_key, hora, minuto, franja | PK hora_key | Generada; franja por rango horario. |
| `dim_inversor` | inversor_key, inversor_id, nombre, subsistema | PK inversor_key | Valores 1 y 2 de `inverter`. |
| `dim_calidad_dato` | calidad_key, codigo, descripcion | PK calidad_key | Construida por el equipo. |
| `dim_factor_emision` | factor_emision_key, anio, factor_kgco2_kwh, fuente, vigente_desde, vigente_hasta, es_actual | PK factor_emision_key | Construida por el equipo; valor oficial UPME/XM pendiente. |
| `dim_tipo_evento` | tipo_evento_key, codigo, descripcion, severidad | PK tipo_evento_key | Construida por el equipo. |

### Capas previas

| Tabla | Descripción | Origen |
|---|---|---|
| `bronze.context` | JSON de contexto en `jsonb` | SQLite `context` (`recorded`, `start`, `end` pasan de epoch a TIMESTAMPTZ). |
| `silver.telemetria_5min` | Telemetría limpia a 5 min por inversor | SQLite `analog_measurements`. |
| `silver.etl_log` | Conteos antes y después de cada regla | Generada por el ETL |
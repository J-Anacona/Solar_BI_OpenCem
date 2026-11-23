# k8s/up.ps1 - levanta toda la solucion desde cero (ejecutar desde la raiz del repo)
$ns = "solarbi"; $pgUser = "solarbi"; $pgDb = "solarbi"; $dump = "data\solarbi.dump"

function Paso($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Ok($m)   { if ($LASTEXITCODE -ne 0) { Write-Host "FALLO: $m" -ForegroundColor Red; exit 1 } }
function Tiene-Datos {
    "$(kubectl exec -n $ns postgres-0 -- psql -U $pgUser -d $pgDb -tAc "SELECT to_regclass('bronze.analog_measurements') IS NOT NULL")".Trim() -eq "t"
}

if (-not (Test-Path "k8s/secrets.local.yaml")) { Write-Host "Falta k8s/secrets.local.yaml" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $dump)) { Write-Host "Falta $dump (ver README: como generar el volcado)" -ForegroundColor Red; exit 1 }

Paso "1/6 Namespace, Secret y ConfigMap"
kubectl apply -f k8s/00-namespace.yaml;  Ok "namespace"
kubectl apply -f k8s/secrets.local.yaml; Ok "secret"
kubectl apply -f k8s/02-configmap.yaml;  Ok "configmap"

Paso "2/6 PostgreSQL (StatefulSet + volumen persistente)"
kubectl apply -f k8s/03-postgres.yaml;   Ok "postgres"
kubectl rollout status statefulset/postgres -n $ns --timeout=600s; Ok "espera de postgres"

Paso "3/6 Datos historicos (restauracion del volcado dentro del pod, tarda varios minutos)"
if (Tiene-Datos) {
    Write-Host "La base ya tiene datos; se omite la restauracion."
} else {
    cmd /c "kubectl exec -i -n $ns postgres-0 -- pg_restore -U $pgUser -d $pgDb --no-owner --no-privileges < $dump"
    if (-not (Tiene-Datos)) { Write-Host "FALLO: la restauracion no dejo las tablas" -ForegroundColor Red; exit 1 }
    kubectl exec -n $ns postgres-0 -- psql -U $pgUser -d $pgDb -tAc "SELECT 'filas en bronze.analog_measurements: ' || COUNT(*) FROM bronze.analog_measurements"
}

Paso "4/6 Grafana (provisioning de datasource, dashboard y alertas)"
kubectl apply -f k8s/04-grafana.yaml;    Ok "grafana"

Paso "5/6 ETL historico (Job); tarda unos minutos"
kubectl delete job etl-historico -n $ns --ignore-not-found | Out-Null
kubectl apply -f k8s/05-etl-job.yaml;    Ok "job etl"
kubectl wait --for=condition=complete job/etl-historico -n $ns --timeout=1200s; Ok "el ETL no termino bien"

Paso "6/6 Simulador (CronJob) y estado final"
kubectl apply -f k8s/06-simulator-cronjob.yaml; Ok "cronjob"
kubectl rollout status deployment/grafana -n $ns --timeout=600s
kubectl get pods,svc,cronjob,job,pvc -n $ns
Write-Host "`nGrafana: http://localhost:30300   |   PostgreSQL: localhost:30432" -ForegroundColor Green
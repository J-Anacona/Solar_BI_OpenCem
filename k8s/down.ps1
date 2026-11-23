# k8s/down.ps1 - elimina toda la solucion (incluye el volumen de PostgreSQL)
kubectl delete namespace solarbi --wait=true
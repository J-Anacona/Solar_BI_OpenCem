# 9 Descarga de datos

# comandos utilizados
Get-Content .\opencem-v1.0.0-SHA256SUMS.txt
Get-FileHash .\opencem-v1.0.0.sqlite.zst -Algorithm SHA256
Get-FileHash .\opencem-v1.0.0-support.zip -Algorithm SHA256

# Resultados
033f94ce388117c5a7076dc0a083f9c66e466ab94aa7a977784751bec4568ba9  README.md
3ca7e024062b6490ac4b604bb05d07012501166ee6a4cb441523b9983a5fd29b  opencem-v1.0.0-sky-2026-03.tar.zst
ee3cf915514bc170cc65fb92eb47d901c56db1054087aef537c7153980634869  opencem-v1.0.0-sky-2026-04.tar.zst
5a261a850a635c21d53a6a3c85ca247754860f6400c416ab75cd9111dae32867  opencem-v1.0.0-sky-2026-05.tar.zst
ed2146498e1487d25c2b8c9a0176f69d0c2bff5f7bd3bb1e1be14ceec8bdda65  opencem-v1.0.0-sky-2026-06.tar.zst
e707d26ce2549536813414320cf057c0035be7f354be01a294c764931e9b7b0d  opencem-v1.0.0-sky-2026-07.tar.zst
5debdbebb82ed784e1c11ac70c81fe876400a049a001a8dc2230446e2f460439  opencem-v1.0.0-support.zip
8e38f98209029367a3775799ee9a7c0757cc7e8f2742e4df4eccc45dd4b27517  opencem-v1.0.0.sqlite.zst

PS C:\Users\John\Downloads\OpenCem-descargas> Get-FileHash .\opencem-v1.0.0.sqlite.zst -Algorithm SHA256

Algorithm       Hash                                                                   Path                                                                   
---------       ----                                                                   ----                                                                   
SHA256          8E38F98209029367A3775799EE9A7C0757CC7E8F2742E4DF4ECCC45DD4B27517       C:\Users\John\Downloads\OpenCem-descargas\opencem-v1.0.0.sqlite.zst  


PS C:\Users\John\Downloads\OpenCem-descargas> Get-FileHash .\opencem-v1.0.0-support.zip -Algorithm SHA256

Algorithm       Hash                                                                   Path                                                                   
---------       ----                                                                   ----                                                                   
SHA256          5DEBDBEBB82ED784E1C11AC70C81FE876400A049A001A8DC2230446E2F460439       C:\Users\John\Downloads\OpenCem-descargas\opencem-v1.0.0-support.zip 


# Comando utilziado para descomprimir el archivo 

# Terminal de powershell
zstd.exe -d opencem-v1.0.0.sqlite.zst -o opencem-v1.0.0.sqlite

Archivo	Tamaño (bytes)	Tamaño aprox.
opencem-v1.0.0.sqlite.zst (comprimido)	302.059.978	288 MiB (302,1 MB)
opencem-v1.0.0.sqlite (descomprimido)	4.439.408.640	4,13 GiB (4,44 GB)



# imagen docker Listo en 196 s
PS C:\Users\John\Downloads\Solar_BI_OpenCem> docker images solarbi-etl
                                                                                                                                           i Info →   U  In UseIMAGE             ID             DISK USAGE   CONTENT SIZE   EXTRA
solarbi-etl:1.0   9ffb21af9bfe        202MB         49.9MB        
PS C:\Users\John\Downloads\Solar_BI_OpenCem> 


# docker images

PS C:\Users\John\Downloads\Solar_BI_OpenCem> docker compose --profile sim build --no-cache simulator
[+] Building 29.8s (12/12) FINISHED                                                                                                               
 => [internal] load local bake definitions                                                                                                   0.1s
 => => reading from stdin 601B                                                                                                               0.1s
 => [internal] load build definition from Dockerfile                                                                                         0.5s
 => => transferring dockerfile: 250B                                                                                                         0.4s
 => [internal] load metadata for docker.io/library/python:3.12-slim                                                                          0.7s
 => [internal] load .dockerignore                                                                                                            0.2s
 => => transferring context: 88B                                                                                                             0.1s
 => [1/5] FROM docker.io/library/python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b                    0.2s
 => => resolve docker.io/library/python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b                    0.2s
 => [internal] load build context                                                                                                            0.1s
 => => transferring context: 3.90kB                                                                                                          0.1s
 => CACHED [2/5] WORKDIR /app                                                                                                                0.0s
 => [3/5] COPY etl/requirements.txt .                                                                                                        0.3s
 => [5/5] COPY simulator/simulador.py .                                                                                                      0.4s
 => exporting to image                                                                                                                       4.5s
 => => exporting layers                                                                                                                      2.6s
 => => exporting manifest sha256:e22e434d895491a016bd7af911ed8a4bb762be24a2c3dc22e65475117ed560cd                                            0.1s
 => => exporting config sha256:9aac32130ba8b692a19baab851fb40b6424130bb0ff2e33e9724b8ce6a2eec49                                              0.1s
 => => exporting attestation manifest sha256:ab2e9680e9342b28aac76e68d8069e3869388cace23fc0f313ac63754365aa85                                0.1s
 => => exporting manifest list sha256:d0eb30e11c8e361a7c673a4dde42d6f5ee9215c7c70c5654c0cae228487936bb                                       0.1s
 => => naming to docker.io/library/solarbi-simulator:1.0                                                                                     0.1s
 => => unpacking to docker.io/library/solarbi-simulator:1.0                                                                                  1.1s
 => resolving provenance for metadata file                                                                                                   0.5s
[+] build 1/1
 ✔ Image solarbi-simulator:1.0 Built                                                                                                         30.8sPS C:\Users\John\Downloads\Solar_BI_OpenCem> docker compose --profile sim run --rm --no-deps simulator
Container solar_bi_opencem-simulator-run-76d29881e08b Creating 
Container solar_bi_opencem-simulator-run-76d29881e08b Created 
[sim] inv=1 pv=  53.9 W  soc=100.0 %  carga=467.6 W
[sim] inv=2 pv=  73.3 W  soc= 88.3 %  carga=338.9 W
PS C:\Users\John\Downloads\Solar_BI_OpenCem> 



# 
PS C:\Users\John\Downloads\Solar_BI_OpenCem> kubectl get pods,pvc,svc -n solarbi                                   
NAME             READY   STATUS    RESTARTS   AGE
pod/postgres-0   1/1     Running   0          67s

NAME                                    STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   VOLUMEATTRIBUTESCLASS   AGE
persistentvolumeclaim/data-postgres-0   Bound    pvc-b3cb31c7-1b0b-4409-b7b7-901dfeb3595a   10Gi       RWO            hostpath       <unset>                 68s

NAME                       TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)          AGE
service/postgres           ClusterIP   10.111.182.101   <none>        5432/TCP         70s
service/postgres-externo   NodePort    10.103.133.22    <none>        5432:30432/TCP   69s
PS C:\Users\John\Downloads\Solar_BI_OpenCem> 










PS C:\Users\John\Downloads\Solar_BI_OpenCem> kubectl describe job etl-historico -n solarbi
Name:             etl-historico
Namespace:        solarbi
Selector:         batch.kubernetes.io/controller-uid=f35e4a9e-b8b8-445d-9be8-330f00e96f60
Labels:           batch.kubernetes.io/controller-uid=f35e4a9e-b8b8-445d-9be8-330f00e96f60
                  batch.kubernetes.io/job-name=etl-historico
                  controller-uid=f35e4a9e-b8b8-445d-9be8-330f00e96f60
                  job-name=etl-historico
Annotations:      <none>
Parallelism:      1
Completions:      1
Completion Mode:  NonIndexed
Suspend:          false
Backoff Limit:    1
Start Time:       Sun, 22 Nov 2026 13:13:40 -0500
Pods Statuses:    1 Active (0 Ready) / 0 Succeeded / 0 Failed
Pod Template:
  Labels:  batch.kubernetes.io/controller-uid=f35e4a9e-b8b8-445d-9be8-330f00e96f60
           batch.kubernetes.io/job-name=etl-historico
           controller-uid=f35e4a9e-b8b8-445d-9be8-330f00e96f60
           job-name=etl-historico
  Containers:
   etl:
    Image:      solarbi-etl:1.0
    Port:       <none>
    Host Port:  <none>
    Limits:
      cpu:     500m
      memory:  512Mi
    Requests:
      cpu:     100m
      memory:  256Mi
    Environment Variables from:
      solarbi-config  ConfigMap  Optional: false
    Environment:
      PGUSER:      <set to the key 'POSTGRES_USER' in secret 'solarbi-secrets'>      Optional: false
      PGPASSWORD:  <set to the key 'POSTGRES_PASSWORD' in secret 'solarbi-secrets'>  Optional: false
    Mounts:        <none>
  Volumes:         <none>
  Node-Selectors:  <none>
  Tolerations:     <none>
Events:
  Type    Reason            Age   From            Message
  ----    ------            ----  ----            -------
  Normal  SuccessfulCreate  11m   job-controller  Created pod: etl-historico-frsfm
PS C:\Users\John\Downloads\Solar_BI_OpenCem> 




PS C:\Users\John\Downloads\Solar_BI_OpenCem> kubectl get pods -n solarbi
NAME                  READY   STATUS      RESTARTS   AGE
etl-historico-frsfm   0/1     Completed   0          12m
postgres-0            1/1     Running     0          50m
PS C:\Users\John\Downloads\Solar_BI_OpenCem> 
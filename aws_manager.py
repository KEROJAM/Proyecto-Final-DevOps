#!/usr/bin/env python3
"""
aws_manager.py - Automatización de tareas AWS con Boto3
Soluciones Tecnológicas del Futuro

Funciones:
  - Aprovisionar instancias EC2 (máx. 9 en total, límite Learner Lab)
  - Listar buckets S3 y sus objetos
  - Subir archivos a buckets S3
  - Generar reporte de uso de recursos en CSV
  - Obtener métricas de CloudWatch para instancias EC2
  - Gestionar reglas de Auto Scaling en EC2
"""

import boto3
import csv
import json
from datetime import datetime, timezone, timedelta

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
REGION         = "us-east-1"
MAX_INSTANCIAS = 9           # Límite Learner Lab
REPORTE_CSV    = "reporte_recursos.csv"

def pedir_configuracion() -> dict:
    """
    Solicita al usuario los valores de configuración necesarios para EC2.

    La AMI ID NO se hardcodea porque:
      - Cambia según la región (us-east-1, us-west-2, etc.)
      - AWS la actualiza periódicamente con nuevas versiones
      - En el Learner Lab puede diferir de la documentación general

    Cómo obtener tu AMI ID en el Learner Lab:
      1. Abre la consola AWS → EC2 → Launch Instance
      2. En 'Application and OS Images' busca 'Ubuntu' o 'Amazon Linux 2'
      3. Copia el valor 'ami-xxxxxxxxxxxxxxxxx' que aparece debajo del nombre
    """
    print("\n" + "="*50)
    print("  Configuración inicial")
    print("="*50)
    print("  (Presiona Enter para aceptar el valor por defecto)\n")

    print("  Dónde obtener la AMI ID:")
    print("  Consola AWS → EC2 → Launch Instance → Application and OS Images")
    print("  Copia el valor 'ami-xxxxxxxxxxxxxxxxx' de la imagen que elijas.\n")

    ami = input("  AMI ID (ej: ami-0c02fb55956c7d316): ").strip()
    while not ami.startswith("ami-"):
        print("  La AMI ID debe comenzar con 'ami-'")
        ami = input("  AMI ID: ").strip()

    tipo = input("  Tipo de instancia [t2.micro]: ").strip() or "t2.micro"
    key  = input("  Nombre del Key Pair [vockey]: ").strip() or "vockey"

    print(f"\n  Región:    {REGION}")
    print(f"  AMI ID:    {ami}")
    print(f"  Tipo:      {tipo}")
    print(f"  Key Pair:  {key}")
    print(f"  Límite:    {MAX_INSTANCIAS} instancias\n")

    return {"ami": ami, "tipo": tipo, "key": key}


# ─── CLIENTES AWS ─────────────────────────────────────────────────────────────
ec2        = boto3.client("ec2",        region_name=REGION)
s3         = boto3.client("s3",         region_name=REGION)
cloudwatch = boto3.client("cloudwatch", region_name=REGION)
autoscaling = boto3.client("autoscaling", region_name=REGION)


# ══════════════════════════════════════════════════════════════════════════════
# EC2
# ══════════════════════════════════════════════════════════════════════════════

def contar_instancias_activas() -> int:
    """Retorna el número de instancias EC2 que NO están terminadas."""
    resp = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name",
                  "Values": ["pending", "running", "stopping", "stopped"]}]
    )
    total = sum(len(r["Instances"]) for r in resp["Reservations"])
    return total


def aprovisionar_instancia(config: dict, nombre: str, cantidad: int = 1) -> list:
    """
    Lanza 'cantidad' instancias EC2 con el nombre dado.
    Respeta el límite de MAX_INSTANCIAS del Learner Lab.
    """
    activas     = contar_instancias_activas()
    disponibles = MAX_INSTANCIAS - activas

    if disponibles <= 0:
        print(f"[EC2] Límite alcanzado: {activas}/{MAX_INSTANCIAS} instancias activas.")
        return []

    cantidad = min(cantidad, disponibles)
    print(f"[EC2] Lanzando {cantidad} instancia(s) '{nombre}' "
          f"({activas} activas, límite {MAX_INSTANCIAS})...")

    resp = ec2.run_instances(
        ImageId=config["ami"],
        InstanceType=config["tipo"],
        MinCount=cantidad,
        MaxCount=cantidad,
        KeyName=config["key"],
        TagSpecifications=[{
            "ResourceType": "instance",
            "Tags": [
                {"Key": "Name",     "Value": nombre},
                {"Key": "Proyecto", "Value": "STF-DevOps"},
            ]
        }],
        IamInstanceProfile={"Name": "LabInstanceProfile"},  # LabRole
    )

    ids = [i["InstanceId"] for i in resp["Instances"]]
    print(f"[EC2] Instancias creadas: {ids}")
    return ids


def listar_instancias() -> list:
    """Lista todas las instancias EC2 con su estado y nombre."""
    resp       = ec2.describe_instances()
    instancias = []

    for reserva in resp["Reservations"]:
        for inst in reserva["Instances"]:
            nombre = next(
                (t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"),
                "sin-nombre"
            )
            instancias.append({
                "id":         inst["InstanceId"],
                "nombre":     nombre,
                "tipo":       inst["InstanceType"],
                "estado":     inst["State"]["Name"],
                "ip_publica": inst.get("PublicIpAddress", "N/A"),
                "lanzada":    str(inst["LaunchTime"]),
            })

    return instancias


def detener_instancia(instance_id: str):
    """Detiene (stop) una instancia EC2."""
    ec2.stop_instances(InstanceIds=[instance_id])
    print(f"[EC2] Instancia {instance_id} detenida.")


def terminar_instancia(instance_id: str):
    """Termina (elimina) una instancia EC2."""
    ec2.terminate_instances(InstanceIds=[instance_id])
    print(f"[EC2] Instancia {instance_id} terminada.")


# ══════════════════════════════════════════════════════════════════════════════
# S3
# ══════════════════════════════════════════════════════════════════════════════

def listar_buckets() -> list:
    """Lista todos los buckets S3 de la cuenta."""
    resp    = s3.list_buckets()
    buckets = [b["Name"] for b in resp.get("Buckets", [])]
    print(f"[S3] Buckets encontrados: {len(buckets)}")
    return buckets


def listar_objetos(bucket: str, prefijo: str = "") -> list:
    """Lista objetos dentro de un bucket S3."""
    objetos   = []
    paginator = s3.get_paginator("list_objects_v2")

    for pagina in paginator.paginate(Bucket=bucket, Prefix=prefijo):
        for obj in pagina.get("Contents", []):
            objetos.append({
                "bucket":     bucket,
                "clave":      obj["Key"],
                "tamanio_kb": round(obj["Size"] / 1024, 2),
                "modificado": str(obj["LastModified"]),
            })

    print(f"[S3] {len(objetos)} objeto(s) en '{bucket}/{prefijo}'")
    return objetos


def crear_bucket(nombre: str) -> bool:
    """Crea un bucket S3."""
    try:
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=nombre)
        else:
            s3.create_bucket(
                Bucket=nombre,
                CreateBucketConfiguration={"LocationConstraint": REGION}
            )
        print(f"[S3] Bucket '{nombre}' creado.")
        return True
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"[S3] El bucket '{nombre}' ya existe y es tuyo.")
        return True
    except Exception as e:
        print(f"[S3] Error al crear bucket: {e}")
        return False


def subir_archivo(bucket: str, ruta_local: str, clave_s3: str = None) -> bool:
    """
    Sube un archivo local a un bucket S3.

    Si no se proporciona clave_s3, se usa el nombre del archivo local.
    """
    import os

    clave_s3 = clave_s3 or os.path.basename(ruta_local)

    if not os.path.isfile(ruta_local):
        print(f"[S3] El archivo '{ruta_local}' no existe.")
        return False

    try:
        s3.upload_file(ruta_local, bucket, clave_s3)
        print(f"[S3] Archivo subido: '{ruta_local}' → s3://{bucket}/{clave_s3}")
        return True
    except Exception as e:
        print(f"[S3] Error al subir archivo: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# CLOUDWATCH – MÉTRICAS DE EC2
# ══════════════════════════════════════════════════════════════════════════════

def obtener_metrica_ec2(instance_id: str, metrica: str,
                        minutos: int = 60) -> list:
    """
    Obtiene los puntos de datos de una métrica de CloudWatch
    para una instancia EC2 en los últimos N minutos.

    Métricas disponibles:
      - CPUUtilization      → uso de CPU en %
      - NetworkIn / NetworkOut → bytes de red entrantes/salientes
      - DiskReadBytes / DiskWriteBytes → bytes leídos/escritos en disco
      - StatusCheckFailed   → fallos de verificación de estado (0 o 1)
    """
    fin    = datetime.now(timezone.utc)
    inicio = fin - timedelta(minutes=minutos)

    resp = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName=metrica,
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=inicio,
        EndTime=fin,
        Period=300,          # punto cada 5 minutos
        Statistics=["Average", "Maximum"],
    )

    puntos = sorted(resp["Datapoints"], key=lambda x: x["Timestamp"])
    return puntos


def reporte_metricas_instancia(instance_id: str, minutos: int = 60):
    """
    Muestra un resumen de las métricas principales de una instancia EC2
    en los últimos N minutos.
    """
    metricas = [
        ("CPUUtilization",   "%"),
        ("NetworkIn",        "bytes"),
        ("NetworkOut",       "bytes"),
        ("DiskReadBytes",    "bytes"),
        ("DiskWriteBytes",   "bytes"),
        ("StatusCheckFailed","count"),
    ]

    print(f"\n[CloudWatch] Métricas de {instance_id} (últimos {minutos} min)")
    print("=" * 60)

    for nombre_metrica, unidad in metricas:
        try:
            puntos = obtener_metrica_ec2(instance_id, nombre_metrica, minutos)
            if not puntos:
                print(f"  {nombre_metrica:<25} Sin datos disponibles")
                continue

            ultimo  = puntos[-1]
            promedio = sum(p["Average"] for p in puntos) / len(puntos)
            maximo   = max(p["Maximum"] for p in puntos)

            print(f"  {nombre_metrica:<25} "
                  f"Promedio: {promedio:>10.2f} {unidad}  |  "
                  f"Máximo: {maximo:>10.2f} {unidad}")
        except Exception as e:
            print(f"  {nombre_metrica:<25} Error: {e}")

    print("=" * 60)


def reporte_metricas_todas_instancias(minutos: int = 60):
    """
    Genera un reporte de CPU para TODAS las instancias EC2 running
    y lo guarda en CSV.
    """
    instancias = [i for i in listar_instancias() if i["estado"] == "running"]

    if not instancias:
        print("[CloudWatch] No hay instancias en estado running.")
        return

    archivo = f"reporte_cloudwatch_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    filas   = []

    for inst in instancias:
        iid = inst["id"]
        print(f"[CloudWatch] Obteniendo métricas de {iid} ({inst['nombre']})...")

        fila = {
            "instance_id":  iid,
            "nombre":       inst["nombre"],
            "tipo":         inst["tipo"],
            "estado":       inst["estado"],
            "timestamp":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }

        for metrica, _ in [("CPUUtilization",""), ("NetworkIn",""),
                            ("NetworkOut",""), ("StatusCheckFailed","")]:
            try:
                puntos = obtener_metrica_ec2(iid, metrica, minutos)
                if puntos:
                    fila[f"{metrica}_avg"] = round(
                        sum(p["Average"] for p in puntos) / len(puntos), 2)
                    fila[f"{metrica}_max"] = round(
                        max(p["Maximum"] for p in puntos), 2)
                else:
                    fila[f"{metrica}_avg"] = "N/A"
                    fila[f"{metrica}_max"] = "N/A"
            except Exception:
                fila[f"{metrica}_avg"] = "ERROR"
                fila[f"{metrica}_max"] = "ERROR"

        filas.append(fila)

    campos = ["instance_id", "nombre", "tipo", "estado", "timestamp",
              "CPUUtilization_avg", "CPUUtilization_max",
              "NetworkIn_avg",      "NetworkIn_max",
              "NetworkOut_avg",     "NetworkOut_max",
              "StatusCheckFailed_avg", "StatusCheckFailed_max"]

    with open(archivo, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas)

    print(f"\n[CloudWatch] Reporte guardado en '{archivo}' ({len(filas)} instancias)")
    return archivo


# ══════════════════════════════════════════════════════════════════════════════
# AUTO SCALING
# Nota: el Learner Lab permite usar Auto Scaling Groups existentes.
# No se crean Launch Configurations nuevas para respetar los límites del Lab.
# ══════════════════════════════════════════════════════════════════════════════

def listar_grupos_autoscaling() -> list:
    """Lista todos los Auto Scaling Groups de la cuenta."""
    resp   = autoscaling.describe_auto_scaling_groups()
    grupos = []

    for g in resp["AutoScalingGroups"]:
        grupos.append({
            "nombre":       g["AutoScalingGroupName"],
            "min":          g["MinSize"],
            "max":          g["MaxSize"],
            "deseado":      g["DesiredCapacity"],
            "instancias":   len(g["Instances"]),
            "estado":       "activo" if g["Instances"] else "sin instancias",
        })

    if not grupos:
        print("[AutoScaling] No hay grupos de Auto Scaling configurados.")
    else:
        print(f"[AutoScaling] Grupos encontrados: {len(grupos)}")
        for g in grupos:
            print(f"  {g['nombre']}: min={g['min']} deseado={g['deseado']} "
                  f"max={g['max']} instancias={g['instancias']}")

    return grupos


def actualizar_capacidad_autoscaling(nombre_grupo: str,
                                     minimo: int,
                                     deseado: int,
                                     maximo: int):
    """
    Actualiza los valores de capacidad de un Auto Scaling Group existente.

    Restricciones del Learner Lab:
      - El total de instancias activas no puede superar 9
      - Solo se pueden modificar grupos existentes, no crear nuevos
    """
    # Validar que el total no supere el límite del Lab
    activas     = contar_instancias_activas()
    disponibles = MAX_INSTANCIAS - activas

    if deseado > disponibles + contar_instancias_autoscaling(nombre_grupo):
        print(f"[AutoScaling] No se puede escalar a {deseado} instancias.")
        print(f"  Activas totales: {activas}/{MAX_INSTANCIAS}")
        return False

    autoscaling.update_auto_scaling_group(
        AutoScalingGroupName=nombre_grupo,
        MinSize=minimo,
        MaxSize=maximo,
        DesiredCapacity=deseado,
    )
    print(f"[AutoScaling] Grupo '{nombre_grupo}' actualizado: "
          f"min={minimo} deseado={deseado} max={maximo}")
    return True


def contar_instancias_autoscaling(nombre_grupo: str) -> int:
    """Retorna cuántas instancias tiene actualmente un Auto Scaling Group."""
    resp = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[nombre_grupo]
    )
    if not resp["AutoScalingGroups"]:
        return 0
    return len(resp["AutoScalingGroups"][0]["Instances"])


def listar_politicas_scaling(nombre_grupo: str) -> list:
    """Lista las políticas de escalado de un Auto Scaling Group."""
    resp      = autoscaling.describe_policies(
        AutoScalingGroupName=nombre_grupo
    )
    politicas = []

    for p in resp["ScalingPolicies"]:
        politicas.append({
            "nombre":     p["PolicyName"],
            "tipo":       p.get("PolicyType", "N/A"),
            "ajuste":     p.get("ScalingAdjustment", "N/A"),
            "cooldown":   p.get("Cooldown", "N/A"),
            "arn":        p["PolicyARN"],
        })

    if not politicas:
        print(f"[AutoScaling] El grupo '{nombre_grupo}' no tiene políticas.")
    else:
        print(f"[AutoScaling] Políticas de '{nombre_grupo}':")
        for p in politicas:
            print(f"  {p['nombre']} | Tipo: {p['tipo']} | "
                  f"Ajuste: {p['ajuste']} | Cooldown: {p['cooldown']}s")

    return politicas


def crear_politica_scaling_cpu(nombre_grupo: str,
                               umbral_alto: float = 70.0,
                               umbral_bajo: float = 30.0):
    """
    Crea dos políticas de escalado basadas en CPU para un grupo existente:
      - Scale Out: agregar 1 instancia si CPU > umbral_alto por 2 periodos
      - Scale In:  quitar 1 instancia si CPU < umbral_bajo por 2 periodos

    Respeta el límite de 9 instancias del Learner Lab verificando el max
    del grupo antes de crear las políticas.
    """
    # Verificar que el grupo existe
    resp = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[nombre_grupo]
    )
    if not resp["AutoScalingGroups"]:
        print(f"[AutoScaling] Grupo '{nombre_grupo}' no encontrado.")
        return

    grupo = resp["AutoScalingGroups"][0]
    if grupo["MaxSize"] > MAX_INSTANCIAS:
        print(f"[AutoScaling] El MaxSize ({grupo['MaxSize']}) supera el límite "
              f"del Learner Lab ({MAX_INSTANCIAS}). Ajusta el grupo primero.")
        return

    # Política Scale Out (CPU alta → agregar instancia)
    resp_out = autoscaling.put_scaling_policy(
        AutoScalingGroupName=nombre_grupo,
        PolicyName=f"{nombre_grupo}-scale-out-cpu",
        PolicyType="SimpleScaling",
        AdjustmentType="ChangeInCapacity",
        ScalingAdjustment=1,       # agregar 1 instancia
        Cooldown=300,              # esperar 5 min antes del siguiente escalado
    )
    arn_out = resp_out["PolicyARN"]

    # Alarma CloudWatch que dispara Scale Out
    cloudwatch.put_metric_alarm(
        AlarmName=f"{nombre_grupo}-cpu-alta",
        AlarmDescription=f"CPU > {umbral_alto}% por 10 min → Scale Out",
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "AutoScalingGroupName", "Value": nombre_grupo}],
        Statistic="Average",
        Period=300,
        EvaluationPeriods=2,
        Threshold=umbral_alto,
        ComparisonOperator="GreaterThanThreshold",
        AlarmActions=[arn_out],
    )

    # Política Scale In (CPU baja → quitar instancia)
    resp_in = autoscaling.put_scaling_policy(
        AutoScalingGroupName=nombre_grupo,
        PolicyName=f"{nombre_grupo}-scale-in-cpu",
        PolicyType="SimpleScaling",
        AdjustmentType="ChangeInCapacity",
        ScalingAdjustment=-1,      # quitar 1 instancia
        Cooldown=300,
    )
    arn_in = resp_in["PolicyARN"]

    # Alarma CloudWatch que dispara Scale In
    cloudwatch.put_metric_alarm(
        AlarmName=f"{nombre_grupo}-cpu-baja",
        AlarmDescription=f"CPU < {umbral_bajo}% por 10 min → Scale In",
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "AutoScalingGroupName", "Value": nombre_grupo}],
        Statistic="Average",
        Period=300,
        EvaluationPeriods=2,
        Threshold=umbral_bajo,
        ComparisonOperator="LessThanThreshold",
        AlarmActions=[arn_in],
    )

    print(f"[AutoScaling] Políticas creadas para '{nombre_grupo}':")
    print(f"  Scale Out → CPU > {umbral_alto}%  (ARN: {arn_out[-30:]}...)")
    print(f"  Scale In  → CPU < {umbral_bajo}%  (ARN: {arn_in[-30:]}...)")


# ══════════════════════════════════════════════════════════════════════════════
# REPORTE DE RECURSOS
# ══════════════════════════════════════════════════════════════════════════════

def generar_reporte(nombre_archivo: str = REPORTE_CSV):
    """Genera un reporte CSV con todas las instancias EC2 y buckets S3."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    filas     = []

    # -- EC2 --
    for inst in listar_instancias():
        filas.append({
            "tipo_recurso":      "EC2",
            "identificador":     inst["id"],
            "nombre":            inst["nombre"],
            "detalle":           inst["tipo"],
            "estado":            inst["estado"],
            "ip_o_region":       inst["ip_publica"],
            "fecha_creacion":    inst["lanzada"],
            "timestamp_reporte": timestamp,
        })

    # -- S3 --
    for bucket in listar_buckets():
        try:
            objetos  = listar_objetos(bucket)
            total_kb = sum(o["tamanio_kb"] for o in objetos)
            filas.append({
                "tipo_recurso":      "S3",
                "identificador":     bucket,
                "nombre":            bucket,
                "detalle":           f"{len(objetos)} objetos / {total_kb:.1f} KB",
                "estado":            "activo",
                "ip_o_region":       REGION,
                "fecha_creacion":    "N/A",
                "timestamp_reporte": timestamp,
            })
        except Exception as e:
            print(f"[S3] No se pudo listar '{bucket}': {e}")

    campos = ["tipo_recurso", "identificador", "nombre", "detalle",
              "estado", "ip_o_region", "fecha_creacion", "timestamp_reporte"]

    with open(nombre_archivo, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas)

    print(f"\n[REPORTE] Guardado en '{nombre_archivo}' ({len(filas)} recursos)")
    return nombre_archivo


# ══════════════════════════════════════════════════════════════════════════════
# MENÚ PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def menu(config: dict):
    opciones = {
        # ── EC2 ──────────────────────────────────────────────────────────────
        "1": ("Listar instancias EC2",
              lambda: print(json.dumps(listar_instancias(), indent=2, default=str))),
        "2": ("Aprovisionar instancia EC2",
              lambda: aprovisionar_instancia(config, input("  Nombre de la instancia: "))),
        "3": ("Detener instancia EC2",
              lambda: detener_instancia(input("  Instance ID: "))),
        "4": ("Terminar instancia EC2",
              lambda: terminar_instancia(input("  Instance ID: "))),
        # ── S3 ───────────────────────────────────────────────────────────────
        "5": ("Listar buckets S3",
              lambda: print("\n".join(listar_buckets()))),
        "6": ("Listar objetos de un bucket S3",
              lambda: print(json.dumps(
                  listar_objetos(input("  Nombre del bucket: ")),
                  indent=2, default=str))),
        "E": ("Subir archivo a un bucket S3",
              lambda: subir_archivo(
                  input("  Nombre del bucket: "),
                  input("  Ruta del archivo local: "),
                  input("  Clave S3 (Enter para usar el nombre del archivo): ").strip() or None)),
        # ── REPORTES ─────────────────────────────────────────────────────────
        "7": ("Generar reporte CSV de recursos (EC2 + S3)",
              lambda: generar_reporte()),
        # ── CLOUDWATCH ───────────────────────────────────────────────────────
        "8": ("Ver métricas CloudWatch de una instancia",
              lambda: reporte_metricas_instancia(
                  input("  Instance ID: "),
                  int(input("  Últimos N minutos [60]: ") or 60))),
        "9": ("Reporte CloudWatch de TODAS las instancias (CSV)",
              lambda: reporte_metricas_todas_instancias(
                  int(input("  Últimos N minutos [60]: ") or 60))),
        # ── AUTO SCALING ─────────────────────────────────────────────────────
        "A": ("Listar grupos de Auto Scaling",
              lambda: listar_grupos_autoscaling()),
        "B": ("Listar políticas de un grupo de Auto Scaling",
              lambda: listar_politicas_scaling(
                  input("  Nombre del grupo: "))),
        "C": ("Actualizar capacidad de un grupo de Auto Scaling",
              lambda: actualizar_capacidad_autoscaling(
                  input("  Nombre del grupo: "),
                  int(input("  Mínimo: ")),
                  int(input("  Deseado: ")),
                  int(input("  Máximo (máx 9 en Learner Lab): ")))),
        "D": ("Crear políticas de escalado por CPU para un grupo",
              lambda: crear_politica_scaling_cpu(
                  input("  Nombre del grupo: "),
                  float(input("  Umbral CPU alto para Scale Out [70]: ") or 70),
                  float(input("  Umbral CPU bajo para Scale In  [30]: ") or 30))),
        # ── SALIR ────────────────────────────────────────────────────────────
        "0": ("Salir", None),
    }

    while True:
        print("\n" + "="*55)
        print("  AWS Manager – STF DevOps")
        print(f"  AMI: {config['ami']}  |  Tipo: {config['tipo']}")
        print(f"  Instancias activas: {contar_instancias_activas()}/{MAX_INSTANCIAS}")
        print("="*55)
        print("  ── EC2 ──────────────────────────────────────────")
        for k in ["1","2","3","4"]:
            print(f"  [{k}] {opciones[k][0]}")
        print("  ── S3 ──────────────────────────────────────────")
        for k in ["5","6","E"]:
            print(f"  [{k}] {opciones[k][0]}")
        print("  ── REPORTES ────────────────────────────────────")
        for k in ["7"]:
            print(f"  [{k}] {opciones[k][0]}")
        print("  ── CLOUDWATCH ──────────────────────────────────")
        for k in ["8","9"]:
            print(f"  [{k}] {opciones[k][0]}")
        print("  ── AUTO SCALING ────────────────────────────────")
        for k in ["A","B","C","D"]:
            print(f"  [{k}] {opciones[k][0]}")
        print("  ────────────────────────────────────────────────")
        print("  [0] Salir")
        print("="*55)

        eleccion = input("  Opción: ").strip().upper()
        if eleccion == "0":
            print("Saliendo...")
            break
        elif eleccion in opciones:
            try:
                opciones[eleccion][1]()
            except Exception as e:
                print(f"[ERROR] {e}")
        else:
            print("Opción inválida.")


if __name__ == "__main__":
    config = pedir_configuracion()
    menu(config)

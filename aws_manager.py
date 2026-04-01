#!/usr/bin/env python3
"""
aws_manager.py - Automatización de tareas AWS con Boto3
Soluciones Tecnológicas del Futuro

Funciones:
  - Aprovisionar instancias EC2 (máx. 9 en total, límite Learner Lab)
  - Listar buckets S3 y sus objetos
  - Generar reporte de uso de recursos en CSV
"""

import boto3
import csv
import json
from datetime import datetime, timezone

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
ec2 = boto3.client("ec2", region_name=REGION)
s3  = boto3.client("s3",  region_name=REGION)


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
        "1": ("Listar instancias EC2",
              lambda: print(json.dumps(listar_instancias(), indent=2, default=str))),
        "2": ("Aprovisionar instancia EC2",
              lambda: aprovisionar_instancia(config, input("  Nombre de la instancia: "))),
        "3": ("Detener instancia EC2",
              lambda: detener_instancia(input("  Instance ID: "))),
        "4": ("Terminar instancia EC2",
              lambda: terminar_instancia(input("  Instance ID: "))),
        "5": ("Listar buckets S3",
              lambda: print("\n".join(listar_buckets()))),
        "6": ("Listar objetos de un bucket S3",
              lambda: print(json.dumps(
                  listar_objetos(input("  Nombre del bucket: ")),
                  indent=2, default=str))),
        "7": ("Generar reporte CSV de recursos",
              lambda: generar_reporte()),
        "0": ("Salir", None),
    }

    while True:
        print("\n" + "="*50)
        print("  AWS Manager – STF DevOps")
        print(f"  AMI: {config['ami']}  |  Tipo: {config['tipo']}")
        print(f"  Instancias activas: {contar_instancias_activas()}/{MAX_INSTANCIAS}")
        print("="*50)
        for k, (desc, _) in opciones.items():
            print(f"  [{k}] {desc}")
        print("="*50)

        eleccion = input("  Opción: ").strip()
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

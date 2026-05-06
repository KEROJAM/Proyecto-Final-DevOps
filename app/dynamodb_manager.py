#!/usr/bin/env python3
"""
dynamodb_manager.py – Gestión de DynamoDB con Boto3
Soluciones Tecnológicas del Futuro

Operaciones:
  - Insertar registros (put_item)
  - Consultar registros (get_item / scan)
  - Modificar registros (update_item)
  - Eliminar registros (delete_item)

Tabla esperada en DynamoDB:
  Nombre:      stf-productos
  Clave primaria (Partition Key): producto_id  (String)

Cómo crear la tabla en la consola AWS:
  1. Abre DynamoDB → Tables → Create table
  2. Table name:       stf-productos
  3. Partition key:    producto_id   (String)
  4. Settings:         Default settings
  5. Click Create table
"""

import boto3
import json
from datetime import datetime, timezone
from decimal import Decimal

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
REGION      = "us-east-1"
NOMBRE_TABLA = "stf-productos"

# ─── CLIENTE DYNAMODB ─────────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb", region_name=REGION)
tabla    = dynamodb.Table(NOMBRE_TABLA)


# ══════════════════════════════════════════════════════════════════════════════
# INSERTAR
# ══════════════════════════════════════════════════════════════════════════════

def insertar_producto(producto_id: str, nombre: str,
                      categoria: str, precio: float,
                      stock: int) -> bool:
    """
    Inserta un nuevo producto en la tabla DynamoDB.
    Si ya existe un registro con el mismo producto_id lo sobreescribe.
    """
    try:
        tabla.put_item(
            Item={
                "producto_id": producto_id,
                "nombre":      nombre,
                "categoria":   categoria,
                "precio":      Decimal(str(precio)),  # DynamoDB no acepta float
                "stock":       stock,
                "creado_en":   datetime.now(timezone.utc).isoformat(),
                "activo":      True,
            }
        )
        print(f"[DynamoDB] Producto '{producto_id}' insertado correctamente.")
        return True
    except Exception as e:
        print(f"[DynamoDB] Error al insertar '{producto_id}': {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# CONSULTAR
# ══════════════════════════════════════════════════════════════════════════════

def obtener_producto(producto_id: str) -> dict:
    """
    Obtiene un producto por su clave primaria (producto_id).
    Retorna el item o None si no existe.
    """
    try:
        resp = tabla.get_item(Key={"producto_id": producto_id})
        item = resp.get("Item")
        if item:
            print(f"[DynamoDB] Producto encontrado: {producto_id}")
        else:
            print(f"[DynamoDB] Producto '{producto_id}' no encontrado.")
        return item
    except Exception as e:
        print(f"[DynamoDB] Error al consultar '{producto_id}': {e}")
        return None


def listar_productos() -> list:
    """
    Lista todos los productos de la tabla con Scan.
    Nota: Scan recorre toda la tabla — usar con cuidado en tablas grandes.
    """
    try:
        resp     = tabla.scan()
        items    = resp.get("Items", [])

        # Manejar paginación si hay más de 1 MB de datos
        while "LastEvaluatedKey" in resp:
            resp  = tabla.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))

        print(f"[DynamoDB] Total de productos: {len(items)}")
        for item in items:
            precio = float(item.get("precio", 0))
            print(f"  {item['producto_id']:<15} | {item.get('nombre',''):<25} | "
                  f"${precio:>8.2f} | stock: {item.get('stock', 0)}")
        return items

    except Exception as e:
        print(f"[DynamoDB] Error al listar productos: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# MODIFICAR
# ══════════════════════════════════════════════════════════════════════════════

def actualizar_precio(producto_id: str, nuevo_precio: float) -> bool:
    """Actualiza el precio de un producto existente."""
    try:
        tabla.update_item(
            Key={"producto_id": producto_id},
            UpdateExpression="SET precio = :p, actualizado_en = :t",
            ExpressionAttributeValues={
                ":p": Decimal(str(nuevo_precio)),
                ":t": datetime.now(timezone.utc).isoformat(),
            },
            ConditionExpression="attribute_exists(producto_id)",
        )
        print(f"[DynamoDB] Precio de '{producto_id}' actualizado a ${nuevo_precio:.2f}")
        return True
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        print(f"[DynamoDB] El producto '{producto_id}' no existe.")
        return False
    except Exception as e:
        print(f"[DynamoDB] Error al actualizar precio: {e}")
        return False


def actualizar_stock(producto_id: str, cantidad: int) -> bool:
    """
    Incrementa o decrementa el stock de un producto.
    Usa una expresión atómica para evitar condiciones de carrera.
    Cantidad positiva = agregar stock / negativa = reducir stock.
    """
    try:
        resp = tabla.update_item(
            Key={"producto_id": producto_id},
            UpdateExpression="SET stock = stock + :c, actualizado_en = :t",
            ExpressionAttributeValues={
                ":c": cantidad,
                ":t": datetime.now(timezone.utc).isoformat(),
                ":cero": 0,
            },
            # Evitar que el stock quede negativo
            ConditionExpression="attribute_exists(producto_id) AND stock + :c >= :cero",
            ReturnValues="UPDATED_NEW",
        )
        nuevo_stock = resp["Attributes"]["stock"]
        accion      = "agregadas" if cantidad > 0 else "reducidas"
        print(f"[DynamoDB] Stock de '{producto_id}' actualizado. "
              f"{abs(cantidad)} unidades {accion}. Nuevo stock: {nuevo_stock}")
        return True
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        print(f"[DynamoDB] No se pudo actualizar: producto no existe "
              f"o el stock quedaría negativo.")
        return False
    except Exception as e:
        print(f"[DynamoDB] Error al actualizar stock: {e}")
        return False


def desactivar_producto(producto_id: str) -> bool:
    """Marca un producto como inactivo sin eliminarlo (soft delete)."""
    try:
        tabla.update_item(
            Key={"producto_id": producto_id},
            UpdateExpression="SET activo = :v, actualizado_en = :t",
            ExpressionAttributeValues={
                ":v": False,
                ":t": datetime.now(timezone.utc).isoformat(),
            },
            ConditionExpression="attribute_exists(producto_id)",
        )
        print(f"[DynamoDB] Producto '{producto_id}' desactivado.")
        return True
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        print(f"[DynamoDB] El producto '{producto_id}' no existe.")
        return False
    except Exception as e:
        print(f"[DynamoDB] Error al desactivar: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# ELIMINAR
# ══════════════════════════════════════════════════════════════════════════════

def eliminar_producto(producto_id: str) -> bool:
    """
    Elimina permanentemente un producto de la tabla.
    Esta operación NO se puede deshacer.
    """
    confirmacion = input(
        f"  ¿Seguro que deseas eliminar '{producto_id}'? (s/N): "
    ).strip().lower()

    if confirmacion != "s":
        print("[DynamoDB] Eliminación cancelada.")
        return False

    try:
        tabla.delete_item(
            Key={"producto_id": producto_id},
            ConditionExpression="attribute_exists(producto_id)",
        )
        print(f"[DynamoDB] Producto '{producto_id}' eliminado permanentemente.")
        return True
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        print(f"[DynamoDB] El producto '{producto_id}' no existe.")
        return False
    except Exception as e:
        print(f"[DynamoDB] Error al eliminar: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# DATOS DE PRUEBA
# ══════════════════════════════════════════════════════════════════════════════

def cargar_datos_prueba():
    """Inserta 5 productos de ejemplo para probar el script."""
    productos = [
        ("PROD-001", "Laptop Pro 15",       "Electrónica",  1299.99, 15),
        ("PROD-002", "Teclado Mecánico",    "Periféricos",    89.99, 42),
        ("PROD-003", "Monitor 27 4K",       "Electrónica",   549.99,  8),
        ("PROD-004", "Mouse Inalámbrico",   "Periféricos",    39.99, 65),
        ("PROD-005", "Silla Ergonómica",    "Mobiliario",    299.99,  5),
    ]
    print("[DynamoDB] Cargando datos de prueba...")
    for prod in productos:
        insertar_producto(*prod)
    print(f"[DynamoDB] {len(productos)} productos cargados.")


# ══════════════════════════════════════════════════════════════════════════════
# MENÚ PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def menu():
    opciones = {
        "1": ("Listar todos los productos",
              lambda: listar_productos()),
        "2": ("Consultar producto por ID",
              lambda: print(json.dumps(
                  obtener_producto(input("  Producto ID: ")),
                  indent=2, default=str))),
        "3": ("Insertar nuevo producto",
              lambda: insertar_producto(
                  input("  Producto ID: "),
                  input("  Nombre: "),
                  input("  Categoría: "),
                  float(input("  Precio: ")),
                  int(input("  Stock: ")))),
        "4": ("Actualizar precio",
              lambda: actualizar_precio(
                  input("  Producto ID: "),
                  float(input("  Nuevo precio: ")))),
        "5": ("Actualizar stock  (+N agregar / -N reducir)",
              lambda: actualizar_stock(
                  input("  Producto ID: "),
                  int(input("  Cantidad (+/-): ")))),
        "6": ("Desactivar producto (soft delete)",
              lambda: desactivar_producto(input("  Producto ID: "))),
        "7": ("Eliminar producto permanentemente",
              lambda: eliminar_producto(input("  Producto ID: "))),
        "8": ("Cargar datos de prueba (5 productos de ejemplo)",
              lambda: cargar_datos_prueba()),
        "0": ("Salir", None),
    }

    print(f"\n  Tabla DynamoDB: {NOMBRE_TABLA}  |  Región: {REGION}")

    while True:
        print("\n" + "="*50)
        print("  DynamoDB Manager – STF DevOps")
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
    menu()

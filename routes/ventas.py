from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify, send_file
from db.conexion import obtener_conexion
from datetime import datetime, date
from io import BytesIO
from openpyxl import Workbook

ventas_bp = Blueprint('ventas', __name__)

@ventas_bp.route("/ventas")
def ventas():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))

    nombre_usuario = session["nombre_usuario"]
    nombre_sucursal = session["nombre_sucursal"]

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT p.id, p.nombre, p.precio_unitario, p.codigo_barras, s.nombre
        FROM productos p
        JOIN inventario i ON i.id_producto = p.id
        JOIN sucursales s ON i.id_sucursal = s.id
        WHERE s.nombre = %s
        ORDER BY p.nombre
    """, (nombre_sucursal,))
    productos = cursor.fetchall()
    cursor.close()
    conexion.close()

    return render_template(
        "ventas.html",
        nombre_usuario=nombre_usuario,
        nombre_sucursal=nombre_sucursal,
        productos=productos,
        rol=session.get("rol")
    )

@ventas_bp.route("/registrar-venta", methods=["POST"])
def registrar_venta():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 403

    data = request.get_json()
    productos = data.get("productos", [])

    if not productos:
        return jsonify({"error": "No se proporcionaron productos"}), 400

    usuario_id = session["usuario_id"]
    nombre_sucursal = session["nombre_sucursal"]

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("SELECT id FROM sucursales WHERE nombre = %s", (nombre_sucursal,))
    sucursal = cursor.fetchone()
    if not sucursal:
        cursor.close()
        conexion.close()
        return jsonify({"error": "Sucursal no encontrada"}), 400
    id_sucursal = sucursal[0]

    total = sum(item["subtotal"] for item in productos)

    cursor.execute("""
        INSERT INTO ventas (id_usuario, id_sucursal, fecha, total)
        VALUES (%s, %s, %s, %s) RETURNING id
    """, (usuario_id, id_sucursal, datetime.now(), total))
    id_venta = cursor.fetchone()[0]

    for item in productos:
        id_producto = item["id"]
        cantidad = item["cantidad"]
        precio_unitario = item["precio"]
        subtotal = item["subtotal"]

        cursor.execute("""
            INSERT INTO detalle_venta (id_venta, id_producto, cantidad, precio_unitario, subtotal)
            VALUES (%s, %s, %s, %s, %s)
        """, (id_venta, id_producto, cantidad, precio_unitario, subtotal))

        cursor.execute("""
            UPDATE inventario
            SET cantidad = cantidad - %s
            WHERE id_producto = %s AND id_sucursal = %s
        """, (cantidad, id_producto, id_sucursal))

    conexion.commit()
    cursor.close()
    conexion.close()

    return jsonify({"mensaje": "Venta registrada"}), 200

@ventas_bp.route("/ventas-del-dia")
def ventas_del_dia():
    if "usuario_id" not in session:
        return "No autorizado", 403

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT v.id, v.fecha, u.nombre AS vendedor, p.nombre AS producto,
               dv.cantidad, dv.precio_unitario, dv.subtotal
        FROM ventas v
        JOIN detalle_venta dv ON v.id = dv.id_venta
        JOIN productos p ON dv.id_producto = p.id
        JOIN usuarios u ON v.id_usuario = u.id
        WHERE DATE(v.fecha) = %s
        ORDER BY v.fecha
    """, (date.today(),))

    ventas = cursor.fetchall()
    cursor.close()
    conexion.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Ventas del Día"
    ws.append(["ID Venta", "Fecha", "Vendedor", "Producto", "Cantidad", "Precio Unitario", "Subtotal"])

    for row in ventas:
        ws.append(row)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(output,
                     as_attachment=True,
                     download_name=f"ventas_dia_{date.today()}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
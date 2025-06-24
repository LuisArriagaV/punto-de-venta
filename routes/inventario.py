from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify, send_file
from db.conexion import obtener_conexion
from datetime import datetime, date
import pandas as pd
import io
from io import BytesIO
from openpyxl import Workbook

inventario_bp = Blueprint('inventario', __name__)

@inventario_bp.route("/inventario")
def inventario():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))

    rol = session.get("rol")
    usuario_id = session["usuario_id"]
    nombre_sucursal = session.get("nombre_sucursal")
    sucursal_filtrada = request.args.get("sucursal_filtrada", nombre_sucursal)

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    if rol == "admin":
        cursor.execute("""
            SELECT 
                p.id,
                p.nombre AS nombre_producto,
                p.descripcion,
                p.codigo_barras,
                s.nombre AS nombre_sucursal,
                i.cantidad,
                p.precio_unitario
            FROM inventario i
            JOIN productos p ON i.id_producto = p.id
            JOIN sucursales s ON i.id_sucursal = s.id
            ORDER BY p.nombre ASC
        """)
    else:
        cursor.execute("""
            SELECT 
                p.id,
                p.nombre AS nombre_producto,
                p.descripcion,
                p.codigo_barras,
                s.nombre AS nombre_sucursal,
                i.cantidad,
                p.precio_unitario
            FROM inventario i
            JOIN productos p ON i.id_producto = p.id
            JOIN sucursales s ON i.id_sucursal = s.id
            WHERE s.nombre = %s
            ORDER BY p.nombre ASC
        """, (sucursal_filtrada,))

    inventario = [
        {
            "id_producto": row[0],
            "nombre_producto": row[1],
            "descripcion": row[2],
            "codigo_barras": row[3],
            "nombre_sucursal": row[4],
            "cantidad": row[5],
            "precio_unitario": row[6]
        }
        for row in cursor.fetchall()
    ]

    cursor.execute("SELECT id, nombre, codigo_barras FROM productos ORDER BY nombre")
    productos = [
        {"id": row[0], "nombre": row[1], "codigo_barras": row[2]}
        for row in cursor.fetchall()
    ]

    sucursales = []
    if rol != "admin":
        cursor.execute("""
            SELECT DISTINCT s.nombre
            FROM usuarios u
            JOIN sucursales s ON u.id_sucursal = s.id
            WHERE u.id = %s
        """, (usuario_id,))
        sucursales = [row[0] for row in cursor.fetchall()]

    cursor.close()
    conexion.close()

    return render_template(
        "inventario.html",
        inventario=inventario,
        rol=rol,
        productos=productos,
        nombre_sucursal=sucursal_filtrada,
        sucursales=sucursales
    )

@inventario_bp.route("/agregar-inventario", methods=["POST"])
def agregar_inventario():
    if "usuario_id" not in session or session.get("rol") != "admin":
        return "Acceso no autorizado", 403

    producto_input = request.form.get("producto", "").strip()
    id_sucursal = request.form["id_sucursal"]
    cantidad = request.form["cantidad"]

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("SELECT id FROM productos WHERE nombre = %s OR codigo_barras = %s", (producto_input, producto_input))
    resultado = cursor.fetchone()

    if resultado:
        id_producto = resultado[0]
    else:
        cursor.close()
        conexion.close()
        return "Producto no encontrado", 400

    cursor.execute("""
        SELECT id FROM inventario
        WHERE id_producto = %s AND id_sucursal = %s
    """, (id_producto, id_sucursal))
    existente = cursor.fetchone()

    if existente:
        cursor.execute("""
            UPDATE inventario
            SET cantidad = cantidad + %s
            WHERE id_producto = %s AND id_sucursal = %s
        """, (cantidad, id_producto, id_sucursal))
    else:
        cursor.execute("""
            INSERT INTO inventario (id_producto, id_sucursal, cantidad)
            VALUES (%s, %s, %s)
        """, (id_producto, id_sucursal, cantidad))

    conexion.commit()
    cursor.close()
    conexion.close()

    return redirect(url_for("inventario.inventario"))

@inventario_bp.route("/mod-inventario", methods=["GET", "POST"])
def mod_inventario():
    if "usuario_id" not in session or session.get("rol") != "admin":
        return redirect(url_for("auth.login"))

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("SELECT id, nombre FROM sucursales")
    sucursales = [{"id": row[0], "nombre": row[1]} for row in cursor.fetchall()]

    # Exportar inventario
    if request.method == "GET" and request.args.get("accion") == "exportar":
        cursor.execute("""
            SELECT 
                p.id AS id_producto,
                p.nombre AS nombre_producto,
                p.codigo_barras,
                s.id AS id_sucursal,
                s.nombre AS nombre_sucursal,
                i.cantidad
            FROM inventario i
            JOIN productos p ON i.id_producto = p.id
            JOIN sucursales s ON i.id_sucursal = s.id
            ORDER BY s.nombre, p.nombre
        """)
        rows = cursor.fetchall()
        cursor.close()
        conexion.close()

        df = pd.DataFrame(rows, columns=[
            "id_producto", "nombre_producto", "codigo_barras",
            "id_sucursal", "nombre_sucursal", "cantidad"
        ])
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Inventario")
        output.seek(0)

        return send_file(output, as_attachment=True, download_name="inventario.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # Importar inventario
    if request.method == "POST" and request.form.get("accion") == "importar":
        archivo = request.files.get("archivo")
        if not archivo:
            flash("No se proporcionó archivo para importar.", "danger")
            cursor.close()
            conexion.close()
            return redirect(url_for("mod_inventario"))

        try:
            if archivo.filename.endswith(".csv"):
                df = pd.read_csv(archivo)
            elif archivo.filename.endswith(".xlsx"):
                df = pd.read_excel(archivo)
            else:
                flash("Formato de archivo no soportado. Usa .csv o .xlsx.", "danger")
                cursor.close()
                conexion.close()
                return redirect(url_for("mod_inventario"))
        except Exception as e:
            flash(f"Error al leer el archivo: {e}", "danger")
            cursor.close()
            conexion.close()
            return redirect(url_for("mod_inventario"))

        columnas_alias = {
            "codigo_barras": None,
            "nombre_producto": None,
            "id_sucursal": None,
            "cantidad": None
        }

        for key in columnas_alias:
            for col in df.columns:
                if col.strip().lower() == key:
                    columnas_alias[key] = col
                    break

        if not columnas_alias["id_sucursal"] or not columnas_alias["cantidad"]:
            faltantes = [k for k, v in columnas_alias.items() if not v and k in ["id_sucursal", "cantidad"]]
            flash(f"El archivo no contiene las columnas requeridas: {', '.join(faltantes)}", "danger")
            cursor.close()
            conexion.close()
            return redirect(url_for("mod_inventario"))

        exitosos = 0
        errores_formato = 0
        incompletos = 0
        no_encontrados = 0

        for _, fila in df.iterrows():
            try:
                valor_barras = fila.get(columnas_alias["codigo_barras"]) if columnas_alias["codigo_barras"] else ""
                codigo_barras = str(valor_barras).strip() if pd.notna(valor_barras) else ""

                valor_nombre = fila.get(columnas_alias["nombre_producto"]) if columnas_alias["nombre_producto"] else ""
                nombre_producto = str(valor_nombre).strip() if pd.notna(valor_nombre) else ""

                id_sucursal = fila.get(columnas_alias["id_sucursal"])
                cantidad = fila.get(columnas_alias["cantidad"])
            except Exception:
                errores_formato += 1
                continue

            if not (id_sucursal and cantidad and (codigo_barras or nombre_producto)):
                incompletos += 1
                continue

            try:
                id_sucursal = int(id_sucursal)
                cantidad = int(cantidad)
            except Exception:
                errores_formato += 1
                continue

            try:
                resultado = None

                if codigo_barras:
                    cursor.execute("SELECT id FROM productos WHERE codigo_barras = %s", (codigo_barras,))
                    resultado = cursor.fetchone()

                if not resultado and codigo_barras:
                    try:
                        codigo_normalizado = str(int(codigo_barras))
                        cursor.execute("SELECT id FROM productos WHERE codigo_barras = %s", (codigo_normalizado,))
                        resultado = cursor.fetchone()
                    except ValueError:
                        pass

                nombre_normalizado = nombre_producto.strip().lower()

                if not resultado and nombre_normalizado:
                    cursor.execute("SELECT id FROM productos WHERE LOWER(TRIM(nombre)) = %s", (nombre_normalizado,))
                    resultado = cursor.fetchone()
                
                if not resultado and nombre_normalizado:
                    like_term = f"%{nombre_normalizado}%"
                    cursor.execute("""
                        SELECT id FROM productos
                        WHERE LOWER(nombre) ILIKE %s OR LOWER(descripcion) ILIKE %s
                        LIMIT 1
                    """, (like_term, like_term))
                    resultado = cursor.fetchone()

                if not resultado:
                    nuevo_nombre = nombre_producto if nombre_producto else f"Producto sin nombre - {codigo_barras or 'sin_codigo'}"
                    nuevo_codigo = codigo_barras if codigo_barras else None
                    try:
                        cursor.execute("""
                            INSERT INTO productos (nombre, descripcion, codigo_barras, precio_unitario)
                            VALUES (%s, %s, %s, %s)
                            RETURNING id
                        """, (nuevo_nombre, "", nuevo_codigo, 0.0))
                        id_producto = cursor.fetchone()[0]
                        print(f"[DEBUG] Producto CREADO: '{nuevo_nombre}' con código '{nuevo_codigo}'")
                    except Exception as e:
                        print(f"[ERROR] No se pudo crear el producto: {e}")
                        errores_formato += 1
                        continue
                else:
                    id_producto = resultado[0]

                cursor.execute("""
                    SELECT id FROM inventario
                    WHERE id_producto = %s AND id_sucursal = %s
                """, (id_producto, id_sucursal))
                existente = cursor.fetchone()

                if existente:
                    cursor.execute("""
                        UPDATE inventario
                        SET cantidad = cantidad + %s
                        WHERE id_producto = %s AND id_sucursal = %s
                    """, (cantidad, id_producto, id_sucursal))
                    exitosos += 1
                else:
                    cursor.execute("""
                        INSERT INTO inventario (id_producto, id_sucursal, cantidad)
                        VALUES (%s, %s, %s)
                    """, (id_producto, id_sucursal, cantidad))
                    exitosos += 1

            except Exception:
                errores_formato += 1
                continue

    conexion.commit()
    cursor.close()
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    # Recuperar inventario actualizado
    cursor.execute("""
        SELECT 
            p.id,
            p.nombre AS nombre_producto,
            p.codigo_barras,
            s.id AS id_sucursal,
            s.nombre AS nombre_sucursal,
            i.cantidad,
            p.precio_unitario
        FROM inventario i
        JOIN productos p ON i.id_producto = p.id
        JOIN sucursales s ON i.id_sucursal = s.id
        ORDER BY p.nombre ASC
    """)
    inventario = [
        {
            "id_producto": row[0],
            "nombre_producto": row[1],
            "codigo_barras": row[2],
            "id_sucursal": row[3],
            "nombre_sucursal": row[4],
            "cantidad": row[5],
            "precio_unitario": row[6]
        }
        for row in cursor.fetchall()
    ]

    cursor.close()
    conexion.close()


    return render_template("mod_inventario.html", inventario=inventario, sucursales=sucursales)


# Nueva función para eliminar inventario
@inventario_bp.route("/eliminar-inventario")
def eliminar_inventario():
    if "usuario_id" not in session or session.get("rol") != "admin":
        return "Acceso no autorizado", 403

    id_producto = request.args.get("id_producto")
    id_sucursal = request.args.get("id_sucursal")

    if not id_producto or not id_sucursal:
        return "Datos incompletos", 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        DELETE FROM inventario
        WHERE id_producto = %s AND id_sucursal = %s
    """, (id_producto, id_sucursal))

    conexion.commit()
    cursor.close()
    conexion.close()

    flash("Producto eliminado del inventario correctamente.", "success")
    return redirect(url_for("inventario.mod_inventario"))

@inventario_bp.route("/transferir-inventario", methods=["POST"])
def transferir_inventario():
    if "usuario_id" not in session or session.get("rol") != "admin":
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for("inventario.mod_inventario"))

    id_producto = request.form.get("id_producto")
    id_origen = request.form.get("id_origen")
    id_destino = request.form.get("id_destino")
    cantidad = request.form.get("cantidad")

    if not all([id_producto, id_origen, id_destino, cantidad]):
        flash("Datos incompletos.", "danger")
        return redirect(url_for("inventario.mod_inventario"))

    try:
        cantidad = int(cantidad)
        if cantidad <= 0:
            flash("Cantidad inválida.", "danger")
            return redirect(url_for("inventario.mod_inventario"))
    except ValueError:
        flash("Cantidad inválida.", "danger")
        return redirect(url_for("inventario.mod_inventario"))

    if id_origen == id_destino:
        flash("La sucursal de origen y destino no pueden ser la misma.", "danger")
        return redirect(url_for("inventario.mod_inventario"))

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT cantidad FROM inventario
        WHERE id_producto = %s AND id_sucursal = %s
    """, (id_producto, id_origen))
    origen = cursor.fetchone()
    if not origen or origen[0] < cantidad:
        cursor.close()
        conexion.close()
        flash("Inventario insuficiente en la sucursal origen.", "danger")
        return redirect(url_for("inventario.mod_inventario"))

    cursor.execute("""
        UPDATE inventario
        SET cantidad = cantidad - %s
        WHERE id_producto = %s AND id_sucursal = %s
    """, (cantidad, id_producto, id_origen))

    cursor.execute("""
        SELECT cantidad FROM inventario
        WHERE id_producto = %s AND id_sucursal = %s
    """, (id_producto, id_destino))
    destino = cursor.fetchone()

    if destino:
        cursor.execute("""
            UPDATE inventario
            SET cantidad = cantidad + %s
            WHERE id_producto = %s AND id_sucursal = %s
        """, (cantidad, id_producto, id_destino))
    else:
        cursor.execute("""
            INSERT INTO inventario (id_producto, id_sucursal, cantidad)
            VALUES (%s, %s, %s)
        """, (id_producto, id_destino, cantidad))

    conexion.commit()
    cursor.close()
    conexion.close()

    flash("Transferencia realizada exitosamente.", "success")
    return redirect(url_for("inventario.mod_inventario"))

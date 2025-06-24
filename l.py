from flask import Flask, render_template, request, redirect, session, url_for, send_file, flash, jsonify

from db.conexion import obtener_conexion
import pandas as pd
import io
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'clave-secreta'  # Cámbiala por algo más seguro en producción

@app.route("/", methods=["GET", "POST"])
def login(): 
    error = None
    if request.method == "POST":
        correo = request.form["correo"]
        contrasena = request.form["contrasena"]
        
        conn = obtener_conexion()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.nombre, u.rol, s.nombre 
            FROM usuarios u
            JOIN sucursales s ON u.id_sucursal = s.id
            WHERE u.correo = %s AND u.contrasena = %s
        """, (correo, contrasena))
        usuario = cur.fetchone()
        conn.close()

        if usuario:
            session["usuario_id"] = usuario[0]
            session["nombre_usuario"] = usuario[1]
            session["rol"] = usuario[2]
            session["nombre_sucursal"] = usuario[3]
            return redirect(url_for("ventas"))
        else:
            error = "Usuario o contraseña incorrectos"

    return render_template("login.html", error=error)

@app.route("/ventas")
def ventas():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

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
        productos=productos
    )

@app.route("/register", methods=["GET", "POST"])
def register():
    if "usuario_id" not in session or session.get("rol") != "admin":
        return redirect(url_for("login"))

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    if request.method == "POST":
        nombre = request.form["nombre"]
        correo = request.form["correo"]
        contrasena = request.form["contrasena"]
        rol = request.form["rol"]
        id_sucursal = request.form["id_sucursal"]

        # Verificar si ya existe el correo
        cursor.execute("SELECT id FROM usuarios WHERE correo = %s", (correo,))
        if cursor.fetchone():
            flash("Ese correo ya está registrado. Intenta con otro.", "danger")
        else:
            cursor.execute("""
                INSERT INTO usuarios (nombre, correo, contrasena, rol, id_sucursal)
                VALUES (%s, %s, %s, %s, %s)
            """, (nombre, correo, contrasena, rol, id_sucursal))
            conexion.commit()
            flash("Usuario registrado exitosamente.", "success")
            return redirect(url_for("ventas"))

    # Obtener sucursales para el formulario
    cursor.execute("SELECT id, nombre FROM sucursales")
    sucursales = cursor.fetchall()

    cursor.close()
    conexion.close()

    return render_template("register.html", sucursales=sucursales)


@app.route("/inventario")
def inventario():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    rol = session.get("rol")
    usuario_id = session["usuario_id"]
    nombre_sucursal = session.get("nombre_sucursal")
    sucursal_filtrada = request.args.get("sucursal_filtrada", nombre_sucursal)

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    # Consulta del inventario con precio_unitario incluido
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

    # Obtener lista de sucursales solo si no es admin
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

@app.route("/agregar-inventario", methods=["POST"])
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

    return redirect(url_for("inventario"))

@app.route("/mod-inventario", methods=["GET", "POST"])
def mod_inventario():
    if "usuario_id" not in session or session.get("rol") != "admin":
        return redirect(url_for("login"))

    # Mostrar inventario, importar o exportar
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    # Obtener todas las sucursales justo después de abrir la conexión
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

        # Aceptar columnas necesarias en cualquier orden
        columnas_posibles = set(df.columns.str.lower())
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

        # Verifica que al menos id_sucursal y cantidad estén presentes
        if not columnas_alias["id_sucursal"] or not columnas_alias["cantidad"]:
            faltantes = [k for k, v in columnas_alias.items() if not v and k in ["id_sucursal", "cantidad"]]
            flash(f"El archivo no contiene las columnas requeridas: {', '.join(faltantes)}", "danger")
            cursor.close()
            conexion.close()
            return redirect(url_for("mod_inventario"))

        exitosos = 0
        no_encontrados = 0
        incompletos = 0
        errores_formato = 0

        for _, fila in df.iterrows():
            try:
                # Verificación explícita de NaN para evitar "nan" string en campos vacíos
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
                # id_sucursal y cantidad pueden venir como float si el archivo es Excel, intenta convertirlos
                id_sucursal = int(id_sucursal)
                cantidad = int(cantidad)
            except Exception:
                errores_formato += 1
                continue

            try:
                resultado = None

                # Buscar por código de barras exacto
                if codigo_barras:
                    cursor.execute("SELECT id FROM productos WHERE codigo_barras = %s", (codigo_barras,))
                    resultado = cursor.fetchone()

                # Buscar por código convertido a número (sin ceros al inicio)
                if not resultado and codigo_barras:
                    try:
                        codigo_normalizado = str(int(codigo_barras))
                        cursor.execute("SELECT id FROM productos WHERE codigo_barras = %s", (codigo_normalizado,))
                        resultado = cursor.fetchone()
                    except ValueError:
                        pass

                # Normalizar nombre para comparación
                nombre_normalizado = nombre_producto.strip().lower()

                # Buscar por nombre exacto (ignorando mayúsculas y espacios)
                if not resultado and nombre_normalizado:
                    cursor.execute("SELECT id FROM productos WHERE LOWER(TRIM(nombre)) = %s", (nombre_normalizado,))
                    resultado = cursor.fetchone()

                # Buscar parcialmente en nombre o descripción
                if not resultado and nombre_normalizado:
                    like_term = f"%{nombre_normalizado}%"
                    cursor.execute("""
                        SELECT id FROM productos
                        WHERE LOWER(nombre) ILIKE %s OR LOWER(descripcion) ILIKE %s
                        LIMIT 1
                    """, (like_term, like_term))
                    resultado = cursor.fetchone()

                # Si no se encuentra, crear producto automáticamente
                if not resultado:
                    # Crear producto si no existe
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
        mensaje = f"Importación completada: {exitosos} exitosos, {no_encontrados} productos no encontrados, {incompletos} filas ignoradas por datos incompletos."
        if errores_formato:
            mensaje += f" {errores_formato} filas con errores de formato fueron ignoradas."
        flash(mensaje, "success")
        # Bandera en sesión para mostrar que se completó la importación
        session["importacion_completada"] = True
        cursor.close()
        conexion.close()
        return redirect(url_for("mod_inventario"))

    # Mostrar inventario
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

@app.route("/actualizar-inventario", methods=["POST"])
def actualizar_inventario():
    if "usuario_id" not in session or session.get("rol") != "admin":
        return "Acceso no autorizado", 403

    id_producto = request.form.get("id_producto")
    id_sucursal = request.form.get("id_sucursal")
    cantidad = request.form.get("cantidad")
    precio = request.form.get("precio_unitario")

    if not id_producto or not id_sucursal or not cantidad:
        return "Datos incompletos", 400

    try:
        cantidad_int = int(cantidad)
        if cantidad_int < 0:
            return "Cantidad inválida", 400
    except ValueError:
        return "Cantidad inválida", 400

    # Validar precio_unitario
    try:
        precio_float = float(precio)
        if precio_float < 0:
            return "Precio inválido", 400
    except (ValueError, TypeError):
        return "Precio inválido", 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        UPDATE inventario
        SET cantidad = %s
        WHERE id_producto = %s AND id_sucursal = %s
    """, (cantidad_int, id_producto, id_sucursal))

    cursor.execute("""
        UPDATE productos
        SET precio_unitario = %s
        WHERE id = %s
    """, (precio_float, id_producto))

    conexion.commit()
    cursor.close()
    conexion.close()

    return redirect(url_for("mod_inventario"))

@app.route("/eliminar-inventario")
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
    return redirect(url_for("mod_inventario"))

@app.route("/transferir-inventario", methods=["POST"])
def transferir_inventario():
    if "usuario_id" not in session or session.get("rol") != "admin":
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for("mod_inventario"))

    id_producto = request.form.get("id_producto")
    id_origen = request.form.get("id_origen")
    id_destino = request.form.get("id_destino")
    cantidad = request.form.get("cantidad")

    if not all([id_producto, id_origen, id_destino, cantidad]):
        flash("Datos incompletos.", "danger")
        return redirect(url_for("mod_inventario"))

    try:
        cantidad = int(cantidad)
        if cantidad <= 0:
            flash("Cantidad inválida.", "danger")
            return redirect(url_for("mod_inventario"))
    except ValueError:
        flash("Cantidad inválida.", "danger")
        return redirect(url_for("mod_inventario"))

    if id_origen == id_destino:
        flash("La sucursal de origen y destino no pueden ser la misma.", "danger")
        return redirect(url_for("mod_inventario"))

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    # Verificar inventario suficiente en origen
    cursor.execute("""
        SELECT cantidad FROM inventario
        WHERE id_producto = %s AND id_sucursal = %s
    """, (id_producto, id_origen))
    origen = cursor.fetchone()
    if not origen or origen[0] < cantidad:
        cursor.close()
        conexion.close()
        flash("Inventario insuficiente en la sucursal origen.", "danger")
        return redirect(url_for("mod_inventario"))

    # Restar del origen
    cursor.execute("""
        UPDATE inventario
        SET cantidad = cantidad - %s
        WHERE id_producto = %s AND id_sucursal = %s
    """, (cantidad, id_producto, id_origen))

    # Sumar o insertar en destino
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
    return redirect(url_for("mod_inventario"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Nueva ruta para registrar venta
@app.route("/registrar-venta", methods=["POST"])
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

    # Obtener id_sucursal
    cursor.execute("SELECT id FROM sucursales WHERE nombre = %s", (nombre_sucursal,))
    sucursal = cursor.fetchone()
    if not sucursal:
        cursor.close()
        conexion.close()
        return jsonify({"error": "Sucursal no encontrada"}), 400
    id_sucursal = sucursal[0]

    # Calcular total
    total = sum(item["subtotal"] for item in productos)

    # Insertar venta
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

        # Insertar en detalle_venta
        cursor.execute("""
            INSERT INTO detalle_venta (id_venta, id_producto, cantidad, precio_unitario, subtotal)
            VALUES (%s, %s, %s, %s, %s)
        """, (id_venta, id_producto, cantidad, precio_unitario, subtotal))

        # Restar del inventario
        cursor.execute("""
            UPDATE inventario
            SET cantidad = cantidad - %s
            WHERE id_producto = %s AND id_sucursal = %s
        """, (cantidad, id_producto, id_sucursal))

    conexion.commit()
    cursor.close()
    conexion.close()

    return jsonify({"mensaje": "Venta registrada"}), 200

@app.route("/ventas-del-dia")
def ventas_del_dia():
    if "usuario_id" not in session:
        return "No autorizado", 403

    from io import BytesIO
    from openpyxl import Workbook
    from datetime import date

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




if __name__ == "__main__":
    app.run(debug=True)
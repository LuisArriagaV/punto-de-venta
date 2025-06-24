from flask import Blueprint, render_template, request, redirect, session, url_for, flash
from db.conexion import obtener_conexion
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/usuarios")
def usuarios():
    if "usuario_id" not in session or session.get("rol") != "admin":
        return redirect(url_for("auth.login"))

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT u.id, u.nombre, u.correo, u.contrasena, u.rol, s.nombre AS sucursal
        FROM usuarios u
        JOIN sucursales s ON u.id_sucursal = s.id
        ORDER BY u.nombre
    """)
    rows = cursor.fetchall()

    usuarios = [
        {
            "id": row[0],
            "nombre": row[1],
            "correo": row[2],
            "contrasena": row[3],
            "rol": row[4],
            "sucursal": row[5],
        }
        for row in rows
    ]

    cursor.close()
    conexion.close()

    return render_template("usuarios.html", usuarios=usuarios)

@auth_bp.route("/usuarios/editar/<int:id>", methods=["GET", "POST"])
def editar_usuario(id):
    if "usuario_id" not in session or session.get("rol") != "admin":
        return redirect(url_for("auth.login"))
    
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    if request.method == "POST":
        nombre = request.form["nombre"]
        correo = request.form["correo"]
        nueva_contrasena = request.form["contrasena"]
        contrasena_hash = generate_password_hash(nueva_contrasena)
        rol = request.form["rol"]
        id_sucursal = request.form["id_sucursal"]

        cursor.execute("""
            UPDATE usuarios
            SET nombre=%s, correo=%s, contrasena=%s, rol=%s, id_sucursal=%s
            WHERE id=%s
        """, (nombre, correo, contrasena_hash, rol, id_sucursal, id))
        conexion.commit()
        cursor.close()
        conexion.close()

        flash("Usuario actualizado correctamente.", "success")
        return redirect(url_for("auth.usuarios"))

    cursor.execute("SELECT nombre, correo, contrasena, rol, id_sucursal FROM usuarios WHERE id=%s", (id,))
    row = cursor.fetchone()

    if not row:
        flash("Usuario no encontrado.", "danger")
        cursor.close()
        conexion.close()
        return redirect(url_for("auth.usuarios"))

    usuario = {
        "nombre": row[0],
        "correo": row[1],
        "contrasena": row[2],
        "rol": row[3],
        "id_sucursal": row[4]
    }

    cursor.execute("SELECT id, nombre FROM sucursales")
    sucursales = cursor.fetchall()

    cursor.close()
    conexion.close()

    return render_template("editar_usuario.html", usuario=usuario, sucursales=sucursales, id=id)

@auth_bp.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        correo = request.form["correo"]
        contrasena = request.form["contrasena"]

        conn = obtener_conexion()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.nombre, u.contrasena, u.rol, s.nombre 
            FROM usuarios u
            JOIN sucursales s ON u.id_sucursal = s.id
            WHERE u.correo = %s
        """, (correo,))
        usuario = cur.fetchone()
        conn.close()

        if usuario and check_password_hash(usuario[2], contrasena):
            session["usuario_id"] = usuario[0]
            session["nombre_usuario"] = usuario[1]
            session["rol"] = usuario[3]
            session["nombre_sucursal"] = usuario[4]
            return redirect(url_for("ventas.ventas"))
        else:
            error = "Usuario o contraseña incorrectos"

    return render_template("login.html", error=error)

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if "usuario_id" not in session or session.get("rol") != "admin":
        return redirect(url_for("auth.login"))

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    if request.method == "POST":
        nombre = request.form["nombre"]
        correo = request.form["correo"]
        contrasena = generate_password_hash(request.form["contrasena"])
        rol = request.form["rol"]
        id_sucursal = request.form["id_sucursal"]

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
            return redirect(url_for("ventas.ventas"))

    cursor.execute("SELECT id, nombre FROM sucursales")
    sucursales = cursor.fetchall()

    cursor.close()
    conexion.close()

    return render_template("register.html", sucursales=sucursales)

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
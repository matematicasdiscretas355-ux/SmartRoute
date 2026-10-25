
from flask import (
    Flask, render_template, render_template_string,
    request, redirect, url_for, session, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import sqlite3
import os

# ============================================
# IMPORTAR LOS SEIS MODULOS
# ============================================

from MODULOS.PEDIDOS.pedidos import (
    pedidos_bp,
    inicializar_base_pedidos
)
from MODULOS.ASIGNACION.routes import modulo3_bp
from MODULOS.cobertura import cobertura_bp
from MODULOS.RUTAS.routes import modulo5_bp
from MODULOS.JERARQUIA.routes import modulo6_bp

# ============================================
# CONFIGURACION
# ============================================

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY", "SmartRoute-clave-local-2026"
)

CARPETA = os.path.dirname(os.path.abspath(__file__))
RUTA_DB = os.path.join(CARPETA, "vehiculos.db")
app.config["PEDIDOS_DB_PATH"] = os.path.join(CARPETA, "pedidos.db")

USUARIO = "admin"
CLAVE_HASH = generate_password_hash("SmartRoute2026!")

# ============================================
# BASE DE DATOS
# ============================================

def conectar():
    return sqlite3.connect(RUTA_DB)


def fecha_actual():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def crear_tabla():
    conexion = conectar()

    conexion.execute("""
        CREATE TABLE IF NOT EXISTS vehiculos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            placa TEXT UNIQUE NOT NULL,
            marca TEXT NOT NULL,
            modelo TEXT NOT NULL,
            anio INTEGER NOT NULL,
            capacidad_peso REAL NOT NULL,
            capacidad_volumen REAL NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Disponible'
        )
    """)

    columnas = [
        fila[1] for fila in
        conexion.execute("PRAGMA table_info(vehiculos)").fetchall()
    ]

    if "fecha_creacion" not in columnas:
        conexion.execute("""
            ALTER TABLE vehiculos
            ADD COLUMN fecha_creacion TEXT
        """)
        conexion.execute("""
            UPDATE vehiculos
            SET fecha_creacion = ?
            WHERE fecha_creacion IS NULL
        """, (fecha_actual(),))

    if "fecha_eliminacion" not in columnas:
        conexion.execute("""
            ALTER TABLE vehiculos
            ADD COLUMN fecha_eliminacion TEXT
        """)

    if "eliminado" not in columnas:
        conexion.execute("""
            ALTER TABLE vehiculos
            ADD COLUMN eliminado INTEGER NOT NULL DEFAULT 0
        """)

    conexion.execute("""
        CREATE TABLE IF NOT EXISTS usuarios_vehiculos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            contrasena TEXT NOT NULL
        )
    """)

    cantidad = conexion.execute(
        "SELECT COUNT(*) FROM usuarios_vehiculos"
    ).fetchone()[0]

    if cantidad == 0:
        conexion.execute("""
            INSERT INTO usuarios_vehiculos
            (usuario, contrasena) VALUES (?, ?)
        """, (
            "adminveh",
            generate_password_hash("Ruta2026!")
        ))

    conexion.commit()
    conexion.close()


# ============================================
# USUARIOS INDEPENDIENTES
# ============================================

def crear_usuario_modulo(base, tabla, usuario, clave):
    tablas_permitidas = {
        "usuarios_pedidos",
        "usuarios_asignacion",
        "usuarios_cobertura",
        "usuarios_rutas",
        "usuarios_jerarquia"
    }

    if tabla not in tablas_permitidas:
        raise ValueError("Tabla no permitida")

    conexion = sqlite3.connect(base)

    conexion.execute(f"""
        CREATE TABLE IF NOT EXISTS {tabla} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            contrasena TEXT NOT NULL
        )
    """)

    existe = conexion.execute(
        f"SELECT id FROM {tabla} WHERE usuario = ?",
        (usuario,)
    ).fetchone()

    if not existe:
        conexion.execute(
            f"INSERT INTO {tabla} (usuario, contrasena) VALUES (?, ?)",
            (usuario, generate_password_hash(clave))
        )

    conexion.commit()
    conexion.close()


def inicializar_usuarios_pedidos():
    crear_usuario_modulo(
        app.config["PEDIDOS_DB_PATH"],
        "usuarios_pedidos", "adminped", "Pedidos2026!"
    )


def inicializar_usuarios_asignacion():
    crear_usuario_modulo(
        RUTA_DB, "usuarios_asignacion",
        "adminasig", "Asignacion2026!"
    )


def inicializar_usuarios_cobertura():
    conexion = conectar()

    conexion.execute("""
        CREATE TABLE IF NOT EXISTS usuarios_cobertura (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            contrasena TEXT NOT NULL
        )
    """)

    usuario = "admincobertura"
    clave = "Cobertura2026!"

    cuenta = conexion.execute("""
        SELECT contrasena
        FROM usuarios_cobertura
        WHERE usuario = ?
    """, (usuario,)).fetchone()

    if cuenta is None:
        conexion.execute("""
            INSERT INTO usuarios_cobertura
            (usuario, contrasena)
            VALUES (?, ?)
        """, (
            usuario,
            generate_password_hash(clave)
        ))

    elif not check_password_hash(cuenta[0], clave):
        conexion.execute("""
            UPDATE usuarios_cobertura
            SET contrasena = ?
            WHERE usuario = ?
        """, (
            generate_password_hash(clave),
            usuario
        ))

    conexion.commit()
    conexion.close()


def inicializar_usuarios_rutas():
    crear_usuario_modulo(
        RUTA_DB, "usuarios_rutas",
        "adminrutas", "Rutas2026!"
    )


def inicializar_usuarios_jerarquia():
    crear_usuario_modulo(
        RUTA_DB, "usuarios_jerarquia",
        "adminjerarquia", "Jerarquia2026!"
    )


# ============================================
# INICIALIZACION
# ============================================

crear_tabla()
inicializar_base_pedidos(app)
inicializar_usuarios_pedidos()
inicializar_usuarios_asignacion()
inicializar_usuarios_cobertura()
inicializar_usuarios_rutas()
inicializar_usuarios_jerarquia()

app.register_blueprint(pedidos_bp)
app.register_blueprint(modulo3_bp)
app.register_blueprint(cobertura_bp)
app.register_blueprint(modulo5_bp)
app.register_blueprint(modulo6_bp)


# ============================================
# PROTECCION DE ACCESOS
# ============================================

def requiere_login(funcion):
    @wraps(funcion)
    def verificar(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return funcion(*args, **kwargs)
    return verificar


def requiere_acceso_vehiculos(funcion):
    @wraps(funcion)
    def verificar(*args, **kwargs):
        if not session.get("acceso_vehiculos"):
            return redirect(url_for("acceso_vehiculos"))
        return funcion(*args, **kwargs)
    return verificar


# ============================================
# LOGIN PRINCIPAL
# ============================================

@app.route("/login", methods=["GET", "POST"])
def login():
    mensaje = ""

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        contrasena = request.form.get("contrasena", "")

        if (
            usuario == USUARIO
            and check_password_hash(CLAVE_HASH, contrasena)
        ):
            session.clear()
            session["usuario"] = usuario
            return redirect(url_for("menu"))

        mensaje = "Usuario o contraseña incorrectos."

    return render_template("login.html", mensaje=mensaje)


@app.route("/cerrar_sesion")
def cerrar_sesion():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@requiere_login
def menu():
    return render_template("menu.html")


# ============================================
# VERIFICAR CREDENCIALES DE MODULOS
# ============================================

def verificar_usuario_modulo(base, tabla, usuario, clave):
    tablas_permitidas = {
        "usuarios_vehiculos",
        "usuarios_pedidos",
        "usuarios_asignacion",
        "usuarios_cobertura",
        "usuarios_rutas",
        "usuarios_jerarquia"
    }

    if tabla not in tablas_permitidas:
        return False

    conexion = sqlite3.connect(base)
    cuenta = conexion.execute(
        f"SELECT contrasena FROM {tabla} WHERE usuario = ?",
        (usuario,)
    ).fetchone()
    conexion.close()

    if not cuenta:
        return False

    return check_password_hash(cuenta[0], clave)


# ============================================
# MODULO 2 - ACCESO VEHICULOS
# ============================================

@app.route("/acceso-vehiculos", methods=["GET", "POST"])
@requiere_login
def acceso_vehiculos():
    mensaje = ""

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("contrasena", "")

        if verificar_usuario_modulo(
            RUTA_DB, "usuarios_vehiculos", usuario, clave
        ):
            session["acceso_vehiculos"] = True
            session["usuario_vehiculos"] = usuario
            return redirect(url_for("inicio"))

        mensaje = "Usuario o contraseña incorrectos."

    return render_template("acceso_vehiculos.html", mensaje=mensaje)


# ============================================
# CREAR USUARIO DE VEHICULOS
# ============================================

@app.route("/crear-usuario-vehiculos", methods=["GET", "POST"])
@requiere_login
def crear_usuario_vehiculos():
    if session.get("usuario") != "admin":
        return "No tienes permiso para crear usuarios.", 403

    mensaje = ""

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("contrasena", "")

        if len(usuario) < 3:
            mensaje = "El usuario debe tener al menos 3 caracteres."
        elif len(clave) < 8:
            mensaje = "La contraseña debe tener al menos 8 caracteres."
        else:
            conexion = conectar()
            try:
                conexion.execute("""
                    INSERT INTO usuarios_vehiculos
                    (usuario, contrasena)
                    VALUES (?, ?)
                """, (
                    usuario,
                    generate_password_hash(clave)
                ))
                conexion.commit()
                mensaje = "Usuario creado correctamente."
            except sqlite3.IntegrityError:
                mensaje = "Ese usuario ya existe."
            finally:
                conexion.close()

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Crear usuario</title>
        <style>
            body {
                font-family: Arial;
                background: #eef3f9;
            }
            .caja {
                max-width: 420px;
                margin: 60px auto;
                padding: 30px;
                background: white;
                border-radius: 15px;
            }
            input, button {
                display: block;
                width: 100%;
                padding: 12px;
                margin: 12px 0;
                box-sizing: border-box;
            }
            button {
                background: #2457a7;
                color: white;
                border: none;
            }
        </style>
    </head>
    <body>
        <div class="caja">
            <h2>Crear usuario de vehículos</h2>
            <p>{{ mensaje }}</p>
            <form method="POST">
                <input name="usuario" placeholder="Usuario" required>
                <input name="contrasena" type="password"
                       placeholder="Contraseña" required>
                <button>Crear usuario</button>
            </form>
            <a href="{{ url_for('menu') }}">Volver</a>
        </div>
    </body>
    </html>
    """, mensaje=mensaje)


@app.route("/cerrar-acceso-vehiculos")
@requiere_login
def cerrar_acceso_vehiculos():
    session.pop("acceso_vehiculos", None)
    session.pop("usuario_vehiculos", None)
    return redirect(url_for("menu"))


# ============================================
# COMPROBAR PLACA
# ============================================

@app.route("/comprobar-placa")
@requiere_login
@requiere_acceso_vehiculos
def comprobar_placa():
    placa = request.args.get("placa", "").strip().upper()

    if not placa:
        return jsonify({"existe": False})

    conexion = conectar()
    existe = conexion.execute("""
        SELECT id FROM vehiculos
        WHERE UPPER(placa) = ?
        AND eliminado = 0
    """, (placa,)).fetchone()
    conexion.close()

    return jsonify({"existe": existe is not None})


# ============================================
# MODULO 2 - GESTION DE VEHICULOS
# ============================================

@app.route("/vehiculos", methods=["GET", "POST"])
@requiere_login
@requiere_acceso_vehiculos
def inicio():
    mensaje = ""

    if request.method == "POST":
        conexion = conectar()
        try:
            conexion.execute("""
                INSERT INTO vehiculos (
                    placa, marca, modelo, anio,
                    capacidad_peso, capacidad_volumen,
                    estado, fecha_creacion,
                    fecha_eliminacion, eliminado
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 0)
            """, (
                request.form["placa"].strip().upper(),
                request.form["marca"].strip(),
                request.form["modelo"].strip(),
                int(request.form["anio"]),
                float(request.form["capacidad_peso"]),
                float(request.form["capacidad_volumen"]),
                request.form["estado"],
                fecha_actual()
            ))
            conexion.commit()
            return redirect(url_for("inicio"))

        except sqlite3.IntegrityError:
            mensaje = "Esa placa ya está registrada."
        except (ValueError, KeyError):
            mensaje = "Revisa los datos ingresados."
        finally:
            conexion.close()

    buscar = request.args.get("buscar", "").strip()
    conexion = conectar()

    if buscar:
        vehiculos = conexion.execute("""
            SELECT * FROM vehiculos
            WHERE eliminado = 0
            AND (placa LIKE ? OR marca LIKE ?)
            ORDER BY id DESC
        """, (
            "%" + buscar + "%",
            "%" + buscar + "%"
        )).fetchall()
    else:
        vehiculos = conexion.execute("""
            SELECT * FROM vehiculos
            WHERE eliminado = 0
            ORDER BY id DESC
        """).fetchall()

    total = conexion.execute("""
        SELECT COUNT(*) FROM vehiculos
        WHERE eliminado = 0
    """).fetchone()[0]

    disponibles = conexion.execute("""
        SELECT COUNT(*) FROM vehiculos
        WHERE eliminado = 0
        AND estado = 'Disponible'
    """).fetchone()[0]

    en_uso = conexion.execute("""
        SELECT COUNT(*) FROM vehiculos
        WHERE eliminado = 0
        AND estado = 'En uso'
    """).fetchone()[0]

    conexion.close()

    return render_template(
        "index.html",
        vehiculos=vehiculos,
        mensaje=mensaje,
        buscar=buscar,
        total=total,
        disponibles=disponibles,
        en_uso=en_uso
    )


# ============================================
# CAMBIAR ESTADO DE VEHICULO
# ============================================

@app.route("/cambiar_estado", methods=["POST"])
@requiere_login
@requiere_acceso_vehiculos
def cambiar_estado():
    nuevo_estado = request.form.get("estado")

    if nuevo_estado not in (
        "Disponible", "En uso", "Mantenimiento"
    ):
        return redirect(url_for("inicio"))

    conexion = conectar()
    conexion.execute("""
        UPDATE vehiculos
        SET estado = ?
        WHERE id = ? AND eliminado = 0
    """, (
        nuevo_estado,
        request.form["id"]
    ))
    conexion.commit()
    conexion.close()

    return redirect(url_for("inicio"))


# ============================================
# ELIMINAR VEHICULO
# ============================================

@app.route("/eliminar", methods=["POST"])
@requiere_login
@requiere_acceso_vehiculos
def eliminar():
    conexion = conectar()
    conexion.execute("""
        UPDATE vehiculos
        SET eliminado = 1,
            fecha_eliminacion = ?
        WHERE id = ? AND eliminado = 0
    """, (
        fecha_actual(),
        request.form["id"]
    ))
    conexion.commit()
    conexion.close()

    return redirect(url_for("inicio"))


# ============================================
# VEHICULOS ELIMINADOS
# ============================================

@app.route("/eliminados")
@requiere_login
@requiere_acceso_vehiculos
def eliminados():
    conexion = conectar()
    vehiculos = conexion.execute("""
        SELECT * FROM vehiculos
        WHERE eliminado = 1
        ORDER BY fecha_eliminacion DESC, id DESC
    """).fetchall()
    conexion.close()

    return render_template(
        "eliminados.html",
        vehiculos=vehiculos
    )


# ============================================
# RESTAURAR VEHICULO
# ============================================

@app.route("/restaurar", methods=["POST"])
@requiere_login
@requiere_acceso_vehiculos
def restaurar():
    conexion = conectar()
    conexion.execute("""
        UPDATE vehiculos
        SET eliminado = 0,
            fecha_eliminacion = NULL
        WHERE id = ? AND eliminado = 1
    """, (request.form["id"],))
    conexion.commit()
    conexion.close()

    return redirect(url_for("eliminados"))


# ============================================
# MODULO 1 - ACCESO PEDIDOS
# ============================================

@app.route("/acceso-pedidos", methods=["GET", "POST"])
@requiere_login
def acceso_pedidos():
    mensaje = ""

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("contrasena", "")

        if verificar_usuario_modulo(
            app.config["PEDIDOS_DB_PATH"],
            "usuarios_pedidos",
            usuario, clave
        ):
            session["acceso_pedidos"] = True
            session["usuario_pedidos"] = usuario
            return redirect(url_for("gestion_pedidos.listar"))

        mensaje = "Usuario o contraseña incorrectos."

    return render_template(
        "acceso_pedidos.html", mensaje=mensaje
    )


@app.route("/cerrar-acceso-pedidos")
@requiere_login
def cerrar_acceso_pedidos():
    session.pop("acceso_pedidos", None)
    session.pop("usuario_pedidos", None)
    return redirect(url_for("menu"))


# ============================================
# MODULO 3 - ACCESO ASIGNACION
# ============================================

@app.route("/acceso-asignacion", methods=["GET", "POST"])
@requiere_login
def acceso_asignacion():
    mensaje = ""

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("contrasena", "")

        if verificar_usuario_modulo(
            RUTA_DB, "usuarios_asignacion",
            usuario, clave
        ):
            session["acceso_asignacion"] = True
            session["usuario_asignacion"] = usuario
            return redirect(
                url_for("modulo3.vista_asignacion_combinatoria")
            )

        mensaje = "Usuario o contraseña incorrectos."

    return render_template(
        "acceso_asignacion.html", mensaje=mensaje
    )


@app.route("/cerrar-acceso-asignacion")
@requiere_login
def cerrar_acceso_asignacion():
    session.pop("acceso_asignacion", None)
    session.pop("usuario_asignacion", None)
    return redirect(url_for("menu"))


# ============================================
# MODULO 4 - ACCESO COBERTURA CORREGIDO
# ============================================

@app.route("/acceso-cobertura", methods=["GET", "POST"])
@requiere_login
def acceso_cobertura():
    mensaje = ""

    if request.method == "POST":

        # Campos exclusivos para evitar la confusion
        # con el inicio de sesion principal.
        usuario = request.form.get(
            "usuario_exclusivo_cobertura", ""
        ).strip()

        clave = request.form.get(
            "clave_exclusiva_cobertura", ""
        )

        print("====================================")
        print("VERIFICACION DEL MODULO 4")
        print("USUARIO RECIBIDO:", repr(usuario))

        acceso_valido = verificar_usuario_modulo(
            RUTA_DB,
            "usuarios_cobertura",
            usuario,
            clave
        )

        print("CREDENCIALES VALIDAS:", acceso_valido)

        if acceso_valido:
            session["acceso_cobertura"] = True
            session["usuario_cobertura"] = usuario
            session.modified = True

            print("ACCESO CORRECTO AL MODULO 4")
            print("====================================")

            return redirect(
                url_for(
                    "smartroute_cobertura.smartroute_cobertura_inicio"
                )
            )

        mensaje = "Usuario o contraseña incorrectos."
        print("ACCESO DENEGADO AL MODULO 4")
        print("====================================")

    elif session.get("acceso_cobertura"):
        return redirect(
            url_for(
                "smartroute_cobertura.smartroute_cobertura_inicio"
            )
        )

    return render_template(
        "acceso_cobertura.html",
        mensaje=mensaje
    )


# ============================================
# CERRAR ACCESO COBERTURA
# ============================================

@app.route("/cerrar-acceso-cobertura")
@requiere_login
def cerrar_acceso_cobertura():
    session.pop("acceso_cobertura", None)
    session.pop("usuario_cobertura", None)
    return redirect(url_for("menu"))


# ============================================
# MODULO 5 - ACCESO RUTAS
# ============================================

@app.route("/acceso-rutas", methods=["GET", "POST"])
@requiere_login
def acceso_rutas():
    mensaje = ""

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("contrasena", "")

        if verificar_usuario_modulo(
            RUTA_DB, "usuarios_rutas", usuario, clave
        ):
            session["acceso_rutas"] = True
            session["usuario_rutas"] = usuario
            return redirect(url_for("modulo5.visualizar_rutas"))

        mensaje = "Usuario o contraseña incorrectos."

    return render_template(
        "acceso_rutas.html", mensaje=mensaje
    )


@app.route("/cerrar-acceso-rutas")
@requiere_login
def cerrar_acceso_rutas():
    session.pop("acceso_rutas", None)
    session.pop("usuario_rutas", None)
    return redirect(url_for("menu"))


# ============================================
# MODULO 6 - ACCESO JERARQUIA
# ============================================

@app.route("/acceso-jerarquia", methods=["GET", "POST"])
@requiere_login
def acceso_jerarquia():
    mensaje = ""

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("contrasena", "")

        if verificar_usuario_modulo(
            RUTA_DB, "usuarios_jerarquia",
            usuario, clave
        ):
            session["acceso_jerarquia"] = True
            session["usuario_jerarquia"] = usuario
            return redirect(
                url_for("modulo6.visualizar_jerarquia")
            )

        mensaje = "Usuario o contraseña incorrectos."

    return render_template(
        "acceso_jerarquia.html", mensaje=mensaje
    )


@app.route("/cerrar-acceso-jerarquia")
@requiere_login
def cerrar_acceso_jerarquia():
    session.pop("acceso_jerarquia", None)
    session.pop("usuario_jerarquia", None)
    return redirect(url_for("menu"))


# ============================================
# INICIAR SMARTROUTE WEB
# ============================================

if __name__ == "__main__":
    app.run(debug=True)

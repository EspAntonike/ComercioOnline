from flask import Flask, render_template, request, jsonify
from pathlib import Path
import sqlite3
import hashlib
import os
import zipfile

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "products.db"   # BD actual en uso
TEMP_PATH = BASE_DIR / "db_temp.db"  # BD en espera (recibida desde subir.py)
DBR_PATH = BASE_DIR / "reseñasDB.db"
UPLOADS_DIR = BASE_DIR / "static" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 🔑 Hash SHA256 de la contraseña correcta
PASSWORD_HASH = "c40e957c730718233694f439449d0166bceea4d46007c789319686233545bc54"


def get_conn():
    """Devuelve conexión a la BD actual"""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_connR():
    """Devuelve conexión a la BD de reseñas"""
    if not DBR_PATH.exists():
        return None
    conn = sqlite3.connect(DBR_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def inicio():
    conn = get_conn()
    destacados = []
    if conn:
        sql = """ SELECT * FROM products ORDER BY COALESCE(entradas,0) DESC LIMIT 5 """
        destacados = conn.execute(sql).fetchall()
        conn.close()
    return render_template("inicio.html", destacados=destacados)


@app.route("/index")
def index():
    # 🔄 Si hay una nueva BD en TEMP, la activamos
    if TEMP_PATH.exists():
        os.replace(TEMP_PATH, DB_PATH)

    conn = get_conn()
    if conn is None:
        return "⚠️ No hay base de datos disponible. Sube una con subir.py.", 503

    # 📌 Parámetros de búsqueda
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", "").strip()
    sexo = request.args.get("sexo", "").strip()
    tallas_selected = request.args.get("tallas", "").strip()
    precio_min = request.args.get("precio_min", "").strip()
    precio_max = request.args.get("precio_max", "").strip()

    # -------------------------------
    # Construcción de SQL para productos
    # -------------------------------
    sql = "SELECT * FROM products WHERE 1=1"
    params = []

    if q:
        sql += " AND (name LIKE ? OR description LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])
    if cat:
        sql += " AND category = ?"
        params.append(cat)
    if sexo:
        sql += " AND sexo = ?"
        params.append(sexo)
    if tallas_selected:
        sql += " AND tallas LIKE ?"
        params.append(f"%{tallas_selected}%")
    if precio_min:
        sql += " AND precio >= ?"
        params.append(precio_min)
    if precio_max:
        sql += " AND precio <= ?"
        params.append(precio_max)

    sql += " ORDER BY created_at DESC"
    products = conn.execute(sql, params).fetchall()

    # -------------------------------
    # Filtros dinámicos
    # -------------------------------
    base_sql = "FROM products WHERE 1=1"
    dyn_params = []

    if q:
        base_sql += " AND (name LIKE ? OR description LIKE ?)"
        dyn_params.extend([f"%{q}%", f"%{q}%"])
    if cat:
        base_sql += " AND category = ?"
        dyn_params.append(cat)
    if sexo:
        base_sql += " AND sexo = ?"
        dyn_params.append(sexo)
    if tallas_selected:
        base_sql += " AND tallas LIKE ?"
        dyn_params.append(f"%{tallas_selected}%")
    if precio_min:
        base_sql += " AND precio >= ?"
        dyn_params.append(precio_min)
    if precio_max:
        base_sql += " AND precio <= ?"
        dyn_params.append(precio_max)

    categories = [r["category"] for r in conn.execute(f"SELECT DISTINCT category {base_sql} ORDER BY category", dyn_params).fetchall()]
    sexos_list = [r["sexo"] for r in conn.execute(f"SELECT DISTINCT sexo {base_sql} ORDER BY sexo", dyn_params).fetchall() if r["sexo"]]

    # 🔹 Separar tallas
    tallas_list_raw = [r["tallas"] for r in conn.execute(f"SELECT DISTINCT tallas {base_sql} ORDER BY tallas", dyn_params).fetchall() if r["tallas"]]
    tallas_list = []
    for t in tallas_list_raw:
        tallas_list.extend(t.split("-"))
    tallas_list = sorted(set(tallas_list))

    row = conn.execute(f"SELECT MIN(precio) as minp, MAX(precio) as maxp {base_sql}", dyn_params).fetchone()
    precio_min_auto = row["minp"] if row and row["minp"] is not None else 0
    precio_max_auto = row["maxp"] if row and row["maxp"] is not None else 0
    conn.close()

    return render_template(
        "index.html",
        products=products,
        categories=categories,
        sexos=sexos_list,
        tallas=tallas_list,
        q=q,
        cat=cat,
        sexo=sexo,
        tallas_selected=tallas_selected,
        precio_min=precio_min,
        precio_max=precio_max,
        precio_min_auto=precio_min_auto,
        precio_max_auto=precio_max_auto,
    )


@app.route("/filtros")
def filtros():
    """Devuelve las opciones de filtros dinámicos según lo seleccionado"""
    conn = get_conn()
    if conn is None:
        return jsonify({"error": "No hay BD"}), 503

    q = request.args.get("q", "").strip()
    cat = request.args.get("category", "").strip()
    sexo = request.args.get("sexo", "").strip()
    tallas_selected = request.args.get("tallas", "").strip()
    precio_min = request.args.get("precio_min", "").strip()
    precio_max = request.args.get("precio_max", "").strip()

    base_sql = "FROM products WHERE 1=1"
    dyn_params = []

    if q:
        base_sql += " AND (name LIKE ? OR description LIKE ?)"
        dyn_params.extend([f"%{q}%", f"%{q}%"])
    if cat:
        base_sql += " AND category = ?"
        dyn_params.append(cat)
    if sexo:
        base_sql += " AND sexo = ?"
        dyn_params.append(sexo)
    if tallas_selected:
        base_sql += " AND tallas LIKE ?"
        dyn_params.append(f"%{tallas_selected}%")
    if precio_min:
        base_sql += " AND precio >= ?"
        dyn_params.append(precio_min)
    if precio_max:
        base_sql += " AND precio <= ?"
        dyn_params.append(precio_max)

    categories = [r["category"] for r in conn.execute(f"SELECT DISTINCT category {base_sql} ORDER BY category", dyn_params).fetchall()]
    sexos_list = [r["sexo"] for r in conn.execute(f"SELECT DISTINCT sexo {base_sql} ORDER BY sexo", dyn_params).fetchall() if r["sexo"]]

    # 🔹 Separar tallas
    tallas_list_raw = [r["tallas"] for r in conn.execute(f"SELECT DISTINCT tallas {base_sql} ORDER BY tallas", dyn_params).fetchall() if r["tallas"]]
    tallas_list = []
    for t in tallas_list_raw:
        tallas_list.extend(t.split("-"))
    tallas_list = sorted(set(tallas_list))

    row = conn.execute(f"SELECT MIN(precio) as minp, MAX(precio) as maxp {base_sql}", dyn_params).fetchone()
    conn.close()

    return jsonify({
        "categories": categories,
        "sexos": sexos_list,
        "tallas": tallas_list,
        "precio_min_auto": row["minp"] if row and row["minp"] is not None else 0,
        "precio_max_auto": row["maxp"] if row and row["maxp"] is not None else 0,
    })


@app.route("/producto/<int:pid>", methods=["GET", "POST"])
def producto(pid):
    """Página de detalle de un producto con reseñas"""
    conn = get_conn()
    if conn is None:
        return "⚠️ No hay base de datos disponible.", 503

    prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    conn.close()

    if not prod:
        return "❌ Producto no encontrado", 404

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        reseña = request.form.get("reseña", "").strip()
        valoracion = request.form.get("valoracion", "").strip()

        if nombre and reseña and valoracion:
            try:
                valoracion = float(valoracion)
            except ValueError:
                valoracion = 0

            connR = get_connR()
            if connR is None:
                return "⚠️ No hay base de datos de reseñas disponible.", 503

            connR.execute(
                "INSERT INTO reseñas (id_pagina, nombre, reseña, valoracion) VALUES (?, ?, ?, ?)",
                (pid, nombre, reseña, valoracion),
            )
            connR.commit()
            connR.close()

    connR = get_connR()
    reseñas = []
    if connR:
        reseñas = connR.execute(
            "SELECT nombre, reseña, valoracion FROM reseñas WHERE id_pagina = ? ORDER BY id DESC",
            (pid,),
        ).fetchall()
        connR.close()

    return render_template("producto.html", p=prod, reseñas=reseñas)


@app.route("/receive", methods=["POST"])
def receive():
    password = request.form.get("password", "")
    dbfile = request.files.get("dbfile")
    zipfile_in = request.files.get("zipfile")

    if not password or (not dbfile and not zipfile_in):
        return "FALTAN DATOS", 400

    phash = hashlib.sha256(password.encode()).hexdigest()
    if phash != PASSWORD_HASH:
        return "FAIL", 403

    # 📌 Si es base de datos
    if dbfile:
        dbfile.save(TEMP_PATH)
        try:
            with sqlite3.connect(TEMP_PATH) as conn:
                rows = conn.execute("SELECT COUNT(*) FROM products").fetchone()
                print(f"✅ BD recibida con {rows[0]} productos (esperando refresco del navegador)")
        except Exception as e:
            return f"ERROR: {e}", 500
        return "OK", 200

    # 📌 Si es zip con imágenes
    if zipfile_in:
        temp_zip = BASE_DIR / "uploads_temp.zip"
        zipfile_in.save(temp_zip)

        try:
            with zipfile.ZipFile(temp_zip, "r") as zip_ref:
                zip_ref.extractall(UPLOADS_DIR)
            temp_zip.unlink()  # borramos el zip
            print(f"✅ Imágenes extraídas en {UPLOADS_DIR}")
        except Exception as e:
            return f"ERROR al descomprimir: {e}", 500
        return "OK", 200

    return "ERROR: No se recibió archivo válido", 400


@app.route("/todos")
def todos():
    conn = get_conn()
    productos = []
    if conn:
        sql = """ SELECT * FROM products ORDER BY COALESCE(entradas,0) DESC """
        productos = conn.execute(sql).fetchall()
        conn.close()
    return render_template("todos.html", productos=productos)


@app.route("/click/<int:pid>", methods=["POST"])
def registrar_click(pid):
    conn = get_conn()
    if conn is None:
        return jsonify({"error": "No hay BD disponible"}), 503
    try:
        conn.execute("UPDATE products SET entradas = COALESCE(entradas,0) + 1 WHERE id = ?", (pid,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
    
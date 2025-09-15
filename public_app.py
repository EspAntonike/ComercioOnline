from flask import Flask, render_template, request, jsonify
from pathlib import Path
import sqlite3
import hashlib
import os
import base64
import requests
import json
from typing import List, Tuple, Optional


# Crypto (cryptography). Si no está instalado: pip install cryptography
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "products.db"   # BD actual en uso
TEMP_PATH = BASE_DIR / "db_temp.db"  # BD en espera (recibida desde subir.py)
DBR_PATH = BASE_DIR / "reseñasDB.db"

# 🔑 Hash SHA256 de la contraseña correcta
PASSWORD_HASH = "c40e957c730718233694f439449d0166bceea4d46007c789319686233545bc54"

GITHUB_REPO = "EspAntonike/ComercioOnline"
GITHUB_IMAGES_PATH = "templates"
GITHUB_API_BASE = "https://api.github.com"

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

# -------------------- helpers para imágenes y GitHub --------------------

def try_load_private_key(pem_bytes: bytes, password: Optional[bytes] = None):
    """Carga una llave privada PEM (bytes). No la guarda en disco."""
    return load_pem_private_key(pem_bytes, password=password)


def rsa_decrypt(private_key_obj, ciphertext: bytes) -> bytes:
    """Descifra datos con OAEP.
    private_key_obj debe ser el objeto devuelto por load_pem_private_key.
    """
    return private_key_obj.decrypt(
        ciphertext,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )


def github_put_file(path_in_repo: str, content_bytes: bytes, commit_message: str) -> Tuple[bool, str]:
    """Sube/actualiza un archivo en GitHub usando el token de entorno.
    Devuelve (ok, mensaje o url)
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return False, "No hay GITHUB_TOKEN en variables de entorno"

    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{path_in_repo}"
    b64 = base64.b64encode(content_bytes).decode("ascii")

    # Primero: comprobar si ya existe para obtener el sha
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    resp = requests.get(url, headers=headers, timeout=20)
    payload = {"message": commit_message, "content": b64}
    if resp.status_code == 200:
        # existe -> update necesita sha
        sha = resp.json().get("sha")
        payload["sha"] = sha

    r = requests.put(url, headers=headers, data=json.dumps(payload), timeout=30)
    if r.status_code in (200, 201):
        return True, r.json().get("content", {}).get("html_url", "OK")
    else:
        return False, f"GitHub error {r.status_code}: {r.text}"


def extract_image_fields_from_db(conn: sqlite3.Connection) -> List[Tuple[str, Optional[bytes]]]:
    """Intento razonable de extraer imágenes (o paths) desde la tabla 'products'.
    Devuelve lista de tuplas (filename_or_key, bytes_or_None)
    - Si la columna contiene un path/nombre -> bytes_or_None será None (se intentará leerlo en disco)
    - Si la columna es BLOB -> bytes_or_None contendrá los bytes

    *Se prueba un conjunto de nombres de columna comunes.*
    """
    candidates = ["image", "imagen", "images", "foto", "img", "image_path", "image_url", "picture", "photo"]
    out = []
    cur = conn.execute("PRAGMA table_info(products)")
    cols = [r[1] for r in cur.fetchall()]

    # Buscar columnas que coincidan con posibles nombres
    found = [c for c in cols if c.lower() in candidates]

    # Si no hay columnas con esos nombres, devolvemos intento con columnas que sean TEXT o BLOB
    if not found:
        # Intentar devolver cualquier columna con tipo BLOB o TEXT que parezca contener imágenes
        info = conn.execute("PRAGMA table_info(products)").fetchall()
        for cid, name, ctype, notnull, dflt, pk in info:
            if ctype and ctype.lower() in ("blob", "bytea"):
                found.append(name)

    if not found:
        # última opción: mirar la primera fila y buscar campos que parezcan rutas (terminan en .png/.jpg/.jpeg/.webp/.enc)
        row = conn.execute("SELECT * FROM products LIMIT 1").fetchone()
        if row:
            for k in row.keys():
                v = row[k]
                if isinstance(v, str) and any(v.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".enc")):
                    found.append(k)

    # ahora extraer todos los valores de las columnas encontradas
    if not found:
        return out

    sql = f"SELECT id, {', '.join(found)} FROM products"
    rows = conn.execute(sql).fetchall()
    for r in rows:
        pid = r[0]
        for col in found:
            val = r[col]
            if val is None:
                continue
            if isinstance(val, (bytes, bytearray)):
                out.append((f"product_{pid}_{col}", bytes(val)))
            elif isinstance(val, str):
                out.append((val, None))
            else:
                # intentar convertir a str
                out.append((str(val), None))
    return out


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
    """Recibe la BD (igual que antes) + opcionalmente rsa_private_key y rsa_public_key.
    - Guarda la BD temporalmente (TEMP_PATH) para que index() la active cuando exista.
    - Intenta extraer imágenes referenciadas en la BD y subirlas a GitHub (no guarda las keys en disco).
    """
    password = request.form.get("password", "")
    file = request.files.get("dbfile")

    if not password or not file:
        return "FALTAN DATOS", 400

    phash = hashlib.sha256(password.encode()).hexdigest()
    if phash != PASSWORD_HASH:
        return "FAIL", 403

    # archivos de llave opcionales (no se guardan en disco)
    rsa_priv = request.files.get("rsa_private_key")
    rsa_pub = request.files.get("rsa_public_key")
    private_key_obj = None
    if rsa_priv:
        pem = rsa_priv.read()
        try:
            private_key_obj = try_load_private_key(pem)
        except Exception as e:
            return f"ERROR llave privada: {e}", 400

    # Guardar temporalmente la BD (la app principal la re-activará si existe TEMP_PATH)
    file.save(TEMP_PATH)
    # probar abrir y contar
    try:
        with sqlite3.connect(TEMP_PATH) as conn:
            rows = conn.execute("SELECT COUNT(*) FROM products").fetchone()
            print(f"✅ BD recibida con {rows[0]} productos (esperando refresco del navegador)")

            # intentar extraer imágenes y subirlas
            images = extract_image_fields_from_db(conn)
            uploaded = []
            for name_or_path, blob in images:
                try:
                    content_bytes = None
                    filename = Path(name_or_path).name

                    if blob is not None:
                        # valor BLOB desde la BD
                        content_bytes = blob
                    else:
                        # intentar leer desde disco relativo a templates/
                        candidate = BASE_DIR / "templates" / name_or_path
                        candidate_alt = BASE_DIR / "templates" / filename
                        if candidate.exists():
                            content_bytes = candidate.read_bytes()
                        elif candidate_alt.exists():
                            content_bytes = candidate_alt.read_bytes()
                        else:
                            # no encontrado en disco. Ignorar.
                            print(f"imagen no encontrada en disco: {name_or_path}")
                            continue

                    # detectar si está cifrada: heurística
                    if content_bytes.startswith(b"ENCRYPTED:") or filename.lower().endswith(".enc"):
                        if private_key_obj is None:
                            print("Imagen cifrada pero no se proporcionó llave privada: salto")
                            continue
                        # quitar prefijo y base64-decode
                        if content_bytes.startswith(b"ENCRYPTED:"):
                            b64 = content_bytes.split(b":", 1)[1].strip()
                            ciphertext = base64.b64decode(b64)
                        else:
                            ciphertext = content_bytes
                        try:
                            content_bytes = rsa_decrypt(private_key_obj, ciphertext)
                        except Exception as e:
                            print(f"Error descifrando {name_or_path}: {e}")
                            continue

                    # subir a GitHub
                    path_in_repo = f"{GITHUB_IMAGES_PATH}/{filename}"
                    ok, msg = github_put_file(path_in_repo, content_bytes, commit_message=f"Upload image {filename} from public_app")
                    uploaded.append((filename, ok, msg))
                except Exception as e:
                    print(f"Error procesando imagen {name_or_path}: {e}")

            print("Resumen subidas:", uploaded)

    except Exception as e:
        return f"ERROR: {e}", 500

    return "OK", 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)


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
    
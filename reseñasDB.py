import sqlite3
from pathlib import Path

# Ruta a la base de datos
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "reseñasDB.db"

# Conexión
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Crear tabla con el campo valoracion
cursor.execute("""
CREATE TABLE IF NOT EXISTS reseñas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_pagina INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    reseña TEXT NOT NULL,
    valoracion REAL CHECK(valoracion >= 0 AND valoracion <= 5)
)
""")

conn.commit()
conn.close()

print("✅ Tabla 'reseñas' creada con campo 'valoracion'.")

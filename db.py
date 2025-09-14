# db.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("products.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT,
    image_path TEXT,   -- ruta relativa en /static/uploads o URL absoluta
    afiliado TEXT,     -- enlace de afiliado
    entradas INTEGER DEFAULT 0, -- contador de entradas o clics
    tallas TEXT,       -- tallas disponibles (ejemplo: "S,M,L,XL")
    sexo TEXT,         -- masculino, femenino, unisex
    precio REAL,       -- precio del producto
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    with conn:
        conn.executescript(SCHEMA_SQL)
    conn.close()

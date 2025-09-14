import sqlite3

conn = sqlite3.connect("reseñasDB.db")
cursor = conn.cursor()

# Ver tablas
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("Tablas:", cursor.fetchall())

# Ver columnas de la tabla 'products'
cursor.execute("PRAGMA table_info(products);")
print("Columnas:", cursor.fetchall())

# Ver 5 filas de la tabla 'products'
cursor.execute("SELECT * FROM reseñas LIMIT 5;")
print("Datos:", cursor.fetchall())

conn.close()

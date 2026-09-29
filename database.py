import os
import pymysql

def koneksi():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "prediksi_komoditas"),
        cursorclass=pymysql.cursors.DictCursor,
        ssl={"ssl": {}} if os.getenv("DB_HOST") else None
    )
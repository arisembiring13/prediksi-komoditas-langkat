import pymysql

def koneksi():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='', # isi jika ada password
        database='prediksi_komoditas',
        cursorclass=pymysql.cursors.DictCursor
    )
from datetime import datetime
from functools import wraps
from flask import Flask, redirect, render_template, request, session, url_for
import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
)

from database import koneksi  # Koneksi database bawaan Anda

app = Flask(__name__)
app.secret_key = 'kunci_rahasia_sistem_prediksi_langkat'

# Format file Excel yang diizinkan untuk import data produksi
ALLOWED_EXCEL_EXTENSIONS = {'xlsx'}


def file_excel_diizinkan(filename):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXCEL_EXTENSIONS
    )


# Decorator untuk Memproteksi Halaman (Wajib Login)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


# Decorator khusus Admin/Pengelola Sistem
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))

        if session.get('role') != 'admin':
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)

    return decorated_function


# ==================== FITUR LOGIN & LOGOUT ====================


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        db = koneksi()
        cursor = db.cursor()
        cursor.execute(
            '''
            SELECT id, username, password, nama_lengkap, role
            FROM users
            WHERE username = %s AND password = %s
            ''',
            (username, password),
        )
        user = cursor.fetchone()

        if user:
            session['logged_in'] = True

            if isinstance(user, dict):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['nama_user'] = user.get('nama_lengkap') or user['username']
                session['role'] = user.get('role', 'user')
            else:
                # Urutan hasil SELECT:
                # 0=id, 1=username, 2=password, 3=nama_lengkap, 4=role
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['nama_user'] = user[3] if user[3] else user[1]
                session['role'] = user[4] if len(user) > 4 and user[4] else 'user'

            return redirect(url_for('dashboard'))
        else:
            return render_template(
                'login.html', error='Username atau Password salah!'
            )

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ==================== HALAMAN UTAMA & ROUTE ====================


@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    db = koneksi()
    cursor = db.cursor()

    cursor.execute('SELECT COUNT(*) as total_data FROM produksi')
    res_tot = cursor.fetchone()
    total_data = (
        res_tot['total_data']
        if isinstance(res_tot, dict)
        else res_tot[0]
        if res_tot
        else 0
    )

    cursor.execute(
        'SELECT COUNT(DISTINCT komoditas) as total_komoditas FROM produksi'
    )
    res_kom = cursor.fetchone()
    total_komoditas = (
        res_kom['total_komoditas']
        if isinstance(res_kom, dict)
        else res_kom[0]
        if res_kom
        else 0
    )

    cursor.execute('SELECT DISTINCT komoditas FROM produksi')
    daftar_komoditas = cursor.fetchall()

    return render_template(
        'dashboard.html',
        total_data=total_data,
        total_komoditas=total_komoditas,
        daftar_komoditas=daftar_komoditas,
    )


# --- ROUTE DATA (MENAMPILKAN, FILTER & INPUT DATA) ---
@app.route('/data', methods=['GET', 'POST'])
@login_required
def data():
    db = koneksi()
    cursor = db.cursor()

    # Pesan dari proses upload Excel
    sukses = request.args.get('sukses')
    error = request.args.get('error')

    if request.method == 'POST':
        # Hanya Admin/Pengelola Sistem yang boleh menambah data
        if session.get('role') != 'admin':
            return redirect(url_for('data'))

        komoditas = request.form.get('komoditas', '').strip()
        tahun = request.form.get('tahun')
        produksi = request.form.get('produksi')
        satuan = request.form.get('satuan', 'Ton')
        keterangan = request.form.get('keterangan', '-')
        tanggal_input = datetime.now().strftime('%d %b %Y %H:%M')

        # Cegah duplikasi berdasarkan kombinasi komoditas + tahun.
        cursor.execute(
            '''
                SELECT id
                FROM produksi
                WHERE LOWER(TRIM(komoditas)) = LOWER(TRIM(%s))
                  AND tahun = %s
                LIMIT 1
            ''',
            (komoditas, tahun),
        )

        if cursor.fetchone():
            return redirect(url_for(
                'data',
                error=(
                    f'Data {komoditas} tahun {tahun} sudah tersedia. '
                    'Silakan gunakan menu Edit untuk mengubah data.'
                ),
            ))

        try:
            query = """
                INSERT INTO produksi
                (komoditas, tahun, produksi, satuan, keterangan, tanggal_input)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(
                query,
                (komoditas, tahun, produksi, satuan, keterangan, tanggal_input),
            )
            db.commit()
        except Exception:
            db.rollback()
            query_basic = """
                INSERT INTO produksi (komoditas, tahun, produksi)
                VALUES (%s, %s, %s)
            """
            cursor.execute(query_basic, (komoditas, tahun, produksi))
            db.commit()

        return redirect(url_for(
            'data',
            sukses=f'Data {komoditas} tahun {tahun} berhasil ditambahkan.',
        ))

    cursor.execute('SELECT COUNT(*) as total_data FROM produksi')
    res_total = cursor.fetchone()
    total_data = (
        res_total['total_data']
        if isinstance(res_total, dict)
        else res_total[0]
        if res_total
        else 0
    )

    cursor.execute(
        'SELECT COUNT(DISTINCT komoditas) as total_komoditas FROM produksi'
    )
    res_kom = cursor.fetchone()
    total_komoditas = (
        res_kom['total_komoditas']
        if isinstance(res_kom, dict)
        else res_kom[0]
        if res_kom
        else 0
    )

    cursor.execute('SELECT MIN(tahun) as min_t, MAX(tahun) as max_t FROM produksi')
    res_thn = cursor.fetchone()
    if isinstance(res_thn, dict):
        min_t, max_t = res_thn.get('min_t', '-'), res_thn.get('max_t', '-')
    else:
        min_t, max_t = (res_thn[0], res_thn[1]) if res_thn else ('-', '-')

    cursor.execute('SELECT SUM(produksi) as total_prod FROM produksi')
    res_prod = cursor.fetchone()
    total_prod_val = (
        res_prod['total_prod']
        if isinstance(res_prod, dict)
        else res_prod[0]
        if res_prod
        else 0
    )
    total_prod_formatted = f'{total_prod_val:,.2f}' if total_prod_val else '0.00'

    ringkasan = {
        'total_data': total_data,
        'total_komoditas': total_komoditas,
        'rentang_tahun': f'{min_t} - {max_t}' if min_t and max_t else '-',
        'total_produksi': total_prod_formatted,
    }

    cursor.execute('SELECT * FROM produksi ORDER BY tahun DESC, id DESC')
    data_produksi = cursor.fetchall()

    return render_template(
        'data.html',
        data=data_produksi,
        ringkasan=ringkasan,
        sukses=sukses,
        error=error,
    )


# ==================== UPLOAD DATA PRODUKSI DARI EXCEL ====================

@app.route('/upload_excel', methods=['POST'])
@admin_required
def upload_excel():
    # File Excel wajib memiliki kolom: tahun, komoditas, produksi.
    # Kolom satuan dan keterangan bersifat opsional.

    if 'file_excel' not in request.files:
        return redirect(url_for('data', error='File Excel belum dipilih.'))

    file_excel = request.files['file_excel']

    if not file_excel or file_excel.filename == '':
        return redirect(url_for(
            'data',
            error='Silakan pilih file Excel terlebih dahulu.'
        ))

    if not file_excel_diizinkan(file_excel.filename):
        return redirect(url_for(
            'data',
            error='Format file tidak didukung. Gunakan file Excel .xlsx.'
        ))

    try:
        df_excel = pd.read_excel(file_excel, engine='openpyxl')

        # Normalisasi nama kolom: Tahun/TAHUN/tahun menjadi "tahun".
        df_excel.columns = [
            str(kolom).strip().lower()
            for kolom in df_excel.columns
        ]

        kolom_wajib = {'tahun', 'komoditas', 'produksi'}
        kolom_tidak_ada = kolom_wajib - set(df_excel.columns)

        if kolom_tidak_ada:
            return redirect(url_for(
                'data',
                error=(
                    'Kolom Excel belum sesuai. Kolom wajib adalah: '
                    'tahun, komoditas, produksi.'
                )
            ))

        if df_excel.empty:
            return redirect(url_for(
                'data',
                error='File Excel tidak memiliki data.'
            ))

        db = koneksi()
        cursor = db.cursor()
        jumlah_berhasil = 0
        jumlah_dilewati = 0

        for _, row in df_excel.iterrows():
            if row[['tahun', 'komoditas', 'produksi']].isna().all():
                continue

            komoditas = str(row.get('komoditas', '')).strip()

            if not komoditas or komoditas.lower() == 'nan':
                jumlah_dilewati += 1
                continue

            try:
                tahun = int(float(row.get('tahun')))
                produksi = float(row.get('produksi'))
            except (TypeError, ValueError):
                jumlah_dilewati += 1
                continue

            if tahun < 1900 or tahun > 2200 or np.isnan(produksi):
                jumlah_dilewati += 1
                continue

            satuan = row.get('satuan', 'Ton')
            keterangan = row.get('keterangan', '-')

            satuan = (
                'Ton'
                if pd.isna(satuan) or str(satuan).strip() == ''
                else str(satuan).strip()
            )

            keterangan = (
                '-'
                if pd.isna(keterangan) or str(keterangan).strip() == ''
                else str(keterangan).strip()
            )

            # Cegah duplikasi komoditas dan tahun yang sama.
            cursor.execute(
                '''
                SELECT id
                FROM produksi
                WHERE LOWER(TRIM(komoditas)) = LOWER(TRIM(%s))
                  AND tahun = %s
                LIMIT 1
                ''',
                (komoditas, tahun)
            )

            if cursor.fetchone():
                jumlah_dilewati += 1
                continue

            tanggal_input = datetime.now().strftime('%d %b %Y %H:%M')

            try:
                cursor.execute(
                    '''
                    INSERT INTO produksi
                    (komoditas, tahun, produksi, satuan, keterangan, tanggal_input)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ''',
                    (
                        komoditas,
                        tahun,
                        produksi,
                        satuan,
                        keterangan,
                        tanggal_input,
                    )
                )
                db.commit()
            except Exception:
                # Fallback bila tabel hanya mempunyai 3 kolom dasar.
                db.rollback()
                cursor = db.cursor()
                cursor.execute(
                    '''
                    INSERT INTO produksi (komoditas, tahun, produksi)
                    VALUES (%s, %s, %s)
                    ''',
                    (komoditas, tahun, produksi)
                )
                db.commit()

            jumlah_berhasil += 1

        if jumlah_berhasil == 0:
            return redirect(url_for(
                'data',
                error=(
                    'Tidak ada data baru yang berhasil diimport. '
                    f'{jumlah_dilewati} baris dilewati karena tidak valid '
                    'atau sudah tersedia di database.'
                )
            ))

        pesan = f'{jumlah_berhasil} data berhasil diimport dari Excel.'

        if jumlah_dilewati > 0:
            pesan += (
                f' {jumlah_dilewati} baris dilewati karena tidak valid '
                'atau sudah tersedia.'
            )

        return redirect(url_for('data', sukses=pesan))

    except Exception as e:
        return redirect(url_for(
            'data',
            error=f'Gagal membaca file Excel: {str(e)}'
        ))


# ROUTE EDIT DATA
@app.route('/edit_data/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_data(id):
    db = koneksi()
    cursor = db.cursor()

    if request.method == 'POST':
        komoditas = request.form.get('komoditas')
        tahun = request.form.get('tahun')
        produksi = request.form.get('produksi')
        satuan = request.form.get('satuan', 'Ton')
        keterangan = request.form.get('keterangan', '-')

        # Cegah hasil edit menjadi duplikat dengan baris lain.
        cursor.execute(
            '''
                SELECT id
                FROM produksi
                WHERE LOWER(TRIM(komoditas)) = LOWER(TRIM(%s))
                  AND tahun = %s
                  AND id != %s
                LIMIT 1
            ''',
            (komoditas, tahun, id),
        )

        if cursor.fetchone():
            return redirect(url_for(
                'data',
                error=(
                    f'Data {komoditas} tahun {tahun} sudah tersedia. '
                    'Perubahan dibatalkan agar tidak terjadi data duplikat.'
                ),
            ))

        try:
            query = """
                UPDATE produksi
                SET komoditas = %s, tahun = %s, produksi = %s,
                    satuan = %s, keterangan = %s
                WHERE id = %s
            """
            cursor.execute(
                query,
                (komoditas, tahun, produksi, satuan, keterangan, id),
            )
            db.commit()
        except Exception:
            db.rollback()
            query_basic = """
                UPDATE produksi
                SET komoditas = %s, tahun = %s, produksi = %s
                WHERE id = %s
            """
            cursor.execute(query_basic, (komoditas, tahun, produksi, id))
            db.commit()

        return redirect(url_for(
            'data',
            sukses=f'Data {komoditas} tahun {tahun} berhasil diperbarui.',
        ))

    cursor.execute("SELECT * FROM produksi WHERE id = %s", (id,))
    row = cursor.fetchone()

    cursor.execute("SELECT DISTINCT komoditas FROM produksi")
    data_komoditas = cursor.fetchall()
    daftar_komoditas = [item['komoditas'] if isinstance(item, dict) else item[0] for item in data_komoditas]

    return render_template('edit_data.html', row=row, daftar_komoditas=daftar_komoditas)


# ROUTE HAPUS DATA
@app.route('/hapus_data/<int:id>')
@admin_required
def hapus_data(id):
    db = koneksi()
    cursor = db.cursor()
    cursor.execute('DELETE FROM produksi WHERE id = %s', (id,))
    db.commit()
    return redirect(url_for('data'))


# ==================== FITUR PREDIKSI PROPHET ====================


@app.route('/prediksi', methods=['GET', 'POST'])
@login_required
def prediksi():
    from prophet import Prophet
    db = koneksi()
    cursor = db.cursor()

    cursor.execute('SELECT DISTINCT komoditas FROM produksi')
    data_komoditas = cursor.fetchall()

    # Format daftar komoditas agar fleksibel (baik berupa dict/tuple)
    daftar_komoditas = []
    for item in data_komoditas:
        val = item['komoditas'] if isinstance(item, dict) else item[0]
        daftar_komoditas.append(val)

    hasil_prediksi = None
    chart_data = None
    evaluasi = None
    perbandingan_data = None
    komoditas_pilihan = (
        daftar_komoditas[0] if daftar_komoditas else 'Kelapa Sawit'
    )
    tahun_prediksi = 5

    if request.method == 'POST':
        komoditas_pilihan = request.form.get('komoditas')
        tahun_prediksi = int(request.form.get('tahun_prediksi', 5))

        cursor.execute(
            'SELECT tahun, produksi FROM produksi WHERE komoditas = %s ORDER BY'
            ' tahun ASC',
            (komoditas_pilihan,),
        )
        data_raw = cursor.fetchall()

        if len(data_raw) < 2:
            return render_template(
                'prediksi.html',
                komoditas_list=daftar_komoditas,
                error=(
                    'Data historis komoditas ini terlalu sedikit untuk melakukan'
                    ' prediksi.'
                ),
            )

        # Konversi data ke DataFrame
        df = pd.DataFrame(data_raw)
        if not isinstance(data_raw[0], dict):
            df.columns = ['tahun', 'produksi']

        df['ds'] = pd.to_datetime(df['tahun'].astype(str) + '-01-01')
        df['y'] = df['produksi'].astype(float)

        # Model Prophet
        model = Prophet(yearly_seasonality=True, interval_width=0.95)
        model.fit(df[['ds', 'y']])

        future = model.make_future_dataframe(periods=tahun_prediksi, freq='YS')
        forecast = model.predict(future)

        # Evaluasi Model (In-Sample)
        y_true = df['y'].values
        y_pred = forecast['yhat'].iloc[: len(df)].values

        # Tabel Perbandingan Data Aktual dan Hasil Prediksi Prophet
        perbandingan_data = []
        for i in range(len(df)):
            tahun = int(df['tahun'].iloc[i])
            aktual = float(y_true[i])
            prediksi_in_sample = float(y_pred[i])
            error_absolut = abs(aktual - prediksi_in_sample)

            perbandingan_data.append({
                'tahun': tahun,
                'aktual': round(aktual, 2),
                'prediksi': round(prediksi_in_sample, 2),
                'error_absolut': round(error_absolut, 2),
            })

        mae = mean_absolute_error(y_true, y_pred)
        mape = mean_absolute_percentage_error(y_true, y_pred) * 100
        rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))

        ss_res = np.sum((y_true - y_pred) ** 2)
        ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        forecast['tahun'] = forecast['ds'].dt.year

        # Filter khusus data masa depan untuk tabel
        data_masa_depan = forecast.tail(tahun_prediksi)
        hasil_prediksi = data_masa_depan[
            ['tahun', 'yhat', 'yhat_lower', 'yhat_upper']
        ].to_dict(orient='records')

        # Data Gabungan Lengkap untuk Grafik Chart.js
        years_all = forecast['tahun'].tolist()
        n_aktual = len(df)

        actual_values = df['y'].tolist() + [None] * tahun_prediksi

        # Sambungkan garis prediksi dari titik terakhir data aktual
        pred_values = [None] * (n_aktual - 1) + forecast['yhat'].iloc[
            n_aktual - 1 :
        ].round(2).tolist()
        lower_values = [None] * (n_aktual - 1) + forecast['yhat_lower'].iloc[
            n_aktual - 1 :
        ].round(2).tolist()
        upper_values = [None] * (n_aktual - 1) + forecast['yhat_upper'].iloc[
            n_aktual - 1 :
        ].round(2).tolist()

        chart_data = {
            'labels': years_all,
            'actual': actual_values,
            'pred': pred_values,
            'lower': lower_values,
            'upper': upper_values,
        }

        # Hitung rata-rata pertumbuhan per tahun
        prod_awal = data_masa_depan['yhat'].iloc[0]
        prod_akhir = data_masa_depan['yhat'].iloc[-1]
        pertumbuhan_total = (
            ((prod_akhir - prod_awal) / prod_awal) * 100
            if prod_awal != 0
            else 0
        )
        rata_pertumbuhan = pertumbuhan_total / (tahun_prediksi - 1 or 1)

        evaluasi = {
            'mae': round(mae, 2),
            'mape': round(mape, 2),
            'rmse': round(rmse, 2),
            'r2': round(r2, 2),
            'r2_pct': round(r2 * 100, 0),
            'produksi_terakhir': df['y'].iloc[-1],
            'tahun_terakhir': df['tahun'].iloc[-1],
            'prediksi_akhir': data_masa_depan['yhat'].iloc[-1],
            'tahun_akhir_prediksi': data_masa_depan['tahun'].iloc[-1],
            'tahun_awal_prediksi': data_masa_depan['tahun'].iloc[0],  # Perbaikan: .iloc[0]
            'selisih': data_masa_depan['yhat'].iloc[-1] - df['y'].iloc[-1],
            'rata_rata_pertumbuhan': round(rata_pertumbuhan, 2),
        }

    return render_template(
        'prediksi.html',
        komoditas_list=daftar_komoditas,
        komoditas_terpilih=komoditas_pilihan,
        tahun_terpilih=tahun_prediksi,
        hasil=hasil_prediksi,
        chart_data=chart_data,
        evaluasi=evaluasi,
        perbandingan_data=perbandingan_data,
    )



# ==================== KELOLA PENGGUNA (KHUSUS ADMIN) ====================

@app.route('/pengguna', methods=['GET', 'POST'])
@admin_required
def kelola_pengguna():
    db = koneksi()
    cursor = db.cursor()

    error = request.args.get('error')
    sukses = request.args.get('sukses')

    if request.method == 'POST':
        nama_lengkap = request.form.get('nama_lengkap', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'user').strip().lower()

        if not nama_lengkap or not username or not password:
            return redirect(url_for(
                'kelola_pengguna',
                error='Nama lengkap, username, dan password wajib diisi.'
            ))

        if role not in ['admin', 'user']:
            role = 'user'

        cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
        akun_lama = cursor.fetchone()

        if akun_lama:
            return redirect(url_for(
                'kelola_pengguna',
                error='Username sudah digunakan. Silakan gunakan username lain.'
            ))

        cursor.execute(
            'INSERT INTO users (username, password, nama_lengkap, role) VALUES (%s, %s, %s, %s)',
            (username, password, nama_lengkap, role)
        )
        db.commit()

        return redirect(url_for(
            'kelola_pengguna',
            sukses='Pengguna berhasil didaftarkan.'
        ))

    cursor.execute(
        'SELECT id, username, nama_lengkap, role FROM users ORDER BY id ASC'
    )
    daftar_pengguna = cursor.fetchall()

    return render_template(
        'kelola_pengguna.html',
        pengguna=daftar_pengguna,
        error=error,
        sukses=sukses,
    )


@app.route('/edit_pengguna/<int:id>', methods=['POST'])
@admin_required
def edit_pengguna(id):
    db = koneksi()
    cursor = db.cursor()

    cursor.execute('SELECT id, role FROM users WHERE id = %s', (id,))
    akun = cursor.fetchone()

    if not akun:
        return redirect(url_for(
            'kelola_pengguna',
            error='Akun pengguna tidak ditemukan.'
        ))

    nama_lengkap = request.form.get('nama_lengkap', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'user').strip().lower()

    if not nama_lengkap or not username:
        return redirect(url_for(
            'kelola_pengguna',
            error='Nama lengkap dan username wajib diisi.'
        ))

    if role not in ['admin', 'user']:
        return redirect(url_for(
            'kelola_pengguna',
            error='Role pengguna tidak valid.'
        ))

    cursor.execute(
        'SELECT id FROM users WHERE username = %s AND id != %s',
        (username, id)
    )
    username_dipakai = cursor.fetchone()

    if username_dipakai:
        return redirect(url_for(
            'kelola_pengguna',
            error='Username sudah digunakan oleh akun lain.'
        ))

    if password:
        cursor.execute(
            '''UPDATE users
               SET username = %s, password = %s, nama_lengkap = %s, role = %s
               WHERE id = %s''',
            (username, password, nama_lengkap, role, id)
        )
    else:
        cursor.execute(
            '''UPDATE users
               SET username = %s, nama_lengkap = %s, role = %s
               WHERE id = %s''',
            (username, nama_lengkap, role, id)
        )

    db.commit()

    return redirect(url_for(
        'kelola_pengguna',
        sukses='Data pengguna berhasil diperbarui.'
    ))


@app.route('/hapus_pengguna/<int:id>')
@admin_required
def hapus_pengguna(id):
    db = koneksi()
    cursor = db.cursor()

    cursor.execute('SELECT id, role FROM users WHERE id = %s', (id,))
    akun = cursor.fetchone()

    if not akun:
        return redirect(url_for(
            'kelola_pengguna',
            error='Akun pengguna tidak ditemukan.'
        ))

    if id == session.get('user_id'):
        return redirect(url_for(
            'kelola_pengguna',
            error='Akun yang sedang digunakan tidak dapat dihapus.'
        ))

    cursor.execute('DELETE FROM users WHERE id = %s', (id,))
    db.commit()

    return redirect(url_for(
        'kelola_pengguna',
        sukses='Pengguna berhasil dihapus.'
    ))


# ==================== HALAMAN EVALUASI ====================

@app.route('/evaluasi', methods=['GET', 'POST'])
@login_required
def evaluasi():
    from prophet import Prophet
    db = koneksi()
    cursor = db.cursor()

    # Ambil daftar komoditas
    cursor.execute('SELECT DISTINCT komoditas FROM produksi ORDER BY komoditas ASC')
    data_komoditas = cursor.fetchall()

    daftar_komoditas = []
    for item in data_komoditas:
        val = item['komoditas'] if isinstance(item, dict) else item[0]
        daftar_komoditas.append(val)

    komoditas_pilihan = (
        daftar_komoditas[0] if daftar_komoditas else None
    )

    hasil_evaluasi = None
    perbandingan_data = None
    error = None

    if request.method == 'POST':
        komoditas_pilihan = request.form.get('komoditas')

        cursor.execute(
            '''
            SELECT tahun, produksi
            FROM produksi
            WHERE komoditas = %s
            ORDER BY tahun ASC
            ''',
            (komoditas_pilihan,)
        )
        data_raw = cursor.fetchall()

        if len(data_raw) < 2:
            error = (
                'Data historis komoditas ini terlalu sedikit '
                'untuk melakukan evaluasi.'
            )
        else:
            # Ubah data menjadi DataFrame
            df = pd.DataFrame(data_raw)

            if not isinstance(data_raw[0], dict):
                df.columns = ['tahun', 'produksi']

            df['ds'] = pd.to_datetime(
                df['tahun'].astype(str) + '-01-01'
            )
            df['y'] = df['produksi'].astype(float)

            # Model Prophet
            model = Prophet(
                yearly_seasonality=True,
                interval_width=0.95
            )
            model.fit(df[['ds', 'y']])

            # Prediksi pada data historis untuk evaluasi
            forecast = model.predict(df[['ds']])

            y_true = df['y'].values
            y_pred = forecast['yhat'].values

            # Hitung metrik evaluasi
            mae = mean_absolute_error(y_true, y_pred)
            mape = mean_absolute_percentage_error(
                y_true,
                y_pred
            ) * 100
            rmse = np.sqrt(
                np.mean((y_true - y_pred) ** 2)
            )

            ss_res = np.sum((y_true - y_pred) ** 2)
            ss_tot = np.sum(
                (y_true - np.mean(y_true)) ** 2
            )
            r2 = (
                1 - (ss_res / ss_tot)
                if ss_tot != 0
                else 0
            )

            hasil_evaluasi = {
                'mae': round(mae, 2),
                'mape': round(mape, 2),
                'rmse': round(rmse, 2),
                'r2': round(r2, 2),
                'r2_pct': round(r2 * 100, 2)
            }

            # Tabel perbandingan aktual dan prediksi
            perbandingan_data = []

            for i in range(len(df)):
                aktual = float(y_true[i])
                prediksi_prophet = float(y_pred[i])
                error_absolut = abs(
                    aktual - prediksi_prophet
                )

                perbandingan_data.append({
                    'tahun': int(df['tahun'].iloc[i]),
                    'aktual': round(aktual, 2),
                    'prediksi': round(
                        prediksi_prophet,
                        2
                    ),
                    'error_absolut': round(
                        error_absolut,
                        2
                    )
                })

    return render_template(
        'evaluasi.html',
        komoditas_list=daftar_komoditas,
        komoditas_terpilih=komoditas_pilihan,
        evaluasi=hasil_evaluasi,
        perbandingan_data=perbandingan_data,
        error=error
    )


@app.route('/tentang')
@login_required
def tentang():
    return render_template('tentang.html')


if __name__ == '__main__':
    app.run(debug=True)
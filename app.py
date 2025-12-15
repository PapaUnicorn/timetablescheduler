import streamlit as st
import pandas as pd
import datetime
import io
import re

# ==========================================
# 0. KONFIGURASI HALAMAN
# ==========================================
st.set_page_config(page_title="Timetable Scheduler by EDUNEXUS", layout="wide")

# --- HEADER ---
st.title("Timetable Scheduler by EDUNEXUS INDONESIA")
st.markdown("by Glenn Bolang | [Support my work via Saweria](https://saweria.co/edunexusindonesia)")
st.markdown("---") 

# --- STATE MANAGEMENT ---
if 'data_classes' not in st.session_state: st.session_state['data_classes'] = []
if 'data_subjects' not in st.session_state: 
    st.session_state['data_subjects'] = pd.DataFrame(columns=[
        'Class', 'Subject Name', 'Subject Code', 
        'Teacher Name', 'Teacher Initials', 'Periods/Week'
    ])
if 'time_structure' not in st.session_state: st.session_state['time_structure'] = pd.DataFrame()
if 'manual_schedule' not in st.session_state: st.session_state['manual_schedule'] = {} 
if 'selected_day_view' not in st.session_state: st.session_state['selected_day_view'] = 'Senin'

# --- FUNGSI BANTUAN: GENERATE TEMPLATE KHUSUS ---
def generate_custom_template(level):
    if level == 'SMP':
        kelas_list = ['Kelas 7', 'Kelas 8', 'Kelas 9']
    else: # SMA
        kelas_list = ['Kelas X', 'Kelas XI', 'Kelas XII']
    
    data = []
    for k in kelas_list:
        for _ in range(20):
            data.append([k, "", "", "", 2]) 
            
    df = pd.DataFrame(data, columns=['Kelas', 'Mata Pelajaran', 'Inisial Mapel', 'Nama Lengkap Guru', 'Jam (JP)'])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Data_Master')
    return output.getvalue()

# --- FUNGSI BANTUAN: AUTO GENERATE INISIAL GURU ---
def create_initials(full_name):
    if not isinstance(full_name, str) or not full_name.strip(): return "???"
    parts = full_name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][:2]).upper()
    elif len(parts) == 1:
        return parts[0][:3].upper()
    else:
        return "???"

# --- FUNGSI BANTUAN: DETEKSI KONFLIK ---
def get_conflict_coordinates(df):
    conflicts = set()
    SAFE_LIST = ["UPACARA", "CHAPEL", "ISTIRAHAT", "BREAK", "RECESS", "NO CLASS", "P5", "FLAG CEREMONY", "DEVOTION", "SCOUT", "EXERCISE", "PRAMUKA"]

    if not isinstance(df, pd.DataFrame): return conflicts

    for idx, row in df.iterrows():
        idx_str = str(idx).upper()
        if "ISTIRAHAT" in idx_str or "BREAK" in idx_str or "RECESS" in idx_str: continue
        if "RECESS" in str(row.values).upper(): continue

        teacher_map = {} 
        for col in df.columns:
            if col == "Waktu": continue
            val = row[col]
            if isinstance(val, str) and val.strip():
                if any(safe in val.upper() for safe in SAFE_LIST): continue
                match = re.search(r'\((.*?)\)', val)
                if match:
                    code = match.group(1)
                    if code not in teacher_map: teacher_map[code] = []
                    teacher_map[code].append(col)
        
        for code, cols in teacher_map.items():
            if len(cols) > 1:
                for c in cols: conflicts.add((idx, c))
    return conflicts

# --- FUNGSI BANTUAN: CUSTOM STYLING (MERAH & KREM) ---
def apply_custom_styles(df):
    # 1. Buat DataFrame kosong untuk menampung style CSS
    df_styler = pd.DataFrame('', index=df.index, columns=df.columns)
    
    # 2. Loop untuk mencari sel KOSONG -> Warna KREM
    for r in df.index:
        for c in df.columns:
            if c == "Waktu": continue # Skip kolom waktu
            val = df.at[r, c]
            
            # Cek apakah kosong (NaN, None, atau string kosong)
            if pd.isna(val) or str(val).strip() == "":
                # Cream Background, Black Font
                df_styler.at[r, c] = 'background-color: #FFFDD0; color: black;'

    # 3. Loop untuk mencari BENTROK -> Warna MERAH (Prioritas Tinggi, akan menimpa krem jika terjadi aneh)
    coords = get_conflict_coordinates(df)
    for r, c in coords:
        # Red Background, White Font, Bold
        df_styler.at[r, c] = 'background-color: #dc3545; color: white; font-weight: bold;'
        
    return df_styler

# --- FUNGSI BANTUAN: HITUNG BEBAN GURU ---
def calculate_teacher_load():
    if st.session_state['data_subjects'].empty: return pd.DataFrame()
    
    df_target = st.session_state['data_subjects'].groupby('Teacher Initials').agg({
        'Periods/Week': 'sum',
        'Teacher Name': 'first'
    }).reset_index()
    df_target.rename(columns={'Periods/Week': 'Target JP'}, inplace=True)
    
    actual_counts = {}
    for day in st.session_state['manual_schedule']:
        df_day = st.session_state['manual_schedule'][day]
        for col in df_day.columns:
            if col == "Waktu": continue
            for cell in df_day[col]:
                if isinstance(cell, str):
                    match = re.search(r'\((.*?)\)', cell)
                    if match:
                        code = match.group(1)
                        if code not in actual_counts: actual_counts[code] = 0
                        actual_counts[code] += 1
                        
    df_target['Terplot'] = df_target['Teacher Initials'].map(actual_counts).fillna(0).astype(int)
    df_target['Sisa'] = df_target['Target JP'] - df_target['Terplot']
    
    def get_status(row):
        if row['Sisa'] == 0: return "✅ LUNAS"
        elif row['Sisa'] > 0: return f"⚠️ Kurang {row['Sisa']}"
        else: return f"🔴 Lebih {abs(row['Sisa'])}"
        
    df_target['Status'] = df_target.apply(get_status, axis=1)
    return df_target[['Teacher Initials', 'Teacher Name', 'Target JP', 'Terplot', 'Status']]

# ==========================================
# SIDEBAR NAVIGATION
# ==========================================
with st.sidebar:
    st.header("Menu Navigasi")
    menu = st.radio("Pilih Langkah:", [
        "1. Panduan & Upload Data", 
        "2. Setting Waktu & Break", 
        "3. Input Jadwal (Visual)"
    ])

# ==========================================
# MENU 1: PANDUAN & UPLOAD
# ==========================================
if menu == "1. Panduan & Upload Data":
    st.header("📖 Panduan Pemakaian")
    
    with st.expander("Klik untuk membaca Panduan Lengkap", expanded=True):
        st.markdown("""
        **Selamat datang di Timetable Scheduler! Ikuti 3 langkah mudah berikut:**
        
        1.  **Persiapan Data (Menu 1):**
            * Unduh **Template Excel** (SMP atau SMA) di bawah.
            * Isi kolom **Kelas, Mata Pelajaran, dan Nama Guru**.
            * Kolom *Inisial Mapel* boleh dikosongkan (opsional).
            * **Upload** file yang sudah diisi ke sistem ini.
        
        2.  **Pengaturan Waktu (Menu 2):**
            * Pindah ke Menu 2 di Sidebar sebelah kiri.
            * Tentukan jam masuk, durasi per jam pelajaran (JP), dan total JP per hari.
            * Atur waktu **Istirahat (Break)**.
            * Klik tombol **Simpan Struktur Waktu**.
        
        3.  **Penyusunan Jadwal (Menu 3):**
            * Pindah ke Menu 3 di Sidebar.
            * Pilih Hari menggunakan tombol warna-warni.
            * Gunakan dropdown untuk memasukkan mapel ke kelas.
            * **Layar Pantau (Atas)** akan berwarna:
                * **MERAH**: Jika guru bentrok (mengajar ganda).
                * **KREM**: Jika sel masih kosong (belum diisi).
            * Unduh hasil akhir via tombol **Export Excel**.
        """)

    st.divider()
    st.subheader("📂 Langkah 1: Upload Data")

    # --- BAGIAN DOWNLOAD TEMPLATE ---
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Unduh Template SMP", generate_custom_template('SMP'), "Template_SMP.xlsx")
    with c2:
        st.download_button("⬇️ Unduh Template SMA", generate_custom_template('SMA'), "Template_SMA.xlsx")

    # --- BAGIAN UPLOAD ---
    uploaded_file = st.file_uploader("Upload File Template yang Sudah Diisi", type=['xlsx'])
    
    if uploaded_file:
        try:
            df_up = pd.read_excel(uploaded_file)
            expected_cols = ['Kelas', 'Mata Pelajaran', 'Inisial Mapel', 'Nama Lengkap Guru', 'Jam (JP)']
            
            if all(col in df_up.columns for col in expected_cols):
                df_up = df_up.dropna(subset=['Kelas', 'Mata Pelajaran', 'Nama Lengkap Guru'])
                df_up['Inisial Guru'] = df_up['Nama Lengkap Guru'].apply(create_initials)
                
                rename_map = {'Kelas': 'Class', 'Mata Pelajaran': 'Subject Name', 'Inisial Mapel': 'Subject Code', 
                              'Nama Lengkap Guru': 'Teacher Name', 'Inisial Guru': 'Teacher Initials', 'Jam (JP)': 'Periods/Week'}
                df_up = df_up.rename(columns=rename_map)
                
                df_up['Class'] = df_up['Class'].astype(str)
                df_up['Periods/Week'] = df_up['Periods/Week'].astype(int)
                
                st.session_state['data_subjects'] = df_up
                st.session_state['data_classes'] = sorted(df_up['Class'].unique().tolist())
                
                st.success(f"✅ Data Berhasil Dimuat! ({len(df_up)} Baris)")
                st.info("Inisial guru berhasil digenerate otomatis.")
                st.dataframe(df_up.head(3))
            else:
                st.error("Format kolom salah! Gunakan template yang disediakan.")
        except Exception as e:
            st.error(f"Error: {e}")

# ==========================================
# MENU 2: SETTING WAKTU
# ==========================================
elif menu == "2. Setting Waktu & Break":
    st.header("⏰ Langkah 2: Setting Waktu")
    
    c1, c2, c3 = st.columns(3)
    start_time = c1.time_input("Jam Masuk", datetime.time(7,0))
    jp_dur = c2.number_input("Durasi 1 JP (Menit)", 35)
    total_jp = c3.number_input("Total JP Hari Ini", min_value=1, value=8)
    
    st.subheader("☕ Konfigurasi Istirahat")
    num_breaks = st.number_input("Jumlah Break", 0, 4, 2)
    break_configs = []
    if num_breaks > 0:
        for i in range(num_breaks):
            bc1, bc2 = st.columns(2)
            pos = bc1.number_input(f"Break {i+1} SETELAH Jam ke-", 1, total_jp, (4 if i==0 else 8), key=f"bpos{i}")
            dur = bc2.number_input(f"Durasi Break {i+1} (Menit)", 5, 60, (15 if i==0 else 30), key=f"bdur{i}")
            break_configs.append({'after': pos, 'duration': dur})
    
    if st.button("💾 Simpan Struktur Waktu", use_container_width=True):
        schedule = []
        curr = datetime.datetime.combine(datetime.date.today(), start_time)
        break_configs.sort(key=lambda x: x['after'])
        
        break_counter = 1
        for i in range(1, total_jp+1):
            end = curr + datetime.timedelta(minutes=jp_dur)
            schedule.append({'Period': str(i), 'Type': 'Class', 'Waktu': f"{curr.strftime('%H:%M')} - {end.strftime('%H:%M')}"})
            curr = end
            
            found = next((b for b in break_configs if b['after'] == i), None)
            if found:
                end_br = curr + datetime.timedelta(minutes=found['duration'])
                schedule.append({'Period': f'BREAK {break_counter}', 'Type': 'BREAK', 'Waktu': f"{curr.strftime('%H:%M')} - {end_br.strftime('%H:%M')}"})
                curr = end_br
                break_counter += 1
                
        st.session_state['time_structure'] = pd.DataFrame(schedule)
        st.session_state['manual_schedule'] = {} 
        st.success("✅ Waktu tersimpan! Grid jadwal telah di-reset sesuai waktu baru.")

    if not st.session_state['time_structure'].empty:
        with st.expander("Lihat Struktur Waktu"):
            st.dataframe(st.session_state['time_structure'])

# ==========================================
# MENU 3: INPUT JADWAL
# ==========================================
elif menu == "3. Input Jadwal (Visual)":
    st.header("🗓️ Langkah 3: Penyusunan Jadwal")

    # Validasi Ketat
    if st.session_state['data_subjects'].empty:
        st.error("⛔ Data Sekolah belum diupload. Silakan kembali ke Menu 1 untuk upload data.")
        st.stop()
    if st.session_state['time_structure'].empty:
        st.error("⛔ Setting Waktu belum dikonfigurasi. Silakan kembali ke Menu 2 untuk simpan waktu.")
        st.stop()

    # --- DAY SELECTOR ---
    st.write("Pilih Hari:")
    day_cols = st.columns(5)
    days_data = [("Senin", "🔴"), ("Selasa", "🟠"), ("Rabu", "🟡"), ("Kamis", "🟢"), ("Jumat", "🔵")]
    
    for i, (day_name, emoji) in enumerate(days_data):
        btn_type = "primary" if st.session_state['selected_day_view'] == day_name else "secondary"
        if day_cols[i].button(f"{emoji} {day_name}", key=f"btn_day_{i}", type=btn_type, use_container_width=True):
            st.session_state['selected_day_view'] = day_name
            st.rerun()

    day = st.session_state['selected_day_view']
    
    classes = st.session_state['data_classes']
    time_df = st.session_state['time_structure']
    periods = time_df['Period'].tolist()
    
    if day not in st.session_state['manual_schedule']:
        cols = ['Waktu'] + classes
        df_init = pd.DataFrame(index=periods, columns=cols)
        time_map = dict(zip(time_df['Period'], time_df['Waktu']))
        df_init['Waktu'] = df_init.index.map(time_map)
        
        for idx in periods:
            if "BREAK" in str(idx).upper() or "ISTIRAHAT" in str(idx).upper():
                df_init.loc[idx, classes] = "RECESS"
        
        st.session_state['manual_schedule'][day] = df_init
    
    current_df = st.session_state['manual_schedule'][day].copy()

    if not isinstance(current_df, pd.DataFrame):
         st.warning("Data korup, mereset...")
         del st.session_state['manual_schedule'][day]
         st.rerun()

    st.subheader(f"Editor Jadwal: {day}")
    
    # --- LAYAR PANTAU (READ ONLY) ---
    st.info("💡 LAYAR PANTAU: Merah = Bentrok | Krem = Sel Masih Kosong")
    
    # Terapkan styling: Merah untuk bentrok, Krem untuk kosong
    st.dataframe(
        current_df.style.apply(lambda _: apply_custom_styles(current_df), axis=None),
        use_container_width=True,
        height=400
    )
    
    st.caption("👆 Layar Pantau di atas hanya untuk melihat status. Silakan edit jadwal di tabel bawah 👇")

    # --- EDITOR JADWAL ---
    col_config = {}
    col_config["Waktu"] = st.column_config.TextColumn("Pukul", width="small", disabled=True)

    for cls in classes:
        subset = st.session_state['data_subjects'][st.session_state['data_subjects']['Class'] == cls]
        opts = [None, "UPACARA", "CHAPEL", "RECESS", "PRAMUKA", "OLAH RAGA", "DEVOTION"]
        if not subset.empty:
            for _, row in subset.iterrows():
                opts.append(f"{row['Subject Code']} ({row['Teacher Initials']})")
        
        # Lebar kolom 'small' agar muat banyak
        col_config[cls] = st.column_config.SelectboxColumn(
            label=cls, 
            options=opts, 
            width="small", 
            required=False
        )
    
    # Deteksi konflik untuk pesan warning (tambahan info)
    conflicts = get_conflict_coordinates(current_df)
    if conflicts:
        st.toast(f"⚠️ ADA {len(conflicts)} BENTROK JADWAL!", icon="🚨")

    edited_df = st.data_editor(
        current_df,
        column_config=col_config,
        use_container_width=True,
        height=500,
        key=f"editor_{day}"
    )

    if not edited_df.equals(current_df):
        st.session_state['manual_schedule'][day] = edited_df
        st.rerun() 
    
    st.divider()

    st.subheader("📊 Monitor Beban Mengajar (Real-Time)")
    st.info("Status otomatis dihitung saat Anda menginput jadwal di atas.")
    
    df_load = calculate_teacher_load()
    
    if not df_load.empty:
        def highlight_status(val):
            color = ''
            if 'LUNAS' in val: color = 'background-color: #d4edda; color: #155724' 
            elif 'Kurang' in val: color = 'background-color: #fff3cd; color: #856404' 
            elif 'Lebih' in val: color = 'background-color: #f8d7da; color: #721c24' 
            return color

        st.dataframe(
            df_load.style.applymap(highlight_status, subset=['Status']),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.text("Belum ada data guru.")

    st.divider()
    
    if st.button("💾 Export Semua Jadwal ke Excel", type="primary"):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            for d in ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"]:
                if d in st.session_state['manual_schedule']:
                    st.session_state['manual_schedule'][d].to_excel(writer, sheet_name=d)
            if not df_load.empty:
                df_load.to_excel(writer, sheet_name="Analisis Beban", index=False)
                
        st.download_button("Klik untuk Download File", out.getvalue(), "Jadwal_Siap_Cetak.xlsx")
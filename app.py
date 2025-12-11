import streamlit as st
import pandas as pd
import datetime
import io
import re

# ==========================================
# 0. KONFIGURASI HALAMAN
# ==========================================
st.set_page_config(page_title="Edunexus Scheduler", layout="wide")
st.title("🗓️ Edunexus Scheduler Pro (Split Columns)")

# --- STATE MANAGEMENT ---
if 'data_classes' not in st.session_state: st.session_state['data_classes'] = []
if 'data_subjects' not in st.session_state: 
    st.session_state['data_subjects'] = pd.DataFrame(columns=[
        'Class', 'Subject Name', 'Subject Code', 
        'Teacher Name', 'Teacher Initials', 'Periods/Week'
    ])
if 'time_structure' not in st.session_state: st.session_state['time_structure'] = pd.DataFrame()
if 'manual_schedule' not in st.session_state: st.session_state['manual_schedule'] = {} 

# --- FUNGSI BANTUAN: DOWNLOAD TEMPLATE ---
def generate_excel_template():
    df_template = pd.DataFrame(columns=['Kelas', 'Mata Pelajaran', 'Jam', 'Guru', 'Initial', 'Init Subj'])
    df_template.loc[0] = ["Kelas 1", "Matematika", 4, "Budi Santoso", "BDS", "MAT"]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_template.to_excel(writer, index=False, sheet_name='Data_Master')
    return output.getvalue()

# --- FUNGSI BANTUAN: VISUAL HIGHLIGHTER ---
def get_conflict_coordinates(df):
    conflicts = set()
    SAFE_LIST = ["UPACARA", "CHAPEL", "ISTIRAHAT", "BREAK", "RECESS", "NO CLASS", "P5", "FLAG CEREMONY", "DEVOTION", "SCOUT", "EXERCISE"]

    if not isinstance(df, pd.DataFrame): return conflicts

    for idx, row in df.iterrows():
        # Skip baris istirahat
        idx_str = str(idx).upper()
        row_str = str(row.values).upper()
        if "ISTIRAHAT" in idx_str or "BREAK" in idx_str or "RECESS" in idx_str:
            continue
        # Jika satu baris isinya RECESS semua, skip
        if "RECESS" in row_str:
            continue

        teacher_map = {} 
        
        for col in df.columns:
            # PENTING: Jangan cek kolom 'Waktu' sebagai guru
            if col == "Waktu": 
                continue

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

def apply_heatmap(df):
    if not isinstance(df, pd.DataFrame): return df
    if not df.index.is_unique: return pd.DataFrame('', index=df.index, columns=df.columns)

    df_style = pd.DataFrame('', index=df.index, columns=df.columns)
    coords = get_conflict_coordinates(df)
    for r, c in coords:
        df_style.at[r, c] = 'background-color: #ff4b4b; color: white; font-weight: bold; border: 2px solid white;'
    return df_style

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.header("Menu Navigasi")
    menu = st.radio("Langkah:", [
        "1. Upload Data Sekolah", 
        "2. Setting Waktu & Break", 
        "3. Input Jadwal (Visual)"
    ])

# ==========================================
# MENU 1: DATA SEKOLAH
# ==========================================
if menu == "1. Upload Data Sekolah":
    st.header("📂 Database Kurikulum")
    uploaded_file = st.file_uploader("Upload File (Excel/CSV)", type=['xlsx', 'csv'])
    
    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'): df_up = pd.read_csv(uploaded_file)
            else: df_up = pd.read_excel(uploaded_file)
            
            col_map = {'Kelas':'Class', 'Mata Pelajaran':'Subject Name', 'Jam':'Periods/Week', 'Guru':'Teacher Name', 'Initial':'Teacher Initials', 'Init Subj':'Subject Code'}
            df_up = df_up.rename(columns=col_map)
            
            required = ['Class', 'Subject Name', 'Subject Code', 'Teacher Name', 'Teacher Initials', 'Periods/Week']
            if all(col in df_up.columns for col in required):
                df_up['Class'] = df_up['Class'].astype(str)
                st.session_state['data_subjects'] = df_up
                st.session_state['data_classes'] = sorted(df_up['Class'].unique().tolist())
                st.success(f"✅ Berhasil memuat {len(df_up)} data Mapel!")
            else:
                st.error("Kolom tidak lengkap.")
        except Exception as e:
            st.error(f"Error: {e}")
            
    st.divider()
    st.download_button("⬇️ Download Template", generate_excel_template(), "Template_Jadwal.xlsx")

# ==========================================
# MENU 2: SETTING WAKTU
# ==========================================
elif menu == "2. Setting Waktu & Break":
    st.header("⏰ Setting Waktu")
    c1, c2, c3 = st.columns(3)
    start_time = c1.time_input("Jam Masuk", datetime.time(7,0))
    jp_dur = c2.number_input("Durasi 1 JP (Menit)", 35)
    total_jp = c3.number_input("Total JP Hari Ini", 10)
    
    st.subheader("☕ Konfigurasi Istirahat")
    num_breaks = st.number_input("Jumlah Break", 0, 4, 2)
    break_configs = []
    if num_breaks > 0:
        for i in range(num_breaks):
            bc1, bc2 = st.columns(2)
            pos = bc1.number_input(f"Break {i+1} SETELAH Jam ke-", 1, total_jp, (4 if i==0 else 8), key=f"bpos{i}")
            dur = bc2.number_input(f"Durasi Break {i+1} (Menit)", 5, 60, (15 if i==0 else 30), key=f"bdur{i}")
            break_configs.append({'after': pos, 'duration': dur})
    
    if st.button("Simpan Struktur Waktu"):
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
        st.session_state['manual_schedule'] = {} # Reset grid
        st.success("Waktu tersimpan! Grid di-reset.")

# ==========================================
# MENU 3: INPUT JADWAL (VISUAL MODE)
# ==========================================
elif menu == "3. Input Jadwal (Visual)":
    st.header("🗓️ Penyusunan Jadwal")

    if st.session_state['data_subjects'].empty:
        st.error("Data Sekolah Kosong.")
        st.stop()
    if st.session_state['time_structure'].empty:
        st.error("Setting Waktu Kosong.")
        st.stop()

    days = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
    day = st.selectbox("Pilih Hari:", days)
    
    classes = st.session_state['data_classes']
    time_df = st.session_state['time_structure']
    
    # --- STRUKTUR KOLOM: [Waktu, Kelas 1, Kelas 2, ...] ---
    # Index: Period (1, 2, BREAK 1...)
    periods = time_df['Period'].tolist()
    
    # Init Grid
    if day not in st.session_state['manual_schedule']:
        # Buat kolom Waktu + Kelas
        cols = ['Waktu'] + classes
        df_init = pd.DataFrame(index=periods, columns=cols)
        
        # Isi Kolom Waktu dari time_structure
        # Kita mapping Period -> Waktu
        time_map = dict(zip(time_df['Period'], time_df['Waktu']))
        df_init['Waktu'] = df_init.index.map(time_map)
        
        # Auto fill Recess untuk kolom Kelas
        for idx in periods:
            if "BREAK" in idx or "ISTIRAHAT" in idx:
                df_init.loc[idx, classes] = "RECESS" # Isi hanya di kolom kelas
        
        st.session_state['manual_schedule'][day] = df_init
    
    # LOAD DATA
    current_df = st.session_state['manual_schedule'][day].copy()

    # Safety Check
    if not isinstance(current_df, pd.DataFrame):
         st.warning("Resetting corrupted data...")
         del st.session_state['manual_schedule'][day]
         st.rerun()

    # --- 1. VISUAL MONITOR ---
    st.markdown("### 🔴 Layar Pantau Bentrok")
    st.dataframe(
        current_df.style.apply(lambda _: apply_heatmap(current_df), axis=None),
        use_container_width=True,
        height=500
    )

    # --- 2. INPUT EDITOR ---
    st.markdown("### ✏️ Input / Edit Jadwal")
    
    col_config = {}
    
    # 2A. Konfigurasi Kolom Waktu (Read Only)
    col_config["Waktu"] = st.column_config.TextColumn(
        "Pukul",
        width="small",
        disabled=True # KUNCI SUPAYA GAK BISA DIEDIT
    )

    # 2B. Konfigurasi Kolom Kelas (Dropdown)
    for cls in classes:
        subset = st.session_state['data_subjects'][st.session_state['data_subjects']['Class'] == cls]
        opts = [None, "UPACARA", "CHAPEL", "RECESS", "FLAG CEREMONY", "DEVOTION", "SCOUT", "EXERCISE"]
        if not subset.empty:
            for _, row in subset.iterrows():
                opts.append(f"{row['Subject Code']} ({row['Teacher Initials']})")
        col_config[cls] = st.column_config.SelectboxColumn(label=cls, options=opts, width="medium")

    edited_df = st.data_editor(
        current_df,
        column_config=col_config,
        use_container_width=True,
        height=500,
        key=f"editor_{day}"
    )

    # --- SYNC MECHANISM ---
    if not edited_df.equals(current_df):
        st.session_state['manual_schedule'][day] = edited_df
        st.rerun()
    
    st.divider()
    if st.button("💾 Export Excel"):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            for d in days:
                if d in st.session_state['manual_schedule']:
                    st.session_state['manual_schedule'][d].to_excel(writer, sheet_name=d)
        st.download_button("Download Excel", out.getvalue(), "Jadwal_Visual_Lengkap.xlsx")
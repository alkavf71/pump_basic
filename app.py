import streamlit as st
import pandas as pd

# Konfigurasi Halaman
st.set_page_config(page_title="Motor Pump Diagnostic System", layout="wide")

st.title("🛠️ Motor Pump Diagnostic & Condition Monitoring")
st.markdown("""
Sistem ini membantu mengidentifikasi kondisi mekanis, hidrolik, dan elektrikal pada sistem Motor-Pump.
**Catatan:** Diagnosa ini berdasarkan aturan umum (Rule of Thumb) nilai RMS. Untuk analisis mendalam, diperlukan data Spektrum (FFT).
""")

# --- INISIALISASI SESSION STATE (Untuk menyimpan input) ---
if 'inputs' not in st.session_state:
    st.session_state.inputs = {}

# ==============================================================================
# BAGIAN 1: VIBRATION VELOCITY (Low Frequency)
# ==============================================================================
st.header("1. Vibration Velocity (mm/s RMS)")
st.caption("Input nilai getaran kecepatan untuk mendeteksi Unbalance, Misalignment, Looseness.")

col_b1, col_b2, col_b3, col_b4 = st.columns(4)

with col_b1:
    st.subheader("Motor DE (B1)")
    v_b1_h = st.number_input("Horizontal (H)", min_value=0.0, step=0.01, key="v_b1_h")
    v_b1_v = st.number_input("Vertical (V)", min_value=0.0, step=0.01, key="v_b1_v")
    v_b1_a = st.number_input("Axial (A)", min_value=0.0, step=0.01, key="v_b1_a")

with col_b2:
    st.subheader("Motor NDE (B2)")
    v_b2_h = st.number_input("Horizontal (H)", min_value=0.0, step=0.01, key="v_b2_h")
    v_b2_v = st.number_input("Vertical (V)", min_value=0.0, step=0.01, key="v_b2_v")
    # B2 biasanya tidak punya Axial, tapi kita set 0 jika tidak ada input
    v_b2_a = 0.0 

with col_b3:
    st.subheader("Pump DE (B3)")
    v_b3_h = st.number_input("Horizontal (H)", min_value=0.0, step=0.01, key="v_b3_h")
    v_b3_v = st.number_input("Vertical (V)", min_value=0.0, step=0.01, key="v_b3_v")
    v_b3_a = st.number_input("Axial (A)", min_value=0.0, step=0.01, key="v_b3_a")

with col_b4:
    st.subheader("Pump NDE (B4)")
    v_b4_h = st.number_input("Horizontal (H)", min_value=0.0, step=0.01, key="v_b4_h")
    v_b4_v = st.number_input("Vertical (V)", min_value=0.0, step=0.01, key="v_b4_v")
    v_b4_a = 0.0

# ==============================================================================
# BAGIAN 2: ACCELERATION BANDS (High Frequency)
# ==============================================================================
st.header("2. Acceleration Bands (g RMS)")
st.caption("Input nilai akselerasi untuk mendeteksi kerusakan Bearing (Early Warning).")

acc_cols = st.columns(4)
bearings = ["Motor DE (B1)", "Motor NDE (B2)", "Pump DE (B3)", "Pump NDE (B4)"]
acc_keys = ["0.5-1.5", "1.5-5", "5-16", "Total"]

acc_data = {}

for i, bearing in enumerate(bearings):
    with acc_cols[i]:
        st.markdown(f"**{bearing}**")
        acc_data[bearing] = {}
        acc_data[bearing]['0.5-1.5'] = st.number_input(f"0.5-1.5 kHz", min_value=0.0, step=0.01, key=f"acc_{i}_1")
        acc_data[bearing]['1.5-5'] = st.number_input(f"1.5-5 kHz", min_value=0.0, step=0.01, key=f"acc_{i}_2")
        acc_data[bearing]['5-16'] = st.number_input(f"5-16 kHz", min_value=0.0, step=0.01, key=f"acc_{i}_3")
        acc_data[bearing]['Total'] = st.number_input(f"Total Acc", min_value=0.0, step=0.01, key=f"acc_{i}_tot")

# ==============================================================================
# BAGIAN 3: HYDRAULIC PARAMETERS
# ==============================================================================
st.header("3. Hydraulic Conditions")
st.caption("Parameter proses untuk mendeteksi Cavitation atau Blockage.")

hyd_col1, hyd_col2 = st.columns(2)
with hyd_col1:
    suction_press = st.number_input("Suction Pressure (bar)", min_value=0.0, step=0.1, key="suction")
with hyd_col2:
    discharge_press = st.number_input("Discharge Pressure (bar)", min_value=0.0, step=0.1, key="discharge")

# ==============================================================================
# BAGIAN 4: ELECTRICAL MEASUREMENTS
# ==============================================================================
st.header("4. Electrical Measurements")
st.caption("Ketidakseimbangan arus (Current Imbalance).")

elec_col1, elec_col2, elec_col3 = st.columns(3)
with elec_col1:
    current_r = st.number_input("Current Phase R (Amp)", min_value=0.0, step=0.1, key="curr_r")
with elec_col2:
    current_s = st.number_input("Current Phase S (Amp)", min_value=0.0, step=0.1, key="curr_s")
with elec_col3:
    current_t = st.number_input("Current Phase T (Amp)", min_value=0.0, step=0.1, key="curr_t")

# ==============================================================================
# LOGIKA ANALISA & HASIL
# ==============================================================================
st.divider()
if st.button("🔍 ANALISA KONDISI MESIN"):
    
    results = []
    
    # --- 1. LOGIKA VELOCITY (Unbalance, Misalignment, Looseness) ---
    # Kita akan mengecek setiap Bearing yang memiliki data Axial (B1 & B3) dan Non-Axial (B2 & B4)
    
    vibration_points = [
        {"name": "Motor DE (B1)", "h": v_b1_h, "v": v_b1_v, "a": v_b1_a},
        {"name": "Motor NDE (B2)", "h": v_b2_h, "v": v_b2_v, "a": v_b2_a},
        {"name": "Pump DE (B3)", "h": v_b3_h, "v": v_b3_v, "a": v_b3_a},
        {"name": "Pump NDE (B4)", "h": v_b4_h, "v": v_b4_v, "a": v_b4_a},
    ]

    st.subheader("📊 Hasil Diagnosa Mekanis (Velocity)")
    
    mech_cols = st.columns(2)
    
    for i, point in enumerate(vibration_points):
        total_v = point['h'] + point['v'] + point['a']
        diagnosis = "Normal / Data Kurang"
        color = "🟢"
        
        if total_v > 0:
            # Logika Sederhana (Rule of Thumb)
            # Misalignment: Axial tinggi (> 50% dari total atau > Horizontal/Vertical)
            # Unbalance: Vertical dominan (> Horizontal) dan 1X RPM tinggi (asumsi RMS mewakili ini)
            # Looseness: Harmonik tinggi (sulit deteksi hanya dengan RMS, tapi sering Vertical sangat tinggi)
            
            ratio_a = point['a'] / total_v if total_v > 0 else 0
            ratio_v = point['v'] / total_v if total_v > 0 else 0
            ratio_h = point['h'] / total_v if total_v > 0 else 0
            
            if point['a'] > 0 and ratio_a > 0.5:
                diagnosis = "⚠️ Potensi Misalignment (Axial High)"
                color = "🟠"
            elif ratio_v > 0.6 and point['v'] > point['h']:
                diagnosis = "⚠️ Potensi Unbalance (Vertical Dominant)"
                color = "🔵"
            elif point['v'] > 2 * point['h'] and point['v'] > 2 * point['a']:
                 diagnosis = "⚠️ Potensi Mechanical Looseness"
                 color = "🟣"
            else:
                diagnosis = "✅ Kondisi Baik / General Vibration"
                color = "🟢"
                
        with mech_cols[i % 2]:
            st.metric(label=f"{point['name']} - Status", value=diagnosis)
            st.write(f"*H: {point['h']}, V: {point['v']}, A: {point['a']}*")

    # --- 2. LOGIKA ACCELERATION (Bearing) ---
    st.subheader("📈 Hasil Diagnosa Bearing (Acceleration)")
    bear_cols = st.columns(4)
    
    for i, bearing in enumerate(bearings):
        data = acc_data[bearing]
        status = "✅ Bearing OK"
        color = "🟢"
        
        # Logika: Jika band frekuensi tinggi (5-16kHz) signifikan terhadap Total
        # Atau jika nilai absolutnya sangat tinggi (misal > 5g untuk contoh ini)
        if data['Total'] > 0:
            hf_ratio = data['5-16'] / data['Total']
            if hf_ratio > 0.3 or data['5-16'] > 2.0: # Threshold contoh
                status = "⚠️ Early Bearing Fault (HF Noise)"
                color = "🟠"
            elif data['Total'] > 10.0:
                status = "🔴 Bearing Damage Severe"
                color = "🔴"
        
        with bear_cols[i]:
            st.metric(label=bearing, value=status)
            st.caption(f"Total: {data['Total']} g | 5-16kHz: {data['5-16']} g")

    # --- 3. LOGIKA HYDRAULIC ---
    st.subheader("💧 Kondisi Hidrolik")
    hyd_status = "✅ Normal Operation"
    hyd_detail = ""
    
    delta_p = discharge_press - suction_press
    
    if suction_press < 1.0 and discharge_press > 5.0: # Contoh threshold
        hyd_status = "⚠️ Risk of Cavitation (Suction Low)"
        hyd_detail = "Tekanan hisap terlalu rendah, berpotensi terjadi kavitasi."
    elif delta_p < 1.0 and discharge_press > 0:
        hyd_status = "⚠️ Possible Blockage or Recirculation"
        hyd_detail = "Delta pressure sangat kecil."
    elif suction_press == 0 and discharge_press == 0:
        hyd_status = "⚪ Pump Stopped / No Flow"
    else:
        hyd_detail = f"Differential Pressure: {delta_p:.2f} bar"

    st.info(f"**Status Hidrolik:** {hyd_status}\n\n{hyd_detail}")

    # --- 4. LOGIKA ELECTRICAL ---
    st.subheader("⚡ Kondisi Elektrikal")
    elec_status = "✅ Balanced"
    
    currents = [current_r, current_s, current_t]
    if sum(currents) > 0:
        avg_current = sum(currents) / 3
        max_dev = max([abs(c - avg_current) for c in currents])
        imbalance_pct = (max_dev / avg_current) * 100 if avg_current > 0 else 0
        
        if imbalance_pct > 10:
            elec_status = f"🔴 High Imbalance ({imbalance_pct:.1f}%)"
            st.error("Arus tidak seimbang > 10%. Cek koneksi terminal, tegangan supply, atau rotor bar motor.")
        elif imbalance_pct > 5:
            elec_status = f"⚠️ Moderate Imbalance ({imbalance_pct:.1f}%)"
            st.warning("Arus tidak seimbang > 5%. Perlu monitoring.")
        else:
            st.success(f"Arus Seimbang (Imbalance: {imbalance_pct:.2f}%)")
    
    st.metric(label="Electrical Status", value=elec_status)

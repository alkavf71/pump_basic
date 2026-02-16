import streamlit as st
import pandas as pd
import numpy as np

# Konfigurasi Halaman
st.set_page_config(page_title="Advanced Motor Pump Diagnostic", layout="wide", page_icon="⚙️")

# CSS Custom untuk tampilan yang lebih rapi
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #ccc;
        margin-bottom: 10px;
    }
    .stAlert {
        margin-top: 10px;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# FUNGSI HELPER & LOGIKA STANDAR
# ==============================================================================

def get_iso_severity(power_kw, rpm, coupling_type, velocity_rms):
    """
    Menghitung Severity berdasarkan ISO 10816-3 (General Industrial Machines).
    Returns: Zone (A, B, C, D), Status Color, Limit Value
    """
    # Simplifikasi Class berdasarkan Power
    # Class 1: Small machines (<15kW)
    # Class 2: Medium machines (15-75kW)
    # Class 3: Large machines (>75kW)
    
    if power_kw < 15:
        machine_class = 1
    elif power_kw <= 75:
        machine_class = 2
    else:
        machine_class = 3

    # Thresholds (mm/s RMS) - Pendekatan Umum ISO 10816
    # Note: Ini adalah aproksimasi. Standar asli lebih kompleks tergantung foundation (Rigid/Flexible)
    if coupling_type == "Rigid":
        # Rigid biasanya limit lebih ketat
        limits = {1: [1.4, 2.8, 4.5], 2: [1.8, 4.5, 7.1], 3: [2.3, 4.5, 7.1]} 
    else: # Flexible
        limits = {1: [1.8, 4.5, 7.1], 2: [2.8, 4.5, 7.1], 3: [4.5, 7.1, 11.2]}

    threshold = limits.get(machine_class, [2.8, 4.5, 7.1])
    
    if velocity_rms < threshold[0]:
        return "Zone A (Good)", "🟢", threshold[0]
    elif velocity_rms < threshold[1]:
        return "Zone B (Satisfactory)", "🟡", threshold[1]
    elif velocity_rms < threshold[2]:
        return "Zone C (Unsatisfactory)", "🟠", threshold[2]
    else:
        return "Zone D (Unacceptable)", "🔴", threshold[2]

def diagnose_fault(h, v, a, total_v):
    """
    Mendiagnosa jenis fault berdasarkan rasio arah getaran.
    """
    if total_v == 0:
        return "No Data", "Tidak ada data getaran."
    
    ratio_a = a / total_v
    ratio_v = v / total_v
    ratio_h = h / total_v
    
    faults = []
    reasons = []
    
    # 1. Misalignment (Dominan Axial)
    # Jika Axial > 50% dari total atau Axial > Radial (H/V)
    if ratio_a > 0.5 or (a > h and a > v):
        faults.append("Misalignment")
        reasons.append(f"Getaran Axial ({a:.2f}) dominan dibanding Radial. Rasio Axial: {ratio_a:.1%}")
    
    # 2. Unbalance (Dominan Radial, khususnya Vertikal/Horizontal seimbang tapi tinggi)
    # Biasanya 1X RPM. Jika Axial rendah tapi Radial tinggi.
    elif ratio_a < 0.3 and (ratio_v > 0.4 or ratio_h > 0.4):
        faults.append("Unbalance")
        reasons.append(f"Getaran Radial (H:{h:.2f}, V:{v:.2f}) dominan. Axial rendah ({ratio_a:.1%}).")
        
    # 3. Looseness (Vertikal jauh lebih tinggi dari Horizontal)
    # Seringkali menghasilkan harmonik, tapi secara RMS, V >> H adalah indikasi kuat.
    if v > 1.5 * h and v > a:
        if "Unbalance" in faults:
            faults.remove("Unbalance") # Looseness lebih prioritas jika V >> H
        faults.append("Mechanical Looseness")
        reasons.append(f"Getaran Vertikal ({v:.2f}) jauh lebih tinggi dari Horizontal ({h:.2f}). Indikasi fondasi longgar atau bearing loose.")
        
    if not faults:
        return "Normal / General Vibration", "Kondisi getaran masih dalam batas wajar atau pola tidak spesifik."
    
    return ", ".join(faults), "; ".join(reasons)

def check_temperature(temp):
    if temp < 70:
        return "🟢 Normal", "Suhu bearing dalam batas aman (<70°C)."
    elif temp < 85:
        return "🟡 Warning", "Suhu mulai meningkat. Cek pelumasan (70-85°C)."
    elif temp < 95:
        return "🟠 Critical", "Suhu tinggi. Risiko kerusakan bearing (85-95°C)."
    else:
        return "🔴 Overheat", "Suhu sangat kritis! Stop mesin segera (>95°C)."

def check_electrical(v_r, v_s, v_t, i_r, i_s, i_t, fla, rated_voltage):
    issues = []
    recommendations = []
    
    # Voltage Analysis
    avg_v = np.mean([v_r, v_s, v_t])
    max_dev_v = max([abs(v - avg_v) for v in [v_r, v_s, v_t]])
    v_unbalance = (max_dev_v / avg_v) * 100 if avg_v > 0 else 0
    
    if avg_v < rated_voltage * 0.9:
        issues.append("Under Voltage")
        recommendations.append("Cek sumber tegangan supply. Tegangan turun >10%.")
    elif v_unbalance > 2: # NEMA standard usually 1-2%
        issues.append(f"Voltage Unbalance ({v_unbalance:.1f}%)")
        recommendations.append("Cek koneksi terminal atau trafo supply. Unbalance tegangan menyebabkan panas motor.")

    # Current Analysis
    avg_i = np.mean([i_r, i_s, i_t])
    max_dev_i = max([abs(i - avg_i) for i in [i_r, i_s, i_t]])
    i_unbalance = (max_dev_i / avg_i) * 100 if avg_i > 0 else 0
    
    if fla > 0:
        load_pct = (avg_i / fla) * 100
        if load_pct < 40:
            issues.append("Under Loading")
            recommendations.append("Motor beroperasi di bawah 40% FLA. Efisiensi rendah, cek ukuran pompa/motor.")
        elif load_pct > 100:
            issues.append("Over Loading")
            recommendations.append("Motor kelebihan beban. Cek ampere trap atau kondisi mekanis pompa.")
            
    if i_unbalance > 10:
        issues.append(f"Current Unbalance ({i_unbalance:.1f}%)")
        recommendations.append("Unbalance arus tinggi. Kemungkinan rotor bar putus atau masalah winding.")
    elif i_unbalance > 5:
        issues.append(f"Minor Current Unbalance ({i_unbalance:.1f}%)")
        recommendations.append("Monitor tren unbalance arus.")
        
    if not issues:
        return "✅ Electrical Healthy", "Parameter tegangan dan arus seimbang serta dalam batas normal."
    
    return "⚠️ " + ", ".join(issues), "; ".join(recommendations)

# ==============================================================================
# UI INPUT SECTION
# ==============================================================================

st.title("⚙️ Advanced Motor Pump Diagnostic System")
st.markdown("Diagnosa berbasis ISO 10816, Pattern Recognition, dan Electrical Analysis.")

# --- SIDEBAR / TOP: MACHINE SPECS ---
with st.expander("📋 1. Machine Specifications (Klik untuk Isi)", expanded=True):
    col_spec1, col_spec2, col_spec3 = st.columns(3)
    with col_spec1:
        motor_kw = st.number_input("Motor Power (kW)", min_value=0.0, value=55.0)
        motor_rpm = st.number_input("Rated RPM", min_value=0, value=2900)
        coupling_type = st.selectbox("Coupling Type", ["Flexible", "Rigid"])
    with col_spec2:
        pump_class = st.selectbox("Pump Class (ISO)", ["Class 1 (Small)", "Class 2 (Medium)", "Class 3 (Large)"])
        fla = st.number_input("Motor FLA (Amp)", min_value=0.0, value=100.0)
        rated_voltage = st.number_input("Rated Voltage (V)", min_value=0, value=380)
    with col_spec3:
        st.info(f"ISO Limit Reference: Based on {motor_kw}kW & {coupling_type}")

# --- MAIN INPUTS ---
st.divider()

# Row 1: Vibration & Temp
st.subheader("📊 2. Vibration & Temperature Data")
vib_cols = st.columns(4)
bearings = ["Motor DE (B1)", "Motor NDE (B2)", "Pump DE (B3)", "Pump NDE (B4)"]
vib_data = {}
temp_data = {}

for i, b_name in enumerate(bearings):
    with vib_cols[i]:
        st.markdown(f"**{b_name}**")
        has_axial = (i == 0 or i == 2) # B1 & B3 have Axial
        
        h = st.number_input(f"H (mm/s)", key=f"h_{i}", min_value=0.0, step=0.01)
        v = st.number_input(f"V (mm/s)", key=f"v_{i}", min_value=0.0, step=0.01)
        a = st.number_input(f"A (mm/s)", key=f"a_{i}", min_value=0.0, step=0.01) if has_axial else 0.0
        temp = st.number_input(f"Temp (°C)", key=f"t_{i}", min_value=0.0, step=0.1)
        
        vib_data[b_name] = {'h': h, 'v': v, 'a': a, 'total': h+v+a}
        temp_data[b_name] = temp

# Row 2: Acceleration
st.subheader("📈 3. Acceleration Bands (g RMS)")
acc_cols = st.columns(4)
acc_data = {}

for i, b_name in enumerate(bearings):
    with acc_cols[i]:
        st.markdown(f"**{b_name}**")
        b1 = st.number_input(f"0.5-1.5 kHz", key=f"ab1_{i}", min_value=0.0, step=0.01)
        b2 = st.number_input(f"1.5-5 kHz", key=f"ab2_{i}", min_value=0.0, step=0.01)
        b3 = st.number_input(f"5-16 kHz", key=f"ab3_{i}", min_value=0.0, step=0.01)
        total_acc = b1 + b2 + b3 # Auto Calculate
        
        st.write(f"**Total Acc: {total_acc:.2f} g**")
        acc_data[b_name] = {'b1': b1, 'b2': b2, 'b3': b3, 'total': total_acc}

# Row 3: Electrical
st.subheader("⚡ 4. Electrical Measurements")
elec_col1, elec_col2 = st.columns(2)
with elec_col1:
    st.markdown("**Voltage (Volt)**")
    v_r = st.number_input("Phase R", key="vr", min_value=0.0)
    v_s = st.number_input("Phase S", key="vs", min_value=0.0)
    v_t = st.number_input("Phase T", key="vt", min_value=0.0)
with elec_col2:
    st.markdown("**Current (Amp)**")
    i_r = st.number_input("Phase R", key="ir", min_value=0.0)
    i_s = st.number_input("Phase S", key="is", min_value=0.0)
    i_t = st.number_input("Phase T", key="it", min_value=0.0)

# Row 4: Hydraulic
st.subheader("💧 5. Hydraulic Parameters")
hyd_col1, hyd_col2 = st.columns(2)
with hyd_col1:
    suction_p = st.number_input("Suction Pressure (bar)", min_value=0.0)
with hyd_col2:
    discharge_p = st.number_input("Discharge Pressure (bar)", min_value=0.0)

# ==============================================================================
# ANALYSIS & DASHBOARD
# ==============================================================================
st.divider()
if st.button("🚀 RUN DIAGNOSTIC ENGINE", type="primary"):
    
    final_report = []
    st.header("📋 Diagnostic Report & Conclusion")
    
    # 1. MECHANICAL VIBRATION ANALYSIS
    st.subheader("1. Mechanical Vibration Diagnosis (ISO 10816)")
    mech_grid = st.columns(2)
    
    for i, b_name in enumerate(bearings):
        data = vib_data[b_name]
        total_v = data['total']
        
        # ISO Severity
        zone, color, limit = get_iso_severity(motor_kw, motor_rpm, coupling_type, total_v)
        
        # Fault Diagnosis
        fault, reason = diagnose_fault(data['h'], data['v'], data['a'], total_v)
        
        # Temp Check
        temp_stat, temp_reason = check_temperature(temp_data[b_name])
        
        with mech_grid[i % 2]:
            with st.container(border=True):
                st.markdown(f"#### {b_name}")
                c1, c2 = st.columns(2)
                c1.metric("Vibration Severity", zone, delta=f"Limit: {limit} mm/s")
                c2.metric("Temperature", f"{temp_data[b_name]}°C", delta=temp_stat.split()[0])
                
                if "Zone C" in zone or "Zone D" in zone or "Critical" in temp_stat or "Overheat" in temp_stat:
                    st.error(f"**Fault Detected:** {fault}")
                    st.caption(f"🔍 *Reason:* {reason}")
                    st.caption(f"🌡️ *Temp:* {temp_reason}")
                    final_report.append(f"{b_name}: {fault} ({zone}), Temp: {temp_stat}")
                elif "Zone B" in zone or "Warning" in temp_stat:
                    st.warning(f"**Attention:** {fault}")
                    st.caption(f"🔍 *Reason:* {reason}")
                    final_report.append(f"{b_name}: {fault} ({zone}), Temp: {temp_stat}")
                else:
                    st.success(f"**Status:** {fault}")
                    st.caption(f"🔍 *Reason:* {reason}")

    # 2. BEARING ACCELERATION
    st.subheader("2. Bearing Condition (Acceleration)")
    acc_grid = st.columns(4)
    for i, b_name in enumerate(bearings):
        data = acc_data[b_name]
        status = "✅ Bearing OK"
        rec = "No action needed."
        
        # Logic: High Frequency Energy (5-16kHz) indicates early bearing fault
        if data['total'] > 0:
            hf_ratio = data['b3'] / data['total'] # 5-16kHz ratio
            
            if data['total'] > 10: # Severe
                status = "🔴 Bearing Damage"
                rec = "Ganti Bearing segera. Cek pelumasan."
            elif hf_ratio > 0.4 or data['b3'] > 3.0: # Early fault
                status = "🟠 Early Bearing Fault"
                rec = "Monitoring ketat. Greasing schedule mungkin perlu dipercepat."
            elif data['total'] > 5.0:
                status = "🟡 Warning"
                rec = "Periksa kondisi pelumasan."
        
        with acc_grid[i]:
            st.metric(b_name, status)
            if status != "✅ Bearing OK":
                st.caption(rec)
                final_report.append(f"{b_name}: {status}")

    # 3. ELECTRICAL
    st.subheader("3. Electrical Health")
    elec_stat, elec_rec = check_electrical(v_r, v_s, v_t, i_r, i_s, i_t, fla, rated_voltage)
    
    if "⚠️" in elec_stat:
        st.error(f"**{elec_stat}**")
        st.info(f"💡 *Recommendation:* {elec_rec}")
        final_report.append(f"Electrical: {elec_stat}")
    else:
        st.success(f"**{elec_stat}**")
        st.caption(elec_rec)

    # 4. HYDRAULIC
    st.subheader("4. Hydraulic Performance")
    delta_p = discharge_p - suction_p
    hyd_stat = "✅ Normal Flow"
    hyd_rec = "Operasi normal."
    
    if suction_p < 1.0 and discharge_p > 2.0:
        hyd_stat = "⚠️ Risk of Cavitation"
        hyd_rec = "Tekanan hisap rendah. Cek filter suction atau level tangki."
        final_report.append("Hydraulic: Cavitation Risk")
    elif delta_p < 1.0:
        hyd_stat = "⚠️ Low Head / Recirculation"
        hyd_rec = "Delta pressure rendah. Cek valve discharge atau impeller wear."
        final_report.append("Hydraulic: Low Head")
        
    st.metric("Differential Pressure", f"{delta_p:.2f} bar")
    if "⚠️" in hyd_stat:
        st.warning(f"**{hyd_stat}** - {hyd_rec}")
    else:
        st.success(hyd_stat)

    # ==============================================================================
    # FINAL SUMMARY
    # ==============================================================================
    st.divider()
    st.header("📝 Final Conclusion & Recommendations")
    
    if not final_report:
        st.success("🎉 Semua parameter dalam kondisi baik. Tidak ada tindakan segera diperlukan.")
    else:
        st.error("⚠️ Ditemukan beberapa anomali yang memerlukan perhatian:")
        
        # Create a summary dataframe
        summary_data = []
        for item in final_report:
            summary_data.append({"Issue": item})
        
        st.table(pd.DataFrame(summary_data))
        
        st.markdown("### 🛠️ Recommended Actions:")
        st.markdown("""
        1. **Prioritas Tinggi:** Jika ada status 'Zone D', 'Overheat', atau 'Bearing Damage', rencanakan shutdown segera.
        2. **Misalignment:** Lakukan laser alignment check pada coupling motor-pump.
        3. **Unbalance:** Lakukan balancing pada rotor/impeller.
        4. **Electrical:** Cek koneksi terminal box dan ukur tegangan sumber.
        5. **Hydraulic:** Pastikan NPSH Available > NPSH Required untuk menghindari kavitasi.
        """)

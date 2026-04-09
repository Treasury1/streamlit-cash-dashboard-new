import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os

st.set_page_config(layout="wide")

# ✅ FIX: fungsi format angka
def fmt_number(x):
    try:
        if pd.isna(x):
            return "-"
        return "{:,.0f}".format(x).replace(",", ".")
    except:
        return x

st.markdown("""
<style>
p, div, h2, h3, h4, h5, h6, span {
  margin-top: 0 !important;
  margin-bottom: 0 !important;
  line-height: 1.2 !important;
}
h1 {
  margin-top: 0rem !important;
  margin-bottom: 0rem !important;
  font-size: 2rem !important;
}
.footer {
  text-align: center;
  font-size: 14px;
  margin-top: 0.3rem;
  color: #555;
}
body, .main { padding-top: 0.3rem !important; padding-bottom: 0.3rem !important; padding-left: 0.3rem !important; padding-right: 0.3rem !important; }
.block-container { padding-top: 1rem !important; padding-bottom: 0.2rem !important; padding-left: 1rem !important ;padding-right: 1rem !important; }
</style>
""", unsafe_allow_html=True)

# --- LOAD DATA ---
sheet_id = "1vTzm9o_m2wwiiS4jWPbP-nMmelIwJCSonBx-pmiN2Q0"
url_saldo = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=SALDO"
url_cf = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=CASHFLOW"

df_saldo = pd.read_csv(url_saldo)
df_cf = pd.read_csv(url_cf)

# --- PREPARE SALDO DATA ---
df_saldo['TANGGAL'] = pd.to_datetime(df_saldo['TANGGAL'], dayfirst=True, errors='coerce')
latest_date = df_saldo['TANGGAL'].max()
saldo_latest = df_saldo[df_saldo['TANGGAL'] == latest_date].copy()
saldo_latest['JENIS SALDO'] = saldo_latest['JENIS SALDO'].astype(str).str.upper().str.strip()
saldo_latest['BANK'] = saldo_latest['BANK'].astype(str).str.upper().str.strip()

update_info = latest_date.strftime("%d %B %Y")

bank_color_map = {
    'BRI': '#0A3185','BSI': '#00A39D','BTN': '#0057B8','BNI': '#F37021',
    'MANDIRI': '#002F6C','CIMB': '#990000','BJB': '#AB9B56','BCA': '#00529B',
    'RAYA': '#00549A','BTN SYARIAH': '#FFC20E','BRI USD': '#0A3185'
}
fallback_colors = ['#999999', '#BBBBBB', '#CCCCCC']

def get_bank_colors(banks):
    return [bank_color_map.get(bank.upper(), fallback_colors[i % len(fallback_colors)]) for i, bank in enumerate(banks)]

col1, col2 = st.columns([1, 6])

with col1:
    # ✅ FIX logo path aman
    current_dir = os.path.dirname(__file__)
    image_path = os.path.join(current_dir, "asdp-logo.png")
    if os.path.exists(image_path):
        st.image(image_path, width=80)

with col2:
    st.markdown(
        "<h1 style='text-align:center;'>Cash and Cash Equivalents Ending Balance Dashboard</h1>",
        unsafe_allow_html=True
    )

st.markdown(f"<p><i>Data per {update_info}</i></p>", unsafe_allow_html=True)
st.markdown("<p><i>(Dalam Miliar Rupiah)</i></p>", unsafe_allow_html=True)

# --- PIVOT ---
pivot = saldo_latest.pivot_table(
    index='BANK',
    columns='JENIS SALDO',
    values='SALDO',
    aggfunc='sum',
    fill_value=0
).reset_index()

pivot['TOTAL SALDO'] = pivot.get('GIRO', 0) + pivot.get('DEPOSITO', 0)
pivot = pivot.sort_values(by='TOTAL SALDO', ascending=False).reset_index(drop=True)

grand_total = pd.DataFrame({
    'BANK': ['GRAND TOTAL'],
    'GIRO': [pivot.get('GIRO', pd.Series([0])).sum()],
    'DEPOSITO': [pivot.get('DEPOSITO', pd.Series([0])).sum()],
    'TOTAL SALDO': [pivot['TOTAL SALDO'].sum()]
})

pivot_display = pd.concat([pivot, grand_total], ignore_index=True)
pivot_display[['GIRO', 'DEPOSITO', 'TOTAL SALDO']] = pivot_display[['GIRO', 'DEPOSITO', 'TOTAL SALDO']].round(0).astype(int)

# --- LAYOUT ---
col1, col2, col3 = st.columns([1.2, 1.2, 1.6])

with col1:
    st.markdown("#### Saldo per Bank")

    def highlight_grand_total(row):
        style = 'font-weight: bold; background-color: #f0f0f0' if row.name == len(pivot_display) - 1 else ''
        return [style] * len(row)

    styled_table = pivot_display.style.format(lambda x: '{:,.0f}'.format(x).replace(',', '.'), subset=['GIRO', 'DEPOSITO', 'TOTAL SALDO'])
    styled_table = styled_table.apply(highlight_grand_total, axis=1)

    st.dataframe(styled_table, use_container_width=True, hide_index=True, height=490)

    # --- SUMMARY ---
    st.markdown("#### Restricted Cash and Cash Equivalents")
    saldo_latest['KETERANGAN'] = saldo_latest['KETERANGAN'].astype(str).str.upper().str.strip()

    summary = saldo_latest.groupby(['JENIS SALDO', 'KETERANGAN'])['SALDO'].sum().unstack(fill_value=0)
    summary['TOTAL'] = summary.sum(axis=1)

    # ✅ FIX kolom aman
    for col in ['RESTRICTED', 'NON RESTRICTED']:
        if col not in summary.columns:
            summary[col] = 0

    summary = summary[['RESTRICTED', 'NON RESTRICTED', 'TOTAL']]

    # ✅ FIX formatting aman
    summary_formatted = summary.applymap(fmt_number)

    st.dataframe(summary_formatted, use_container_width=True, height=120)

with col2:
    st.markdown("### Persentase GIRO per Bank")
    giro_data = pivot[pivot.get('GIRO', 0) > 0]
    fig_giro = px.pie(giro_data, names='BANK', values='GIRO', hole=0.4)
    st.plotly_chart(fig_giro, use_container_width=True)

with col3:
    st.markdown("### Grafik Tren")
    df_saldo['BULAN'] = df_saldo['TANGGAL'].dt.to_period('M').dt.to_timestamp()
    monthly = df_saldo.groupby(['BULAN'])['SALDO'].sum().reset_index()

    fig = px.line(monthly.tail(12), x='BULAN', y='SALDO')
    st.plotly_chart(fig, use_container_width=True)

st.markdown("""<div class="footer">Created by Nur Vita Anjaningrum</div>""", unsafe_allow_html=True)

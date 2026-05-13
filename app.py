# app.py — Cash and Cash Equivalents Dashboard
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple
import math

import gspread
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google.oauth2.service_account import Credentials


# --- Konstanta ---
SHEET_GIRO_DEPOSITO = "giro deposito"
SHEET_TOTAL = "total"

SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
)


@dataclass(frozen=True)
class ColGD:
    tanggal: str = "TANGGAL"
    bank: str = "BANK"
    tipe: str = "TYPE"
    cabang_pusat: str = "CABANG/PUSAT"
    keterangan: str = "KETERANGAN"
    saldo: str = "SALDO AKHIR"


@dataclass(frozen=True)
class ColTotal:
    tahun: str = "TAHUN"
    total: str = "CASH & CASH EQUIVALENTS"


# --- CSS Layout ---
def _css_layout():
    st.markdown(
        """
        <style>
          .block-container {
              padding-top: 1.2rem !important;
              max-width: 1400px;
          }
          h1 {
              text-align:center;
              font-size:1.6rem !important;
              margin-bottom:0.6rem;
          }
          table th {
              text-align:center !important;
              font-weight:700 !important;
              background-color:#f8f9fa !important;
          }
          table td:first-child {
              text-align:left !important;
          }
          .footer-credit {
              text-align:center;
              font-size:0.8rem;
              color:#555;
              font-style:italic;
              margin-top:1.2rem;
              padding:0.25rem 0;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


# --- Utility ---
def round_half_up(n):
    """Pembulatan ke atas jika >= .5"""
    if pd.isna(n):
        return 0
    return math.floor(float(n) + 0.5)


def _require_secrets() -> Tuple[str, Dict[str, Any]]:
    if "SPREADSHEET_ID" not in st.secrets or "gcp_service_account" not in st.secrets:
        raise KeyError("Missing Streamlit secrets: SPREADSHEET_ID atau gcp_service_account belum diisi.")

    return (
        str(st.secrets["SPREADSHEET_ID"]).strip(),
        dict(st.secrets["gcp_service_account"]),
    )


@st.cache_resource
def _gs_client(service_account_info: Dict[str, Any]) -> gspread.Client:
    creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_data(ttl=300)
def _load_sheet(
    spreadsheet_id: str,
    worksheet_name: str,
    service_account_info: Dict[str, Any],
) -> pd.DataFrame:
    gc = _gs_client(service_account_info)
    ws = gc.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    return pd.DataFrame(ws.get_all_records())


def _to_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(" ", "", regex=False),
        errors="coerce",
    )


def _style_grand_total(df: pd.DataFrame, label_col: str) -> str:
    """Return HTML table with grand total styled."""
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    html = "<table style='width:100%;border-collapse:collapse;'>"
    html += "<thead><tr>"

    for col in df.columns:
        html += (
            "<th style='border:1px solid #ddd;padding:6px;"
            "background:#f8f9fa;text-align:center;'>"
            f"{col}</th>"
        )

    html += "</tr></thead><tbody>"

    for _, row in df.iterrows():
        if str(row[label_col]) == "Grand Total":
            html += "<tr style='background:#f2f2f2;font-weight:700;'>"
        else:
            html += "<tr>"

        for col in df.columns:
            align = "left" if col == label_col else "right"
            val = row[col]

            if col in numeric_cols:
                val = f"{val:,.0f}"

            html += (
                f"<td style='border:1px solid #ddd;padding:6px;"
                f"text-align:{align};'>{val}</td>"
            )

        html += "</tr>"

    html += "</tbody></table>"
    return html


def _prepare_total_trend(total: pd.DataFrame, ct: ColTotal) -> pd.DataFrame:
    """Menyiapkan data tren agar label dan angka aman dipakai untuk grafik."""
    total = total.copy()

    bulan_map = {
        "Jan": "Jan",
        "Feb": "Feb",
        "Mar": "Mar",
        "Apr": "Apr",
        "Mei": "May",
        "Jun": "Jun",
        "Jul": "Jul",
        "Agu": "Aug",
        "Sep": "Sep",
        "Okt": "Oct",
        "Nov": "Nov",
        "Des": "Dec",
    }

    bulan_map_reverse = {
        "Jan": "Jan",
        "Feb": "Feb",
        "Mar": "Mar",
        "Apr": "Apr",
        "May": "Mei",
        "Jun": "Jun",
        "Jul": "Jul",
        "Aug": "Agu",
        "Sep": "Sep",
        "Oct": "Okt",
        "Nov": "Nov",
        "Dec": "Des",
    }

    total[ct.tahun] = total[ct.tahun].astype(str).str.strip()
    total[ct.total] = _to_numeric(total[ct.total]).fillna(0)

    tahun_en = total[ct.tahun].copy()
    for indo, eng in bulan_map.items():
        tahun_en = tahun_en.str.replace(indo, eng, regex=False)

    total["date_sort"] = pd.to_datetime(tahun_en, errors="coerce")
    total["label"] = total["date_sort"].dt.strftime("%b %Y")

    total["label"] = total["label"].fillna(total[ct.tahun])

    for eng, indo in bulan_map_reverse.items():
        total["label"] = total["label"].str.replace(eng, indo, regex=False)

    total = total.sort_values("date_sort", na_position="last")
    total[ct.total] = total[ct.total].apply(round_half_up)

    return total


# --- Main ---
def main():
    st.set_page_config(
        page_title="Cash and Cash Equivalents Dashboard",
        layout="wide",
    )

    _css_layout()

    spreadsheet_id, svc = _require_secrets()

    gd = _load_sheet(spreadsheet_id, SHEET_GIRO_DEPOSITO, svc)
    total = _load_sheet(spreadsheet_id, SHEET_TOTAL, svc)

    cg = ColGD()
    ct = ColTotal()

    # --- Cleaning data giro deposito ---
    gd[cg.bank] = gd[cg.bank].fillna("").astype(str).str.strip().str.upper()
    gd[cg.tipe] = gd[cg.tipe].fillna("").astype(str).str.strip().str.upper()
    gd[cg.cabang_pusat] = gd[cg.cabang_pusat].fillna("").astype(str).str.strip().str.upper()
    gd[cg.keterangan] = gd[cg.keterangan].fillna("").astype(str).str.strip().str.upper()
    gd[cg.saldo] = _to_numeric(gd[cg.saldo]).fillna(0.0)

    # Ambil tanggal terbaru
    update_date = pd.to_datetime(gd[cg.tanggal], errors="coerce").max()
    update_text = update_date.strftime("%d %B %Y") if pd.notna(update_date) else "-"

    # --- Judul dan Update Info ---
    st.markdown(
        """
        <div style='text-align:center;'>
            <h1>Cash and Cash Equivalents Dashboard</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div style='text-align:left; font-style:italic; margin-top:-0.4rem; margin-bottom:1rem;'>
            Updated per {update_text}<br>
            (In Billion Rupiah)
        </div>
        """,
        unsafe_allow_html=True,
    )

    # === Pisahkan data utama ===
    deposito_restricted = gd[
        (gd[cg.tipe] == "DEPOSITO")
        & (gd[cg.keterangan].str.contains(r"\bRESTRICT(ED)?\b", case=False, na=False))
        & (~gd[cg.keterangan].str.contains("NON", case=False, na=False))
    ]

    restricted_total = deposito_restricted[cg.saldo].sum()

    deposito_non = gd[
        (gd[cg.tipe] == "DEPOSITO")
        & (gd[cg.keterangan].str.contains("NON", case=False, na=False))
    ]

    giro = gd[gd[cg.tipe] == "GIRO"]
    kas = gd[gd[cg.tipe] == "KAS"]

    # === BAGIAN ATAS: TABEL TOTAL CABANG/PUSAT ===
    table_total = pd.DataFrame({"Cabang/Pusat": ["CABANG", "PUSAT"]})

    depo_non_sum = deposito_non.groupby(cg.cabang_pusat, as_index=False)[cg.saldo].sum()
    depo_non_sum.rename(columns={cg.saldo: "Total Deposito (Non Restricted)"}, inplace=True)

    table_total = table_total.merge(
        depo_non_sum,
        left_on="Cabang/Pusat",
        right_on=cg.cabang_pusat,
        how="left",
    )

    giro_sum = giro.groupby(cg.cabang_pusat, as_index=False)[cg.saldo].sum()
    giro_sum.rename(columns={cg.saldo: "Total Giro"}, inplace=True)

    table_total = table_total.merge(
        giro_sum,
        left_on="Cabang/Pusat",
        right_on=cg.cabang_pusat,
        how="left",
    )

    kas_sum = kas.groupby(cg.cabang_pusat, as_index=False)[cg.saldo].sum()
    kas_sum.rename(columns={cg.saldo: "Total Kas"}, inplace=True)

    table_total = table_total.merge(
        kas_sum,
        left_on="Cabang/Pusat",
        right_on=cg.cabang_pusat,
        how="left",
    )

    table_total = table_total.drop(
        columns=[
            c
            for c in table_total.columns
            if "CABANG/PUSAT" in c.upper() and c != "Cabang/Pusat"
        ],
        errors="ignore",
    ).fillna(0)

    table_total["Total"] = (
        table_total["Total Deposito (Non Restricted)"]
        + table_total["Total Giro"]
        + table_total["Total Kas"]
    )

    for col in ["Total Deposito (Non Restricted)", "Total Giro", "Total Kas", "Total"]:
        table_total[col] = table_total[col].apply(round_half_up)

    table_total.loc[len(table_total)] = [
        "Grand Total",
        table_total["Total Deposito (Non Restricted)"].sum(),
        table_total["Total Giro"].sum(),
        table_total["Total Kas"].sum(),
        table_total["Total"].sum(),
    ]

    # === GRAFIK TREN ===
    total_trend = _prepare_total_trend(total, ct)

    bar_texts = [f"{v:,.0f}" for v in total_trend[ct.total]]

    fig_bar = go.Figure()

    fig_bar.add_bar(
        x=total_trend["label"],
        y=total_trend[ct.total],
        text=bar_texts,
        textposition="outside",
        name="Cash & Cash Equivalents",
    )

    fig_bar.add_scatter(
        x=total_trend["label"],
        y=total_trend[ct.total],
        mode="lines+markers",
        line=dict(width=2),
        name="Trend",
    )

    ymax = total_trend[ct.total].max()
    ymax = float(ymax) if pd.notna(ymax) and ymax > 0 else 1

    fig_bar.update_layout(
        height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis=dict(range=[0, ymax * 1.2]),
        showlegend=False,
    )

    colA, colB = st.columns(2)

    with colA:
        st.subheader("Total Cash and Cash Equivalents")
        st.markdown(
            _style_grand_total(table_total, label_col="Cabang/Pusat"),
            unsafe_allow_html=True,
        )
        st.markdown(
            (
                "<div style='font-style:italic;margin-top:6px;'>"
                f"*Exclude Restricted Deposito: {round_half_up(restricted_total):,.0f}*"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

    with colB:
        st.subheader("Cash and Cash Equivalents Trend")
        st.plotly_chart(fig_bar, use_container_width=True)

    # === BAGIAN BAWAH: DETAIL PER BANK ===
    giro_pusat = giro[giro[cg.cabang_pusat] == "PUSAT"]
    giro_cabang = giro[giro[cg.cabang_pusat] == "CABANG"]

    df_detail = (
        pd.DataFrame({cg.bank: gd[cg.bank].unique()})
        .merge(
            giro_pusat.groupby(cg.bank, as_index=False)[cg.saldo]
            .sum()
            .rename(columns={cg.saldo: "Giro Pusat"}),
            on=cg.bank,
            how="left",
        )
        .merge(
            giro_cabang.groupby(cg.bank, as_index=False)[cg.saldo]
            .sum()
            .rename(columns={cg.saldo: "Giro Cabang"}),
            on=cg.bank,
            how="left",
        )
        .merge(
            deposito_non.groupby(cg.bank, as_index=False)[cg.saldo]
            .sum()
            .rename(columns={cg.saldo: "Deposito (Non Restricted)"}),
            on=cg.bank,
            how="left",
        )
        .merge(
            kas.groupby(cg.bank, as_index=False)[cg.saldo]
            .sum()
            .rename(columns={cg.saldo: "Kas"}),
            on=cg.bank,
            how="left",
        )
        .fillna(0)
    )

    df_detail["Total"] = (
        df_detail["Giro Pusat"]
        + df_detail["Giro Cabang"]
        + df_detail["Deposito (Non Restricted)"]
        + df_detail["Kas"]
    )

    for col in ["Giro Pusat", "Giro Cabang", "Deposito (Non Restricted)", "Kas", "Total"]:
        df_detail[col] = df_detail[col].apply(round_half_up)

    df_detail = df_detail.sort_values("Total", ascending=False)

    df_detail.loc[len(df_detail)] = [
        "Grand Total",
        df_detail["Giro Pusat"].sum(),
        df_detail["Giro Cabang"].sum(),
        df_detail["Deposito (Non Restricted)"].sum(),
        df_detail["Kas"].sum(),
        df_detail["Total"].sum(),
    ]

    color_map = {
        "BRI": "#0A3185",
        "BSI": "#00A39D",
        "BTN": "#0057B8",
        "BNI": "#F37021",
        "MANDIRI": "#002F6C",
        "CIMB": "#990000",
        "BJB": "#AB9B56",
        "BCA": "#00529B",
        "BANK RAYA": "#00549A",
        "BTN SYARIAH": "#FFC20E",
        "BRI USD": "#0A3185",
        "BCA SYARIAH": "#00979D",
        "KAS": "#D3D3D3",
    }

    pie_data = df_detail[df_detail[cg.bank] != "Grand Total"].copy()
    pie_total = pie_data["Total"].sum()

    if pie_total > 0:
        pie_text = [
            f"{bank}<br>{(value / pie_total) * 100:.1f}%"
            for bank, value in zip(pie_data[cg.bank], pie_data["Total"])
        ]
    else:
        pie_text = [str(bank) for bank in pie_data[cg.bank]]

    fig_pie = go.Figure(
        data=[
            go.Pie(
                labels=pie_data[cg.bank],
                values=pie_data["Total"],
                text=pie_text,
                textinfo="text",
                textposition="outside",
                pull=[0.03] * len(pie_data),
                marker=dict(
                    colors=[color_map.get(bank, "#CCCCCC") for bank in pie_data[cg.bank]]
                ),
                hole=0.35,
            )
        ]
    )

    fig_pie.update_layout(
        height=450,
        margin=dict(l=40, r=40, t=40, b=40),
        showlegend=False,
    )

    col1, col2 = st.columns([1.1, 0.9])

    with col1:
        st.subheader("Cash and Cash Equivalents Details per Bank")
        st.markdown(
            _style_grand_total(df_detail, label_col=cg.bank),
            unsafe_allow_html=True,
        )

    with col2:
        st.subheader("% Cash and Equivalents per Bank (Exclude Restricted)")
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown(
        "<div class='footer-credit'>Created by Nur Vita Anajningrum</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

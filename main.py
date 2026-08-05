import streamlit as st
import pandas as pd
import json
import os
from backend import QAReportWorker, get_available_spreadsheets

# Page Configuration
st.set_page_config(
    page_title="QA Report Automation",
    page_icon="📊",
    layout="wide"
)

st.title("📊 QA Rapor Otomasyonu")
st.markdown("Google Sheets üzerindeki ham veri sekmelerinden performans sayılarını hesaplar ve ana rapora aktarır.")

# ==========================================
# 🔑 CREDENTIALS & SECRETS OTOMATİK TESPİT
# ==========================================

creds_input = None

# 1. Streamlit Secrets İçindeki Tüm Olası Yapıları Tara
if len(st.secrets) > 0:
    # A) Direkt dict / bölüm olarak kayıtlıysa
    for key in ["gcp_service_account", "credentials", "service_account", "gspread"]:
        if key in st.secrets:
            creds_input = dict(st.secrets[key])
            break
    
    # B) Eğer Secrets içine direkt ham JSON string olarak yapıştırıldıysa
    if creds_input is None:
        for key in st.secrets:
            val = st.secrets[key]
            if isinstance(val, str) and "private_key" in val:
                try:
                    creds_input = json.loads(val)
                    break
                except Exception:
                    pass
            elif isinstance(val, dict) and "private_key" in val:
                creds_input = dict(val)
                break

# 2. Yerel Dosya Kontrolü (Eğer Secrets'ta bulunamazsa)
if creds_input is None:
    possible_files = ["credentials.json", "service_account.json", "key.json"]
    for file_name in possible_files:
        if os.path.exists(file_name):
            try:
                with open(file_name, "r", encoding="utf-8") as f:
                    creds_input = json.load(f)
                break
            except Exception:
                pass

# Hata Verip Durdurma
if creds_input is None:
    st.error("❌ Streamlit Secrets içinde geçerli bir Google Service Account anahtarı okunamadı.")
    st.info("💡 Streamlit Secrets panelinde alan adınızın `[gcp_service_account]` veya `[credentials]` olduğundan emin olun.")
    st.stop()

# ==========================================
# 📁 DRIVER / ETABLO SEÇİM ALANI
# ==========================================

st.sidebar.header("⚙️ Ayarlar & Dosya Seçimi")

sheets_data = get_available_spreadsheets(creds_input)
all_sheets = sheets_data.get("all", {})

if "error" in sheets_data:
    st.error(f"❌ Google Drive Bağlantı Hatası: {sheets_data['error']}")
    st.stop()

if not all_sheets:
    st.warning("⚠️ Hesabınıza tanımlı hiç Google Sheets dosyası bulunamadı.")
    st.stop()

sorted_sheet_names = sorted(list(all_sheets.keys()))

selected_source_name = st.sidebar.selectbox(
    "📁 Kaynak (Ham Veri) Dosyası:",
    options=sorted_sheet_names,
    index=0,
    help="İşlemek istediğiniz dilin ham veri tablosunu seçin."
)
source_id = all_sheets[selected_source_name]

selected_report_name = st.sidebar.selectbox(
    "🎯 Hedef (Ana Rapor) Dosyası:",
    options=sorted_sheet_names,
    index=min(1, len(sorted_sheet_names) - 1),
    help="Puanların aktarılacağı ana rapor tablosunu seçin."
)
report_id = all_sheets[selected_report_name]

# ==========================================
# 📅 FİLTRE VE DİL SEÇİMLERİ
# ==========================================

col_lang, col_month, col_year = st.columns(3)

with col_lang:
    selected_lang = st.selectbox(
        "🌐 Dil Filtresi / Tipi:",
        options=["Tümü", "ENG", "POR", "ESP", "TR"],
        index=0
    )

with col_month:
    months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", 
              "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    selected_month = st.selectbox("📅 Ay Seçimi:", options=months, index=6)

with col_year:
    years = [2024, 2025, 2026, 2027]
    selected_year = st.selectbox("📆 Yıl Seçimi:", options=years, index=2)

st.info(
    f"📌 **Seçilen İşlem Detayları:**\n\n"
    f"- **Kaynak Dosya:** `{selected_source_name}` *(ID: {source_id})*\n"
    f"- **Hedef Rapor:** `{selected_report_name}` *(ID: {report_id})*\n"
    f"- **Filtre Dönemi:** {selected_month} {selected_year} | **Dil:** {selected_lang}"
)

# ==========================================
# 🚀 ARAYÜZ CANLI LOG VE ÇALIŞTIRMA
# ==========================================

log_container = st.empty()
log_messages = []

def append_log(message):
    log_messages.append(message)
    log_container.text_area("📋 İşlem Canlı Logları", value="\n".join(log_messages), height=220)

progress_bar = st.progress(0)

def update_progress(val):
    progress_bar.progress(val)

if st.button("🚀 Raporu Çalıştır", type="primary", use_container_width=True):
    log_messages.clear()
    append_log("🔄 İşlem başlatılıyor...")
    
    try:
        worker = QAReportWorker(
            creds_input=creds_input,
            source_id=source_id,
            report_id=report_id,
            selected_lang=selected_lang,
            selected_year=selected_year,
            selected_month=selected_month,
            log_callback=append_log,
            progress_callback=update_progress
        )

        updated_df = worker.process()

        if updated_df is not None and not updated_df.empty:
            st.success("🎉 Rapor verileri hedef tabloya başarıyla yazıldı!")
            st.subheader("📊 Güncellenmiş Hedef Tablo Önizlemesi")
            st.dataframe(updated_df, use_container_width=True)
        else:
            st.warning("⚠️ Seçilen filtrelere uygun veri işlenemedi veya hedef tablo boş döndü.")

    except Exception as e:
        st.error(f"❌ İşlem sırasında bir hata oluştu: {str(e)}")
        append_log(f"❌ HATA: {str(e)}")

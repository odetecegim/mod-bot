import streamlit as st
import pandas as pd
import json
import os
from backend import QAReportWorker, get_available_spreadsheets

st.set_page_config(
    page_title="QA Report Automation",
    page_icon="📊",
    layout="wide"
)

st.title("📊 QA Rapor Otomasyonu")

# ==========================================
# 🔑 AKILLI CREDENTIALS PARSER
# ==========================================

creds_input = None

if hasattr(st, "secrets") and len(st.secrets) > 0:
    target_sec = None
    for k in st.secrets:
        if k.lower() in ["gcp_service_account", "credentials", "service_account"]:
            target_sec = st.secrets[k]
            break
            
    if target_sec:
        c_dict = dict(target_sec)
        required_keys = ["client_id", "auth_uri", "token_uri", "auth_provider_x509_cert_url", "client_x509_cert_url"]
        for r_key in required_keys:
            if r_key not in c_dict and r_key in st.secrets:
                c_dict[r_key] = st.secrets[r_key]
        creds_input = c_dict

if not creds_input:
    for f_name in ["credentials.json", "service_account.json"]:
        if os.path.exists(f_name):
            try:
                with open(f_name, "r", encoding="utf-8") as f:
                    creds_input = json.load(f)
                break
            except Exception:
                pass

if not creds_input:
    st.error("❌ Google Service Account anahtarı okunamadı. Lütfen Secrets yapısını kontrol edin.")
    st.stop()

# ==========================================
# 📁 ETABLO SEÇİM ALANI (ANA EKRAN)
# ==========================================

sheets_data = get_available_spreadsheets(creds_input)
all_sheets = sheets_data.get("all", {})

if "error" in sheets_data:
    st.error(f"❌ Google Drive Bağlantı Hatası: {sheets_data['error']}")
    st.stop()

if not all_sheets:
    st.warning("⚠️ Hesabınıza tanımlı hiç Google Sheets dosyası bulunamadı.")
    st.stop()

sorted_sheet_names = sorted(list(all_sheets.keys()))

st.subheader("⚙️ Dosya Seçimleri")
col_src, col_rep = st.columns(2)

with col_src:
    selected_source_name = st.selectbox(
        "📁 Kaynak (Ham Veri) Dosyası:",
        options=sorted_sheet_names,
        index=0,
        help="İşlenecek veri tablosunu seçin (Örn: Error Reporting ENG, POR, ESP)"
    )
    source_id = all_sheets[selected_source_name]

with col_rep:
    default_rep_idx = 1 if len(sorted_sheet_names) > 1 else 0
    selected_report_name = st.selectbox(
        "🎯 Hedef (Ana Konsolide Rapor) Dosyası:",
        options=sorted_sheet_names,
        index=default_rep_idx,
        help="Puanların yazılacağı ANA Konsolide Rapor dosyasını seçin."
    )
    report_id = all_sheets[selected_report_name]

# ==========================================
# 📅 FİLTRE VE DİL SEÇİMLERİ (Sadece ENG, POR, ESP)
# ==========================================

col_lang, col_month, col_year = st.columns(3)

with col_lang:
    selected_lang = st.selectbox(
        "🌐 Dil Filtresi / Tipi:", 
        options=["Tümü", "ENG", "POR", "ESP"], 
        index=0
    )

with col_month:
    months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    selected_month = st.selectbox("📅 Ay Seçimi:", options=months, index=6)

with col_year:
    years = [2024, 2025, 2026, 2027]
    selected_year = st.selectbox("📆 Yıl Seçimi:", options=years, index=2)

st.markdown("---")

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

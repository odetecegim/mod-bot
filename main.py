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
# 📁 ETABLO SEÇİM ALANI (FİLTRELENMİŞ LISTELER)
# ==========================================

sheets_data = get_available_spreadsheets(creds_input)
all_sheets = sheets_data.get("all", {})

if "error" in sheets_data:
    st.error(f"❌ Google Drive Bağlantı Hatası: {sheets_data['error']}")
    st.stop()

if not all_sheets:
    st.warning("⚠️ Hesabınıza tanımlı hiç Google Sheets dosyası bulunamadı.")
    st.stop()

# 1. Kaynak (Ham Veri) Listesi: "Global Perf Tablosu" ve log dosyalarını filtrele
filtered_source_sheets = {
    name: sid for name, sid in all_sheets.items()
    if "global perf" not in name.lower() and not name.lower().endswith(".log") and "modbot" not in name.lower()
}
sorted_source_names = sorted(list(filtered_source_sheets.keys()))

# 2. Hedef (Konsolide Rapor) Listesi: Sadece "Global Perf Tablosu" kalsın
filtered_report_sheets = {
    name: sid for name, sid in all_sheets.items()
    if "global perf" in name.lower()
}
sorted_report_names = sorted(list(filtered_report_sheets.keys()))

# Eğer listede bulunamazsa güvenlik önlemi
if not sorted_report_names:
    sorted_report_names = sorted(list(all_sheets.keys()))
    filtered_report_sheets = all_sheets

st.subheader("⚙️ Dosya Seçimleri")
col_src, col_rep = st.columns(2)

with col_src:
    selected_source_name = st.selectbox(
        "📁 Kaynak (Ham Veri) Dosyası:",
        options=sorted_source_names,
        index=0 if sorted_source_names else 0,
        help="İşlenecek ham veri tablosunu seçin."
    )
    source_id = filtered_source_sheets.get(selected_source_name, "")

with col_rep:
    selected_report_name = st.selectbox(
        "🎯 Hedef (Ana Konsolide Rapor) Dosyası:",
        options=sorted_report_names,
        index=0,
        help="Puanların yazılacağı Global Perf Tablosu dosyasını seçin."
    )
    report_id = filtered_report_sheets.get(selected_report_name, "")

# ==========================================
# 📅 TARIH SEÇİMLERİ (DİL SEÇENEĞİ KALDIRILDI)
# ==========================================

col_month, col_year = st.columns(2)

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
            selected_lang="Tümü",  # Dil paneli kaldırıldığı için otomatik "Tümü" gönderiliyor
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

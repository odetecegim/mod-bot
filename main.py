import streamlit as st
import pandas as pd
import json
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
# 🔑 CREDENTIALS & SESSIONS SETUP
# ==========================================

# Streamlit secrets veya yerel dosya üzerinden kimlik doğrulama
if "gcp_service_account" in st.secrets:
    creds_input = dict(st.secrets["gcp_service_account"])
else:
    try:
        with open("credentials.json", "r", encoding="utf-8") as f:
            creds_input = json.load(f)
    except Exception as e:
        st.error("❌ `credentials.json` dosyası veya Streamlit Secrets bulunamadı!")
        st.stop()

# ==========================================
# 📁 DRIVER / ETABLO SEÇİM ALANI
# ==========================================

st.sidebar.header("⚙️ Ayarlar & Dosya Seçimi")

# Drive üzerindeki tüm erişilebilir Google Sheets listesini alıyoruz
sheets_data = get_available_spreadsheets(creds_input)
all_sheets = sheets_data.get("all", {})

if "error" in sheets_data:
    st.error(f"❌ Google Drive Bağlantı Hatası: {sheets_data['error']}")
    st.stop()

if not all_sheets:
    st.warning("⚠️ Hesabınıza tanımlı hiç Google Sheets dosyası bulunamadı.")
    st.stop()

# Dosya adlarını alfabetik sıralıyoruz
sorted_sheet_names = sorted(list(all_sheets.keys()))

# 1. Kaynak Tablo Seçimi (ENG / POR / ESP / TR Ham Veri Dosyası)
selected_source_name = st.sidebar.selectbox(
    "📁 Kaynak (Ham Veri) Dosyası:",
    options=sorted_sheet_names,
    index=0,
    help="İşlemek istediğiniz dilin (ENG, POR, ESP, TR) ham veri tablosunu seçin."
)
source_id = all_sheets[selected_source_name]

# 2. Hedef Rapor Tablosu Seçimi (Verilerin aktarılacağı ana tablo)
selected_report_name = st.sidebar.selectbox(
    "🎯 Hedef (Ana Rapor) Dosyası:",
    options=sorted_sheet_names,
    index=min(1, len(sorted_sheet_names) - 1),
    help="Puanların aktarılacağı ana konsolide rapor tablosunu seçin."
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
        index=0,
        help="'Tümü' seçeneği sekme ismindeki tüm dilleri otomatik algılar."
    )

with col_month:
    months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", 
              "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    selected_month = st.selectbox("📅 Ay Seçimi:", options=months, index=6) # Temmuz Varsayılan

with col_year:
    years = [2024, 2025, 2026, 2027]
    selected_year = st.selectbox("📆 Yıl Seçimi:", options=years, index=2) # 2026 Varsayılan

# ==========================================
# 📌 SEÇİM TEYİT KUTUSU
# ==========================================

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

        # İşlemi başlat ve güncellenmiş tabloyu al
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

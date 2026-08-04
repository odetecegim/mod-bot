import os
import json
import streamlit as st
from backend import QAReportWorker, get_available_spreadsheets

# Sayfa Yapılandırması
st.set_page_config(
    page_title="QA Raporlama Paneli",
    page_icon="📊",
    layout="centered"
)

st.title("📊 QA Görev Raporlama Paneli")
st.caption("Google Sheets verilerini seçilen Ay ve Yıl'a göre otomatik eşleştirin ve güncelleyin.")

# --- GOOGLE CREDENTIALS YÖNETİMİ ---
JSON_PATH = "credentials.json"

@st.cache_resource
def setup_credentials():
    # 1. Streamlit Cloud Secrets Kontrolü
    if "GOOGLE_CREDENTIALS" in st.secrets:
        try:
            creds_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])
            
            # PEM Hatasını Çözen Kısım: \n karakterlerini gerçek alt satıra dönüştürür
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                
            with open("temp_credentials.json", "w", encoding="utf-8") as f:
                json.dump(creds_dict, f)
            return "temp_credentials.json"
        except Exception as e:
            st.error(f"Secrets okunurken hata oluştu: {e}")
            return None
            
    # 2. Yerel Dosya Kontrolü
    elif os.path.exists(JSON_PATH):
        return JSON_PATH
    else:
        return None

active_json_path = setup_credentials()

if not active_json_path:
    st.error("❌ Google bağlantı bilgileri yüklenemedi! Lütfen Secrets ayarlarını kontrol edin.")
    st.stop()

# --- TABLOLARI LİSTELE ---
try:
    spreadsheet_dict = get_available_spreadsheets(active_json_path)
    sheet_names = list(spreadsheet_dict.keys())
except Exception as e:
    st.error(f"Google Drive bağlantı hatası: {e}")
    st.stop()

# --- FORM ARAYÜZÜ ---
with st.form("qa_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        source_name = st.selectbox("Kaynak Tablo (Source Sheet)", options=sheet_names)
    with col2:
        report_name = st.selectbox("Rapor Tablosu (Report Sheet)", options=sheet_names)

    col3, col4, col5 = st.columns(3)
    
    with col3:
        selected_lang = st.selectbox("Dil", ["Tümü", "ENG", "ESP", "POR", "TR"])
    with col4:
        months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        selected_month = st.selectbox("Ay", months, index=6) # Varsayılan: Temmuz
    with col5:
        selected_year = st.selectbox("Yıl", ["2025", "2026", "2027"], index=1)

    submit_button = st.form_submit_button("🚀 Raporu Güncelle", use_container_width=True)

# --- İŞLEM BAŞLATMA VE LOG EKRANI ---
if submit_button:
    source_id = spreadsheet_dict[source_name]
    report_id = spreadsheet_dict[report_name]

    progress_bar = st.progress(0)
    log_box = st.code("> İşlem başlatıldı...\n", language="bash")

    logs_list = []

    def log_callback(msg):
        logs_list.append(f"> {msg}")
        log_box.code("\n".join(logs_list), language="bash")

    def progress_callback(val):
        progress_bar.progress(val)

    try:
        worker = QAReportWorker(
            json_path=active_json_path,
            source_id=source_id,
            report_id=report_id,
            selected_lang=selected_lang,
            selected_year=selected_year,
            selected_month=selected_month,
            log_callback=log_callback,
            progress_callback=progress_callback
        )
        worker.process()
        st.success("✅ Rapor başarıyla güncellendi!")
    except Exception as e:
        st.error(f"❌ İşlem sırasında bir hata oluştu: {str(e)}")

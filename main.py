import os
import json
import streamlit as st
from backend import QAReportWorker, get_available_spreadsheets

st.set_page_config(
    page_title="QA Raporlama Paneli",
    page_icon="📊",
    layout="centered"
)

st.title("📊 QA Görev Raporlama Paneli")
st.caption("Google Sheets verilerini seçilen Ay ve Yıl'a göre otomatik eşleştirin ve güncelleyin.")

# --- GOOGLE CREDENTIALS YÖNETİMİ ---
@st.cache_resource
def get_credentials():
    if "GOOGLE_CREDENTIALS" in st.secrets:
        # Streamlit secrets TOML objesini düzgün dictionary'e dönüştür
        creds = dict(st.secrets["GOOGLE_CREDENTIALS"])
        
        # Private key format düzeltmesi
        if "private_key" in creds:
            pk = creds["private_key"]
            # Çift kaçış karakterlerini ve hatalı tırnakları temizle
            pk = pk.replace("\\n", "\n").strip()
            if pk.startswith('"') and pk.endswith('"'):
                pk = pk[1:-1]
            creds["private_key"] = pk
            
        return creds
    elif os.path.exists("credentials.json"):
        return "credentials.json"
    else:
        return None

creds_input = get_credentials()

if not creds_input:
    st.error("❌ Google bağlantı bilgileri bulunamadı! Lütfen Streamlit Secrets ayarlarını kontrol edin.")
    st.stop()

# --- TABLOLARI LİSTELE ---
try:
    spreadsheet_dict = get_available_spreadsheets(creds_input)
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
        selected_month = st.selectbox("Ay", months, index=6)
    with col5:
        selected_year = st.selectbox("Yıl", ["2025", "2026", "2027"], index=1)

    submit_button = st.form_submit_button("🚀 Raporu Güncelle", use_container_width=True)

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
            creds_input=creds_input,
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

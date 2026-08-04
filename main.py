import streamlit as st
import datetime
from backend import QAReportWorker, get_available_spreadsheets

st.set_page_config(page_title="Rapor Eşleştirme Paneli", layout="wide")

st.title("📊 QA Raporu Otomatik İşleme Paneli")
st.caption("Google Sheets verilerini seçilen Dil, Ay ve Yıl'a göre tam eşleşmeyle güncelleyin.")

# Creds / Bağlantı Yükleme (Streamlit Secrets veya Local credentials.json)
creds_data = st.secrets["gcp_service_account"] if "gcp_service_account" in st.secrets else "credentials.json"

# Tabloları Çek
sheets_dict = get_available_spreadsheets(creds_data)

# Hata Kontrolü ve Detaylı Bilgilendirme
if "error" in sheets_dict:
    st.error(f"❌ Google Sheets Bağlantı Hatası: {sheets_dict['error']}")
    st.info("💡 Lütfen `credentials.json` dosyanızı veya Streamlit Secrets (`[gcp_service_account]`) ayarlarınızı kontrol edin.")
    st.stop()

all_options = list(sheets_dict.get("all", {}).keys())

if not all_options:
    st.warning("⚠️ Google Sheets bağlantısı başarılı fakat erişilebilen hiç tablo bulunamadı.")
    st.info("💡 Lütfen işlem yapacağınız Google Sheets tablolarını Service Account e-postanız ile **Paylaş (Share)** kısmından Düzenleyen (Editor) olarak paylaşın.")
    st.stop()

# Dil Sekmeleri Paneli
tab_eng, tab_por, tab_esp, tab_tr = st.tabs([
    "🇬🇧 ENG Raporu", 
    "🇵🇹 POR Raporu", 
    "🇪🇸 ESP Raporu", 
    "🇹🇷 TR Raporu"
])

MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
YEARS = [2024, 2025, 2026, 2027]

def render_language_panel(lang_code):
    col1, col2 = st.columns(2)
    
    # Varsayılan tablo seçimi
    default_src = next((s for s in all_options if lang_code in s.upper()), all_options[0])
    default_rep = next((s for s in all_options if "PERF" in s.upper() or "GLOBAL" in s.upper()), all_options[0])

    with col1:
        source_name = st.selectbox(
            f"Kaynak Tablo ({lang_code})", 
            all_options, 
            index=all_options.index(default_src),
            key=f"src_{lang_code}"
        )
    with col2:
        report_name = st.selectbox(
            f"Rapor Tablosu ({lang_code})", 
            all_options, 
            index=all_options.index(default_rep),
            key=f"rep_{lang_code}"
        )

    col3, col4 = st.columns(2)
    with col3:
        selected_month = st.selectbox("Ay", MONTHS, index=6, key=f"month_{lang_code}") # Temmuz
    with col4:
        selected_year = st.selectbox("Yıl", YEARS, index=2, key=f"year_{lang_code}")   # 2026

    if st.button(f"🚀 {lang_code} Raporunu Güncelle", use_container_width=True, key=f"btn_{lang_code}"):
        source_id = sheets_dict["all"][source_name]
        report_id = sheets_dict["all"][report_name]

        log_container = st.empty()
        progress_bar = st.progress(0)

        logs = []
        def append_log(msg):
            logs.append(msg)
            log_container.code("\n".join(logs), language="bash")

        def update_progress(val):
            progress_bar.progress(val)

        worker = QAReportWorker(
            creds_input=creds_data,
            source_id=source_id,
            report_id=report_id,
            selected_lang=lang_code,
            selected_year=selected_year,
            selected_month=selected_month,
            log_callback=append_log,
            progress_callback=update_progress
        )

        try:
            worker.process()
            st.success(f"✅ {lang_code} işlemi tamamlandı!")
        except Exception as e:
            st.error(f"❌ İşlem sırasında hata oluştu: {str(e)}")

with tab_eng:
    render_language_panel("ENG")

with tab_por:
    render_language_panel("POR")

with tab_esp:
    render_language_panel("ESP")

with tab_tr:
    render_language_panel("TR")

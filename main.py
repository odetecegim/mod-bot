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
# 🔑 ADVANCED CREDENTIALS / SECRETS PARSER
# ==========================================

creds_input = None

def parse_dict_or_json(val):
    """Gelen veriyi dict'e çevirmeye çalışır."""
    if isinstance(val, dict):
        return val
    elif isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            # Tırnaklar veya escape karakterleri bozuksa temizlemeyi dener
            try:
                clean_str = val.replace("'", '"')
                return json.loads(clean_str)
            except Exception:
                pass
    return None

# 1. Streamlit Secrets Kontrolü
if hasattr(st, "secrets") and len(st.secrets) > 0:
    # A) Doğrudan bilinen anahtarlara bak
    for k in ["gcp_service_account", "credentials", "service_account", "gspread"]:
        if k in st.secrets:
            creds_input = parse_dict_or_json(st.secrets[k])
            if creds_input:
                break
    
    # B) Anahtar ismi farklıysa secrets içindeki tüm değerleri tara
    if not creds_input:
        for k in st.secrets:
            parsed = parse_dict_or_json(st.secrets[k])
            if parsed and isinstance(parsed, dict) and "private_key" in parsed:
                creds_input = parsed
                break

    # C) Secrets kök dizininde tanımlanmışsa (Sekmesiz TOML)
    if not creds_input and "private_key" in st.secrets:
        creds_input = dict(st.secrets)

# 2. Yerel Dosya Kontrolü (Secrets çalışmazsa)
if not creds_input:
    for file_name in ["credentials.json", "service_account.json", "key.json"]:
        if os.path.exists(file_name):
            try:
                with open(file_name, "r", encoding="utf-8") as f:
                    creds_input = json.load(f)
                break
            except Exception:
                pass

# Hata Verip Durdurma
if not creds_input:
    st.error("❌ Google Service Account anahtarı okunamadı.")
    
    # Hata Tespiti İçin Arayüzde Mevcut Keys Gösterimi
    st.warning("🔍 **Mevcut Secrets Anahtarları:**")
    if hasattr(st, "secrets") and len(st.secrets) > 0:
        st.json(list(st.secrets.keys()))
    else:
        st.write("`st.secrets` tamamen boş görünüyor.")

    st.info(
        "💡 **Çözüm:**\n"
        "1. Streamlit Cloud panelinde **Settings -> Secrets** sekmesini açın.\n"
        "2. Yukarıdaki **1. Yöntemde** verilen TOML formatında `[gcp_service_account]` başlığıyla bilgilerinizi yapıştırın ve **Save** butonuna basın."
    )
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
    index=0
)
source_id = all_sheets[selected_source_name]

selected_report_name = st.sidebar.selectbox(
    "🎯 Hedef (Ana Rapor) Dosyası:",
    options=sorted_sheet_names,
    index=min(1, len(sorted_sheet_names) - 1)
)
report_id = all_sheets[selected_report_name]

# ==========================================
# 📅 FİLTRE VE DİL SEÇİMLERİ
# ==========================================

col_lang, col_month, col_year = st.columns(3)

with col_lang:
    selected_lang = st.selectbox("🌐 Dil Filtresi / Tipi:", options=["Tümü", "ENG", "POR", "ESP", "TR"], index=0)

with col_month:
    months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
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
        append_log(f"❌ HATA: {str(e)}")# ==========================================

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

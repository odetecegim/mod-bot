import os
import json
import base64
import time
from datetime import datetime
import pandas as pd
import streamlit as st
from backend import QAReportWorker, get_available_spreadsheets

# 1 Saat = 3600 Saniye
ONE_HOUR_SECONDS = 3600
LOG_FILE_PATH = "app_audit_logs.json"

# Sayfa Yapılandırması
st.set_page_config(
    page_title="QA Control Center — Yönetim Paneli",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- LOGLAMA / AUDIT LOG FONKSİYONLARI ---
def load_audit_logs():
    """Geçmiş işlem loglarını okur."""
    if os.path.exists(LOG_FILE_PATH):
        try:
            with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_audit_log(entry):
    """Yeni yapılan işlemi log dosyasına kaydeder."""
    logs = load_audit_logs()
    logs.insert(0, entry) # En son yapılan işlemi en başa ekle
    try:
        with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(logs[:100], f, ensure_ascii=False, indent=2) # Son 100 kaydı tut
    except Exception as e:
        print(f"Log yazma hatası: {e}")

# --- OTURUM VE ZAMAN AŞIMI YÖNETİMİ ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if "login_time" not in st.session_state:
    st.session_state["login_time"] = None

if "login_date" not in st.session_state:
    st.session_state["login_date"] = None

def check_session_timeout():
    """1 saatlik ve Gece Yarısı (00:00) otomatik oturum kapatma kontrolü."""
    if st.session_state["authenticated"] and st.session_state["login_time"] is not None:
        now = time.time()
        current_date = datetime.now().date()
        
        # Her gece saat 00:00 sonrası otomatik çıkış
        if st.session_state["login_date"] is not None and current_date != st.session_state["login_date"]:
            st.session_state["authenticated"] = False
            st.session_state["login_time"] = None
            st.session_state["login_date"] = None
            st.warning("⚠️ Gece yarısı (00:00) olduğu için oturumunuz otomatik kapatıldı.")
            return

        # 1 Saatlik zaman aşımı kontrolü
        elapsed = now - st.session_state["login_time"]
        if elapsed > ONE_HOUR_SECONDS:
            st.session_state["authenticated"] = False
            st.session_state["login_time"] = None
            st.session_state["login_date"] = None
            st.warning("⚠️ Oturum süreniz (1 saat) dolduğu için kilit ekranına yönlendirildiniz.")

check_session_timeout()

# --- GİRİŞ EKRANI (ZULA TEMALI) ---
def login_screen():
    zula_logo_url = "https://upload.wikimedia.org/wikipedia/commons/9/91/Zula_New_LOGO_VECTOR.png"

    st.markdown(f"""
        <style>
            .stApp {{
                background: radial-gradient(circle at center, #2a2d34 0%, #121316 60%, #08080a 100%) !important;
            }}
            html, body, [data-testid="stAppViewContainer"] {{
                height: 100vh;
                margin: 0;
                padding: 0;
            }}
            .main .block-container {{
                padding-top: 0rem !important;
                padding-bottom: 0rem !important;
                max-width: 440px !important;
                height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: flex-end;
                padding-bottom: 10vh !important;
                position: relative;
            }}
            .main .block-container::before {{
                content: "";
                position: absolute;
                top: 28%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 360px;
                height: 180px;
                background-image: url('{zula_logo_url}');
                background-size: contain;
                background-repeat: no-repeat;
                background-position: center;
                opacity: 0.9;
                filter: drop-shadow(0 0 25px rgba(245, 158, 11, 0.4));
                pointer-events: none;
                z-index: 0;
            }}
            div[data-testid="stForm"] {{
                position: relative;
                z-index: 1;
                background: rgba(18, 20, 26, 0.85) !important;
                border: 1px solid rgba(255, 255, 255, 0.12) !important;
                border-radius: 20px !important;
                padding: 2.2rem 2rem !important;
                box-shadow: 0 25px 50px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
                backdrop-filter: blur(12px);
                margin-top: 22vh !important;
            }}
            label {{
                color: #f1f5f9 !important;
                font-size: 12px !important;
                font-weight: 600 !important;
                margin-bottom: 6px !important;
            }}
            div[data-baseweb="input"] {{
                background-color: rgba(10, 11, 15, 0.85) !important;
                border: 1px solid rgba(255, 255, 255, 0.15) !important;
                border-radius: 12px !important;
                color: #ffffff !important;
            }}
            div[data-testid="stFormSubmitButton"] > button {{
                background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%) !important;
                color: #ffffff !important;
                border: none !important;
                border-radius: 12px !important;
                height: 48px !important;
                font-weight: 700 !important;
                font-size: 15px !important;
                box-shadow: 0 8px 20px rgba(245, 158, 11, 0.35) !important;
                margin-top: 10px !important;
            }}
            .footer-text {{
                position: relative;
                z-index: 1;
                text-align: center;
                font-size: 12px;
                color: #94a3b8;
                margin-top: 1rem;
            }}
        </style>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        password_input = st.text_input("GİRİŞ ŞİFRESİ", type="password", placeholder="••••••••••••")
        submit = st.form_submit_button("Sisteme Giriş Yap →", use_container_width=True)

        if submit:
            admin_pass = st.secrets.get("ADMIN_PASSWORD", "akademi2026")
            if password_input == admin_pass:
                st.session_state["authenticated"] = True
                st.session_state["login_time"] = time.time()
                st.session_state["login_date"] = datetime.now().date()
                st.rerun()
            else:
                st.error("❌ Hatalı Şifre! Lütfen tekrar deneyin.")

    st.markdown('<div class="footer-text">🔒 Oturum süresi: <strong>1 Saat / Gece 00:00 Çıkışlı</strong></div>', unsafe_allow_html=True)

if not st.session_state.get("authenticated", False):
    login_screen()
    st.stop()

# ==============================================================================
# === GİRİŞ YAPILDIKTAN SONRA GÖRÜNECEK ANA PANEL ===
# ==============================================================================

col_title, col_logout = st.columns([4, 1])

with col_title:
    login_time = st.session_state.get("login_time")
    if login_time is not None:
        elapsed_time = time.time() - login_time
        remaining_min = max(0, int((ONE_HOUR_SECONDS - elapsed_time) / 60))
        st.caption(f"⏱️ Oturum Süresi: Kalan ~**{remaining_min} dakika** (Her gece 00:00'da sıfırlanır)")

with col_logout:
    if st.button("🚪 Çıkış Yap", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state["login_time"] = None
        st.session_state["login_date"] = None
        st.rerun()

st.title("📊 QA Görev Raporlama ve Otomasyon Paneli")
st.caption("Google Sheets verilerini otomatik eşleştirin, rapor oluşturun ve sistem geçmişini takip edin.")

# --- GOOGLE CREDENTIALS YÖNETİMİ ---
@st.cache_resource
def get_credentials():
    sec_key = None
    for k in ["gcp_service_account", "GCP_SERVICE_ACCOUNT", "GOOGLE_CREDENTIALS", "google_credentials"]:
        if k in st.secrets:
            sec_key = k
            break

    if sec_key:
        try:
            sec = st.secrets[sec_key]
            if isinstance(sec, (dict, st.runtime.secrets.AttrDict)):
                creds = dict(sec)
            elif isinstance(sec, str):
                try:
                    decoded = base64.b64decode(sec).decode('utf-8')
                    creds = json.loads(decoded)
                except Exception:
                    creds = json.loads(sec)
            else:
                creds = dict(sec)

            if "private_key" in creds:
                pk = str(creds["private_key"])
                pk = pk.replace("\\n", "\n").strip()
                if pk.startswith('"') and pk.endswith('"'):
                    pk = pk[1:-1]
                creds["private_key"] = pk
                
            return creds
        except Exception as e:
            st.error(f"Secrets okuma hatası: {e}")
            return None
    elif os.path.exists("credentials.json"):
        return "credentials.json"
    else:
        return None

creds_input = get_credentials()

if not creds_input:
    st.error("❌ Google bağlantı bilgileri bulunamadı! Lütfen Streamlit Secrets ayarlarınızı kontrol edin.")
    st.stop()

# --- TABLOLARI LİSTELE VE AYRIŞTIR ---
try:
    sheets_data = get_available_spreadsheets(creds_input)
    
    if "error" in sheets_data:
        st.error(f"❌ Google Sheets Bağlantı Hatası: {sheets_data['error']}")
        st.stop()

    source_sheets_dict = sheets_data.get("source", sheets_data.get("all", {}))
    report_sheets_dict = sheets_data.get("report", sheets_data.get("all", {}))
    
    # 1. KAYNAK TABLO
    filtered_source_dict = {
        name: sheet_id for name, sheet_id in source_sheets_dict.items()
        if "global perf" not in name.lower()
    }
    source_sheets_dict = filtered_source_dict
    source_options = list(source_sheets_dict.keys())
    
    # 2. RAPOR TABLOSU (Global Perf)
    filtered_report_dict = {
        name: sheet_id for name, sheet_id in report_sheets_dict.items()
        if "global perf" in name.lower()
    }

    if filtered_report_dict:
        report_sheets_dict = filtered_report_dict
        report_options = list(report_sheets_dict.keys())
    else:
        report_options = [k for k in report_sheets_dict.keys() if "global perf" in k.lower()]
        if not report_options and list(report_sheets_dict.keys()):
            report_options = [list(report_sheets_dict.keys())[0]]

    if not source_options:
        st.warning("⚠️ Erişilebilir Kaynak Sheet bulunamadı (Tümü filtrelenmiş veya yetki eksik).")
        st.stop()

except Exception as e:
    st.error(f"Google Drive bağlantı hatası: {e}")
    st.stop()

# --- DİNAMİK ZAMAN VE HESAPLAMALAR (OTOMATİK AY VE YIL SEÇİMİ) ---
months_list = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
now_dt = datetime.now()

# Bulunduğumuz Ay ve Yıl Otomatik Tespiti
default_month_idx = now_dt.month - 1  # 0-indexed
current_year = now_dt.year

# Bulunduğumuz yıldan başlayarak dinamik yıl listesi (Örn: [2025, 2026, 2027, 2028, 2029])
years_list = [str(y) for y in range(max(2025, current_year - 1), current_year + 4)]
default_year_idx = years_list.index(str(current_year)) if str(current_year) in years_list else 0

# --- FORM VE BUTON HIZLI BAĞLANTILARI ---
st.subheader("🛠️ Rapor Oluşturma Parametreleri")

with st.form("qa_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        source_name = st.selectbox("Kaynak Tablo (Source Sheet)", options=source_options)
    with col2:
        report_name = st.selectbox("Rapor Tablosu (Report Sheet)", options=report_options)

    col3, col4, col5 = st.columns(3)
    
    with col3:
        selected_lang = st.selectbox("Dil Filtresi", ["Tümü", "ENG", "ESP", "POR"])
    with col4:
        selected_month = st.selectbox("İşlenecek Ay", months_list, index=default_month_idx)
    with col5:
        selected_year = st.selectbox("İşlenecek Yıl", years_list, index=default_year_idx)

    submit_button = st.form_submit_button("🚀 Raporu Çalıştır ve Güncelle", use_container_width=True)

# Seçili Tablo Hızlı Erişim Bağlantıları
source_id = source_sheets_dict.get(source_name)
report_id = report_sheets_dict.get(report_name)

col_link1, col_link2 = st.columns(2)
with col_link1:
    if source_id:
        st.markdown(f"🔗 [📄 Kaynak Sheet'e Git (Google Drive)](https://docs.google.com/spreadsheets/d/{source_id})")
with col_link2:
    if report_id:
        st.markdown(f"🔗 [📊 Global Perf Sheet'e Git (Google Drive)](https://docs.google.com/spreadsheets/d/{report_id})")

st.divider()

# --- İŞLEM BAŞLATMA VE LOG EKRANI ---
if submit_button:
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
        
        # Raporu İşle
        updated_data = worker.process()
        
        # Başarılı İşlem Kaydı (Audit Log)
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user": "Admin",
            "source_table": source_name,
            "report_table": report_name,
            "month": selected_month,
            "year": selected_year,
            "lang": selected_lang,
            "status": "Başarılı ✅"
        }
        save_audit_log(log_entry)
        
        st.success("✅ Rapor başarıyla güncellendi ve sisteme kaydedildi!")
        
        # Rapor Önizleme Ekranı
        st.subheader("👁️ Güncellenen Raporun Canlı Önizlemesi")
        if updated_data is not None and isinstance(updated_data, pd.DataFrame):
            st.dataframe(updated_data, use_container_width=True)
        elif updated_data is not None and isinstance(updated_data, list):
            st.dataframe(pd.DataFrame(updated_data), use_container_width=True)
        else:
            st.info("İşlenen veri özet olarak Global Perf tablosuna aktarıldı. Yukarıdaki bağlantıdan kontrol edebilirsiniz.")

    except Exception as e:
        # Hatalı İşlem Kaydı (Audit Log)
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user": "Admin",
            "source_table": source_name,
            "report_table": report_name,
            "month": selected_month,
            "year": selected_year,
            "lang": selected_lang,
            "status": f"Hata ❌ ({str(e)})"
        }
        save_audit_log(log_entry)
        st.error(f"❌ İşlem sırasında bir hata oluştu: {str(e)}")

# --- SİSTEM GEÇMİŞİ VE AUDIT LOG TABLOSU ---
st.subheader("📜 Raporlama ve İşlem Geçmişi (Audit Logs)")
audit_data = load_audit_logs()

if audit_data:
    df_logs = pd.DataFrame(audit_data)
    df_logs.columns = ["Tarih / Saat", "Kullanıcı", "Kaynak Tablo", "Rapor Tablosu", "Ay", "Yıl", "Dil", "Durum"]
    st.dataframe(df_logs, use_container_width=True, hide_index=True)
else:
    st.caption("Henüz kayıtlı bir işlem geçmişi bulunmuyor.")

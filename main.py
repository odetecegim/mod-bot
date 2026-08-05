import os
import json
import base64
import time
from datetime import datetime
import pandas as pd
import streamlit as st
import gspread
from backend import QAReportWorker, get_available_spreadsheets

# 1 Saat = 3600 Saniye
ONE_HOUR_SECONDS = 3600
LOG_SHEET_NAME = "ModBot.log"

# Sayfa Yapılandırması
st.set_page_config(
    page_title="Zula Raporlama Paneli",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

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

# --- GOOGLE SHEETS "ModBot.log" DOSYASINA LOG YAZMA ---
def append_log_to_google_sheet(creds, status, details):
    """Log kayıtlarını ModBot.log Google Sheet dosyasına her zaman A sütunundan başlayarak işler."""
    try:
        if isinstance(creds, str):
            gc = gspread.service_account(filename=creds)
        else:
            gc = gspread.service_account_from_dict(creds)

        try:
            sh = gc.open(LOG_SHEET_NAME)
        except gspread.exceptions.SpreadsheetNotFound:
            sh = gc.create(LOG_SHEET_NAME)

        ws = sh.sheet1
        all_vals = ws.get_all_values()

        headers = [
            "Tarih / Saat", 
            "İşlemi Yapan Kullanıcı", 
            "Kaynak Tablo", 
            "Rapor Tablosu", 
            "Ay", 
            "Yıl", 
            "Durum", 
            "Hata Detayı"
        ]

        # Başlık yoksa ekle
        if len(all_vals) == 0:
            ws.update(range_name='A1', values=[headers])
            next_row = 2
        else:
            next_row = len(all_vals) + 1

        # Parametrelerin güvenli dönüştürülmesi
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_name = details.get("user") or st.session_state.get("current_user") or "Bilinmeyen Kullanıcı"
        source_val = str(details.get("source") or "-")
        report_val = str(details.get("report") or "-")
        month_val = str(details.get("month") or "-")
        year_val = str(details.get("year") or "-")
        error_msg = str(details.get("error") or "")

        row = [
            timestamp,   # A: Tarih / Saat
            user_name,   # B: İşlemi Yapan Kullanıcı
            source_val,  # C: Kaynak Tablo
            report_val,  # D: Rapor Tablosu
            month_val,   # E: Ay
            year_val,    # F: Yıl
            status,      # G: Durum
            error_msg    # H: Hata Detayı
        ]

        # Doğrudan A sütunundaki ilgili satıra yazar (A:H aralığı)
        ws.update(range_name=f'A{next_row}:H{next_row}', values=[row], value_input_option="USER_ENTERED")

    except Exception as e:
        print(f"Google Sheet Log Yazma Hatası: {e}")
# --- OTURUM VE ZAMAN AŞIMI YÖNETİMİ ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if "current_user" not in st.session_state:
    st.session_state["current_user"] = None

if "login_time" not in st.session_state:
    st.session_state["login_time"] = None

if "login_date" not in st.session_state:
    st.session_state["login_date"] = None

def check_session_timeout():
    if st.session_state["authenticated"] and st.session_state["login_time"] is not None:
        now = time.time()
        current_date = datetime.now().date()
        
        if st.session_state["login_date"] is not None and current_date != st.session_state["login_date"]:
            st.session_state["authenticated"] = False
            st.session_state["current_user"] = None
            st.session_state["login_time"] = None
            st.session_state["login_date"] = None
            st.warning("⚠️ Gece yarısı (00:00) olduğu için oturumunuz otomatik kapatıldı.")
            return

        elapsed = now - st.session_state["login_time"]
        if elapsed > ONE_HOUR_SECONDS:
            st.session_state["authenticated"] = False
            st.session_state["current_user"] = None
            st.session_state["login_time"] = None
            st.session_state["login_date"] = None
            st.warning("⚠️ Oturum süreniz (1 saat) dolduğu için kilit ekranına yönlendirildiniz.")

check_session_timeout()

# --- SADECE ŞİFRE İLE GİRİŞ EKRANI (Gömülü SVG Logolu) ---
def login_screen():
    st.markdown("""
        <style>
            .stApp {
                background: radial-gradient(circle at center, #2a2d34 0%, #121316 60%, #08080a 100%) !important;
            }
            div[data-testid="stForm"] {
                background: rgba(18, 20, 26, 0.95) !important;
                border: 1px solid rgba(255, 255, 255, 0.15) !important;
                border-radius: 16px !important;
                padding: 2rem 1.5rem !important;
                box-shadow: 0 20px 40px rgba(0,0,0,0.8) !important;
            }
            label {
                color: #f1f5f9 !important;
                font-size: 13px !important;
                font-weight: 600 !important;
            }
            div[data-baseweb="input"] {
                background-color: rgba(10, 11, 15, 0.9) !important;
                border: 1px solid rgba(255, 255, 255, 0.2) !important;
                border-radius: 10px !important;
                color: #ffffff !important;
            }
            div[data-testid="stFormSubmitButton"] > button {
                background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%) !important;
                color: #ffffff !important;
                border: none !important;
                border-radius: 10px !important;
                height: 45px !important;
                font-weight: 700 !important;
                font-size: 14px !important;
                margin-top: 10px !important;
            }
            .footer-text {
                text-align: center;
                font-size: 12px;
                color: #94a3b8;
                margin-top: 1.2rem;
            }
            .brand-logo-title {
                text-align: center;
                font-size: 32px;
                font-weight: 900;
                letter-spacing: 4px;
                color: #f59e0b;
                text-shadow: 0 0 20px rgba(245, 158, 11, 0.5);
                margin-bottom: 1.5rem;
                font-family: 'Arial Black', sans-serif;
            }
        </style>
    """, unsafe_allow_html=True)

    _, center_col, _ = st.columns([1, 1.2, 1])

    with center_col:
        st.write("")
        st.write("")
        
        # Kesintisiz ZULA Tasarımlı Logo
        st.markdown('<div class="brand-logo-title">⚡ZULA OYUN⚡</div>', unsafe_allow_html=True)

        with st.form("login_form"):
            password_input = st.text_input("GİRİŞ ŞİFRESİ", type="password", placeholder="••••••••••••")
            submit = st.form_submit_button("Sisteme Giriş Yap →", use_container_width=True)

            if submit:
                raw_users = st.secrets.get("USERS", {})
                typed_pass = password_input.strip()

                found_user = None
                for user_name, user_pass in raw_users.items():
                    if str(user_pass).strip() == typed_pass:
                        found_user = str(user_name).strip()
                        break

                if found_user:
                    st.session_state["authenticated"] = True
                    st.session_state["current_user"] = found_user
                    st.session_state["login_time"] = time.time()
                    st.session_state["login_date"] = datetime.now().date()
                    st.rerun()
                else:
                    st.error("❌ Hatalı veya Geçersiz Şifre!")

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
    current_user = st.session_state.get("current_user", "Kullanıcı")
    if login_time is not None:
        elapsed_time = time.time() - login_time
        remaining_min = max(0, int((ONE_HOUR_SECONDS - elapsed_time) / 60))
        st.caption(f"👤 Aktif Kullanıcı: **{current_user}** | ⏱️ Kalan Süre: ~**{remaining_min} dk**")

with col_logout:
    if st.button("🚪 Çıkış Yap", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state["current_user"] = None
        st.session_state["login_time"] = None
        st.session_state["login_date"] = None
        st.rerun()

st.title("📊 QA Görev Raporlama ve Otomasyon Paneli")
st.caption("Google Sheets verilerini otomatik eşleştirin ve rapor oluşturun.")

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
        if "global perf" not in name.lower() and name.lower() != LOG_SHEET_NAME.lower()
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
        st.warning("⚠️ Erişilebilir Kaynak Sheet bulunamadı.")
        st.stop()

except Exception as e:
    st.error(f"Google Drive bağlantı hatası: {e}")
    st.stop()

# --- DİNAMİK ZAMAN VE HESAPLAMALAR ---
months_list = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
now_dt = datetime.now()

default_month_idx = now_dt.month - 1
current_year = now_dt.year

years_list = [str(y) for y in range(max(2025, current_year - 1), current_year + 4)]
default_year_idx = years_list.index(str(current_year)) if str(current_year) in years_list else 0

# --- FORM VE PARAMETRELER ---
st.subheader("🛠️ Rapor Oluşturma Parametreleri")

with st.form("qa_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        source_name = st.selectbox("Kaynak Tablo (Source Sheet)", options=source_options)
    with col2:
        report_name = st.selectbox("Rapor Tablosu (Report Sheet)", options=report_options)

    col3, col4 = st.columns(2)
    
    with col3:
        selected_month = st.selectbox("İşlenecek Ay", months_list, index=default_month_idx)
    with col4:
        selected_year = st.selectbox("İşlenecek Yıl", years_list, index=default_year_idx)

    submit_button = st.form_submit_button("🚀 Raporu Çalıştır ve Güncelle", use_container_width=True)

source_id = source_sheets_dict.get(source_name)
report_id = report_sheets_dict.get(report_name)

st.divider()

# --- İŞLEM BAŞLATMA ---
if submit_button:
    progress_bar = st.progress(0)

    def silent_log_callback(msg):
        pass

    def progress_callback(val):
        progress_bar.progress(val)

    job_details = {
        "source": source_name,
        "report": report_name,
        "month": selected_month,
        "year": selected_year,
        "user": current_user
    }

    try:
        with st.spinner("⏳ Veriler Google Sheets üzerinden okunuyor ve işleniyor, lütfen bekleyin..."):
            # Parametreleri backend'in orijinal beklentisine göre gönderiyoruz
            worker = QAReportWorker(
                creds_input=creds_input,
                source_id=source_id,
                report_id=report_id,
                selected_year=selected_year,
                selected_month=selected_month,
                log_callback=silent_log_callback,
                progress_callback=progress_callback
            )
            
            # Raporu İşle ve Ana Tabloyu Güncelle
            updated_data = worker.process()
        
        # ModBot.log Google Sheets Dosyasına Başarılı Logu Yaz
        append_log_to_google_sheet(creds_input, "Başarılı ✅", job_details)
        
        st.success("✅ Rapor başarıyla güncellendi ve ana tabloya aktarıldı!")
        
        if updated_data is not None and isinstance(updated_data, pd.DataFrame) and not updated_data.empty:
            st.subheader("👁️ Güncellenen Veri Önizlemesi")
            st.dataframe(updated_data, use_container_width=True)

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        job_details["error"] = str(e)
        
        # Hata durumunda log yaz
        append_log_to_google_sheet(creds_input, "Hata ❌", job_details)
        
        st.error(f"❌ İşlem sırasında hata oluştu: {str(e)}")
        # Neden çalışmadığını tam olarak görmek için teknik hatayı ekrana basıyoruz:
        with st.expander("🔍 Hata Detayını Gör"):
            st.code(error_details, language="python")
        
        # ModBot.log Google Sheets Dosyasına Yaz
        append_log_to_google_sheet(creds_input, "Başarılı ✅", job_details)
        
        # Ekran Bildirimi
        st.success("✅ Rapor başarıyla güncellendi ve aktarıldı!")
        
        # Rapor Önizleme Ekranı
        if updated_data is not None and isinstance(updated_data, pd.DataFrame) and not updated_data.empty:
            st.subheader("👁️ Güncellenen Veri Önizlemesi")
            st.dataframe(updated_data, use_container_width=True)

    except Exception as e:
        job_details["error"] = str(e)
        
        # ModBot.log Google Sheets Dosyasına Hata Yaz
        append_log_to_google_sheet(creds_input, "Hata ❌", job_details)
        
        st.error(f"❌ İşlem sırasında bir hata oluştu: {str(e)}")

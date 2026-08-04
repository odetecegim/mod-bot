import os
import json
import base64
import time
import streamlit as st
from backend import QAReportWorker, get_available_spreadsheets

# 1 Saat = 3600 Saniye
ONE_HOUR_SECONDS = 3600

# Sayfa Yapılandırması
st.set_page_config(
    page_title="QA Control Center — Giriş",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- OTURUM VE ZAMAN AŞIMI YÖNETİMİ ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if "login_time" not in st.session_state:
    st.session_state["login_time"] = None

def check_session_timeout():
    """1 saatlik zaman aşımını kontrol eder."""
    if st.session_state["authenticated"] and st.session_state["login_time"] is not None:
        elapsed = time.time() - st.session_state["login_time"]
        if elapsed > ONE_HOUR_SECONDS:
            st.session_state["authenticated"] = False
            st.session_state["login_time"] = None
            st.warning("⚠️ Oturum süreniz (1 saat) dolduğu için kilit ekranına yönlendirildiniz.")

check_session_timeout()

# --- ZULA OYUNCU REHBERİ TEMALI GİRİŞ ARAYÜZÜ ---
def login_screen():
    # Zula Oyuncu Rehberi Resmi HD Arka Plan Görseli
    bg_image_url = "https://images4.alphacoders.com/122/thumb-1920-1228871.jpg"

    st.markdown(f"""
        <style>
            /* Zula Arka Plan Görseli */
            .stApp {{
                background: linear-gradient(rgba(10, 10, 15, 0.65), rgba(10, 10, 15, 0.78)),
                            url('{bg_image_url}') no-repeat center center fixed !important;
                background-size: cover !important;
            }}

            /* Dikey ve Yatay Tam Ortalama */
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
                justify-content: center;
            }}

            /* Rozet Alanı */
            .badge-box {{
                background: rgba(239, 68, 68, 0.18);
                border: 1px solid rgba(239, 68, 68, 0.45);
                border-radius: 50px;
                padding: 6px 16px;
                width: fit-content;
                margin: 0 auto 1rem auto;
                display: flex;
                align-items: center;
                gap: 8px;
                backdrop-filter: blur(8px);
            }}
            .badge-dot {{
                width: 8px;
                height: 8px;
                background-color: #ef4444;
                border-radius: 50%;
                box-shadow: 0 0 10px #ef4444;
            }}
            .badge-text {{
                color: #f87171;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1.5px;
                text-transform: uppercase;
            }}

            /* Başlık Stilleri */
            .title-text {{
                text-align: center;
                font-size: 26px;
                font-weight: 800;
                color: #ffffff;
                letter-spacing: -0.5px;
                margin-bottom: 6px;
                font-family: 'Inter', system-ui, -apple-system, sans-serif;
                text-shadow: 0 2px 10px rgba(0,0,0,0.7);
            }}
            .subtitle-text {{
                text-align: center;
                font-size: 13px;
                color: #cbd5e1;
                margin-bottom: 1.8rem;
                text-shadow: 0 1px 5px rgba(0,0,0,0.7);
            }}

            /* Glassmorphism Form Kartı */
            div[data-testid="stForm"] {{
                background: rgba(15, 15, 23, 0.82) !important;
                border: 1px solid rgba(255, 255, 255, 0.15) !important;
                border-radius: 20px !important;
                padding: 2.2rem 2rem !important;
                box-shadow: 0 25px 50px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.15) !important;
                backdrop-filter: blur(16px);
            }}

            /* Input Alanları */
            label {{
                color: #f1f5f9 !important;
                font-size: 12px !important;
                font-weight: 600 !important;
                letter-spacing: 0.5px !important;
                margin-bottom: 6px !important;
            }}
            div[data-baseweb="input"] {{
                background-color: rgba(10, 10, 18, 0.85) !important;
                border: 1px solid rgba(255, 255, 255, 0.15) !important;
                border-radius: 12px !important;
                color: #ffffff !important;
                transition: all 0.3s ease !important;
            }}
            div[data-baseweb="input"]:focus-within {{
                border-color: #ef4444 !important;
                box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.35) !important;
            }}

            /* Buton Stili */
            div[data-testid="stFormSubmitButton"] > button {{
                background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%) !important;
                color: #ffffff !important;
                border: none !important;
                border-radius: 12px !important;
                height: 48px !important;
                font-weight: 700 !important;
                font-size: 15px !important;
                letter-spacing: 0.5px !important;
                box-shadow: 0 8px 20px rgba(239, 68, 68, 0.45) !important;
                transition: all 0.2s ease-in-out !important;
                margin-top: 10px !important;
            }}
            div[data-testid="stFormSubmitButton"] > button:hover {{
                transform: translateY(-2px);
                box-shadow: 0 12px 25px rgba(239, 68, 68, 0.65) !important;
                background: linear-gradient(135deg, #f87171 0%, #ef4444 100%) !important;
            }}

            /* Alt Bilgi */
            .footer-text {{
                text-align: center;
                font-size: 12px;
                color: #94a3b8;
                margin-top: 1.5rem;
            }}
            .footer-text strong {{
                color: #f1f5f9;
            }}
        </style>
    """, unsafe_allow_html=True)

    st.markdown("""
        <div class="badge-box">
            <div class="badge-dot"></div>
            <div class="badge-text">QA CONTROL CENTER</div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="title-text">Yönetici Portalı</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle-text">Devam etmek için güvenli şifrenizi girin</div>', unsafe_allow_html=True)

    with st.form("login_form"):
        password_input = st.text_input("GİRİŞ ŞİFRESİ", type="password", placeholder="••••••••••••")
        submit = st.form_submit_button("Sisteme Giriş Yap →", use_container_width=True)

        if submit:
            admin_pass = st.secrets.get("ADMIN_PASSWORD", "akademi2026")
            if password_input == admin_pass:
                st.session_state["authenticated"] = True
                st.session_state["login_time"] = time.time()
                st.rerun()
            else:
                st.error("❌ Hatalı Şifre! Lütfen tekrar deneyin.")

    st.markdown('<div class="footer-text">🔒 Oturum süresi: <strong>1 Saat</strong></div>', unsafe_allow_html=True)

# Oturum Doğrulama Kontrolü
if not st.session_state.get("authenticated", False) or st.session_state.get("login_time") is None:
    st.session_state["authenticated"] = False
    st.session_state["login_time"] = None
    login_screen()
    st.stop()

# ==============================================================================
# === GİRİŞ YAPILDIKTAN SONRA GÖRÜNECEK ANA PANEL ===
# ==============================================================================

col_title, col_logout = st.columns([3, 1])

with col_title:
    login_time = st.session_state.get("login_time")
    if login_time is not None:
        elapsed_time = time.time() - login_time
        remaining_min = max(0, int((ONE_HOUR_SECONDS - elapsed_time) / 60))
        st.caption(f"⏱️ Oturum Süresi: Kalan ~**{remaining_min} dakika**")
    else:
        st.caption("⏱️ Oturum Süresi: Belirtilmedi")

with col_logout:
    if st.button("🚪 Çıkış Yap"):
        st.session_state["authenticated"] = False
        st.session_state["login_time"] = None
        st.rerun()

st.title("📊 QA Görev Raporlama Paneli")
st.caption("Google Sheets verilerini seçilen Ay ve Yıl'a göre otomatik eşleştirin ve güncelleyin.")

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
    
    # 1. KAYNAK TABLO (Source Sheet): İçinde "global perf" geçen tabloları siliyoruz
    filtered_source_dict = {
        name: sheet_id for name, sheet_id in source_sheets_dict.items()
        if "global perf" not in name.lower()
    }
    source_sheets_dict = filtered_source_dict
    source_options = list(source_sheets_dict.keys())
    
    # 2. RAPOR TABLOSU (Report Sheet): Sadece "Global Perf" olanları tutuyoruz
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
        st.warning("⚠️ Erişilebilir Kaynak Sheet bulunamadı (Tümü filtrelenmiş veya yetki eksik). Tabloları Service Account e-postası ile paylaştığınızdan emin olun.")
        st.stop()

except Exception as e:
    st.error(f"Google Drive bağlantı hatası: {e}")
    st.stop()

# --- FORM ARAYÜZÜ ---
with st.form("qa_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        source_name = st.selectbox("Kaynak Tablo (Source Sheet)", options=source_options)
    with col2:
        report_name = st.selectbox("Rapor Tablosu (Report Sheet)", options=report_options)

    col3, col4, col5 = st.columns(3)
    
    with col3:
        selected_lang = st.selectbox("Dil", ["Tümü", "ENG", "ESP", "POR"])
    with col4:
        months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylul", "Ekim", "Kasım", "Aralık"]
        selected_month = st.selectbox("Ay", months, index=6)
    with col5:
        selected_year = st.selectbox("Yıl", ["2025", "2026", "2027"], index=1)

    submit_button = st.form_submit_button("🚀 Raporu Güncelle", use_container_width=True)

# --- İŞLEM BAŞLATMA VE LOG EKRANI ---
if submit_button:
    source_id = source_sheets_dict[source_name]
    report_id = report_sheets_dict[report_name]

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

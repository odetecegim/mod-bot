import os
import json
import base64
import streamlit as st
from backend import QAReportWorker, get_available_spreadsheets

# Sayfa Yapılandırması
st.set_page_config(
    page_title="Control Center — Zula Teşkilat Girişi",
    page_icon="🔴",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- ŞİFRE VE OTURUM KONTROLÜ (ZULA TEŞKİLAT TEMASI) ---
def login_screen():
    st.markdown("""
        <style>
            .stApp {
                background: linear-gradient(rgba(10, 10, 12, 0.88), rgba(10, 10, 12, 0.95)),
                            url('https://images.alphacoders.com/849/849204.png') no-repeat center center fixed !important;
                background-size: cover !important;
            }

            .main {
                display: flex;
                justify-content: center;
                align-items: center;
            }
            .block-container {
                padding-top: 2rem !important;
                padding-bottom: 2rem !important;
                max-width: 480px !important;
            }

            .icon-box {
                background: linear-gradient(135deg, #dc2626 0%, #7f1d1d 100%);
                width: 90px;
                height: 90px;
                border-radius: 22px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 1.2rem auto;
                box-shadow: 0 0 35px rgba(220, 38, 38, 0.6);
                border: 2px solid #ef4444;
                overflow: hidden;
                padding: 10px;
            }
            .icon-box img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }

            .title-text {
                text-align: center;
                font-size: 28px;
                font-weight: 800;
                color: #ffffff;
                letter-spacing: 1px;
                text-shadow: 0 0 10px rgba(220, 38, 38, 0.5);
                margin-bottom: 4px;
                font-family: 'Arial Black', sans-serif;
            }
            .subtitle-text {
                text-align: center;
                font-size: 13px;
                color: #9ca3af;
                letter-spacing: 0.5px;
                margin-bottom: 1.8rem;
            }

            div[data-testid="stForm"] {
                background: rgba(18, 18, 22, 0.85) !important;
                border: 1px solid rgba(220, 38, 38, 0.3) !important;
                border-radius: 16px !important;
                padding: 2rem !important;
                box-shadow: 0 15px 35px rgba(0, 0, 0, 0.8), 0 0 15px rgba(220, 38, 38, 0.15) !important;
                backdrop-filter: blur(10px);
            }

            label {
                color: #ef4444 !important;
                font-size: 11px !important;
                font-weight: 800 !important;
                letter-spacing: 0.1em !important;
                text-transform: uppercase !important;
            }
            div[data-baseweb="input"] {
                background-color: #0d0d11 !important;
                border: 1px solid #27272a !important;
                border-radius: 8px !important;
                color: #ffffff !important;
            }
            div[data-baseweb="input"]:focus-within {
                border-color: #ef4444 !important;
                box-shadow: 0 0 10px rgba(239, 68, 68, 0.4) !important;
            }

            div[data-testid="stFormSubmitButton"] > button {
                background: linear-gradient(90deg, #dc2626 0%, #991b1b 100%) !important;
                color: white !important;
                border: 1px solid #f87171 !important;
                border-radius: 8px !important;
                height: 50px !important;
                font-weight: 700 !important;
                font-size: 16px !important;
                letter-spacing: 1px !important;
                text-transform: uppercase !important;
                box-shadow: 0 4px 20px rgba(220, 38, 38, 0.4) !important;
                transition: all 0.2s ease !important;
            }
            div[data-testid="stFormSubmitButton"] > button:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 25px rgba(220, 38, 38, 0.7) !important;
                background: linear-gradient(90deg, #ef4444 0%, #dc2626 100%) !important;
            }

            .footer-text {
                text-align: center;
                font-size: 12px;
                color: #6b7280;
                margin-top: 1.5rem;
            }
            .footer-text span {
                color: #ef4444;
                font-weight: 700;
            }
        </style>

        <script>
            document.addEventListener('mousemove', function(e) {
                let star = document.createElement('div');
                star.className = 'star-particle';
                star.innerHTML = '★';
                
                star.style.left = e.clientX + 'px';
                star.style.top = e.clientY + 'px';
                
                let size = Math.random() * 12 + 10;
                star.style.fontSize = size + 'px';
                star.style.position = 'fixed';
                star.style.color = '#ef4444';
                star.style.textShadow = '0 0 8px #dc2626, 0 0 15px #ff0000';
                star.style.pointerEvents = 'none';
                star.style.zIndex = '999999';
                star.style.transition = 'all 0.6s linear';
                star.style.transform = `translate(-50%, -50%) rotate(${Math.random() * 360}deg)`;
                star.style.opacity = '1';
                
                document.body.appendChild(star);
                
                setTimeout(() => {
                    star.style.top = (e.clientY + 20) + 'px';
                    star.style.opacity = '0';
                    star.style.transform += ' scale(0.3)';
                }, 50);
                
                setTimeout(() => {
                    star.remove();
                }, 600);
            });
        </script>
    """, unsafe_allow_html=True)

    st.markdown('<div class="icon-box"><img src="https://i.ibb.co/JRkyN71r/logo.png" alt="Teşkilat Logo"></div>', unsafe_allow_html=True)
    st.markdown('<div class="title-text">TEŞKİLAT CONTROL CENTER</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle-text">Yetkili Yönetici Girişi</div>', unsafe_allow_html=True)

    with st.form("login_form"):
        password_input = st.text_input("YÖNETİCİ ŞİFRESİ", type="password", placeholder="••••••••••••")
        submit = st.form_submit_button("🎯 ONAYLA VE GİRİŞ YAP", use_container_width=True)

        if submit:
            admin_pass = st.secrets.get("ADMIN_PASSWORD", "akademi2026")
            if password_input == admin_pass:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Yetkisiz Giriş! Şifre Hatalı.")

    st.markdown('<div class="footer-text">Oturum <span>12 saat</span> boyunca aktif kalır</div>', unsafe_allow_html=True)

# Oturum Kontrolü
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    login_screen()
    st.stop()

# ==============================================================================
# === GİRİŞ YAPILDISAN SONRA GÖRÜNECEK ANA PANEL ===
# ==============================================================================

col_title, col_logout = st.columns([4, 1])
with col_logout:
    if st.button("🚪 Çıkış Yap"):
        st.session_state["authenticated"] = False
        st.rerun()

st.title("📊 QA Görev Raporlama Paneli")
st.caption("Google Sheets verilerini seçilen Ay ve Yıl'a göre otomatik eşleştirin ve güncelleyin.")

# --- GOOGLE CREDENTIALS YÖNETİMİ ---
@st.cache_resource
def get_credentials():
    if "GCP_SERVICE_ACCOUNT" in st.secrets:
        try:
            sec = st.secrets["GCP_SERVICE_ACCOUNT"]
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
    elif "GOOGLE_CREDENTIALS" in st.secrets:
        creds = dict(st.secrets["GOOGLE_CREDENTIALS"])
        if "private_key" in creds:
            creds["private_key"] = str(creds["private_key"]).replace("\\n", "\n")
        return creds
    elif os.path.exists("credentials.json"):
        return "credentials.json"
    else:
        return None

creds_input = get_credentials()

if not creds_input:
    st.error("❌ Google bağlantı bilgileri bulunamadı! Lütfen Streamlit Secrets ayarlarını kontrol edin.")
    st.stop()

# --- TABLOLARI LİSTELE VE AYRIŞTIR ---
try:
    sheets_data = get_available_spreadsheets(creds_input)
    source_sheets_dict = sheets_data["source"]
    report_sheets_dict = sheets_data["report"]
    
    source_options = list(source_sheets_dict.keys())
    report_options = list(report_sheets_dict.keys())
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
        selected_lang = st.selectbox("Dil", ["Tümü", "ENG", "ESP", "POR", "TR"])
    with col4:
        months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
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

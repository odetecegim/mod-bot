import streamlit as st
import pandas as pd
import json
import os
import time
from datetime import datetime
from backend import QAReportWorker, get_available_spreadsheets

# Streamlit Konfigürasyonu (En Üstte Olmalıdır)
st.set_page_config(
    page_title="QA Report Automation",
    page_icon="📊",
    layout="wide"
)

# --- SABİTLER VE AYARLAR ---
ONE_HOUR_SECONDS = 3600

# ==========================================
# 🔐 OTURUM VE ZAMAN AŞIMI YÖNETİMİ
# ==========================================

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

# ==========================================
# 🔑 SADECE ŞİFRE İLE GİRİŞ EKRANI
# ==========================================

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
        st.markdown('<div class="brand-logo-title">⚡ ZULA QA ⚡</div>', unsafe_allow_html=True)

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

# ==========================================
# 📊 UYGULAMA ANA ARAYÜZÜ (GİRİŞ SONRASI)
# ==========================================

# Yan Menüde Kullanıcı Bilgisi ve Çıkış Butonu
with st.sidebar:
    st.write(f"👤 **Kullanıcı:** {st.session_state.get('current_user', 'Bilinmeyen')}")
    if st.button("🚪 Çıkış Yap"):
        st.session_state["authenticated"] = False
        st.session_state["current_user"] = None
        st.rerun()

st.title("📊 QA Rapor Otomasyonu")

# --- CREDENTIALS YÜKLEME / OKUMA ---
creds_input = None

if hasattr(st, "secrets") and len(st.secrets) > 0:
    for k in st.secrets:
        if k.lower() in ["gcp_service_account", "credentials", "service_account"]:
            creds_input = dict(st.secrets[k])
            break

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
    st.error("❌ Google Service Account anahtarı okunamadı. Lütfen Secrets yapısını veya credentials.json dosyasını kontrol edin.")
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

# 1. Kaynak Listesi: "Global Perf Tablosu" ve log dosyaları gizlendi
filtered_source_sheets = {
    name: sid for name, sid in all_sheets.items()
    if "global perf" not in name.lower() and not name.lower().endswith(".log") and "modbot" not in name.lower()
}
sorted_source_names = sorted(list(filtered_source_sheets.keys()))

# 2. Hedef Listesi: Sadece "Global Perf Tablosu" kalsın
filtered_report_sheets = {
    name: sid for name, sid in all_sheets.items()
    if "global perf" in name.lower()
}
sorted_report_names = sorted(list(filtered_report_sheets.keys()))

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
# 📅 TARIH SEÇİMLERİ (2026 VE SONRASI)
# ==========================================

col_month, col_year = st.columns(2)

with col_month:
    months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylul", "Ekim", "Kasım", "Aralık"]
    selected_month = st.selectbox("📅 Ay Seçimi:", options=months, index=6)

with col_year:
    years = [2026, 2027, 2028, 2029, 2030]
    selected_year = st.selectbox("📆 Yıl Seçimi:", options=years, index=0)

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
            selected_lang="Tümü",
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

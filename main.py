import streamlit as st
import pandas as pd
import json
import os
import time
from datetime import datetime
from backend import QAReportWorker, get_available_spreadsheets

# Streamlit Konfigürasyonu
st.set_page_config(
    page_title="QA Report Automation",
    page_icon="📊",
    layout="wide"
)

ONE_HOUR_SECONDS = 3600

# ==========================================
# 🔐 OTURUM YÖNETİMİ
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "current_user" not in st.session_state:
    st.session_state["current_user"] = None
if "login_time" not in st.session_state:
    st.session_state["login_time"] = None
if "login_date" not in st.session_state:
    st.session_state["login_date"] = None
if "last_processed_df" not in st.session_state:
    st.session_state["last_processed_df"] = None

def check_session_timeout():
    if st.session_state["authenticated"] and st.session_state["login_time"] is not None:
        now = time.time()
        current_date = datetime.now().date()
        
        if st.session_state["login_date"] is not None and current_date != st.session_state["login_date"]:
            st.session_state["authenticated"] = False
            st.session_state["current_user"] = None
            st.warning("⚠️ Gece yarısı oturumunuz kapatıldı.")
            return

        elapsed = now - st.session_state["login_time"]
        if elapsed > ONE_HOUR_SECONDS:
            st.session_state["authenticated"] = False
            st.session_state["current_user"] = None
            st.warning("⚠️ Oturum süreniz doldu.")

check_session_timeout()

# ==========================================
# 🔑 GİRİŞ EKRANI
# ==========================================
def login_screen():
    st.markdown("""
        <style>
            .stApp { background: radial-gradient(circle at center, #2a2d34 0%, #121316 60%, #08080a 100%) !important; }
            div[data-testid="stForm"] { background: rgba(18, 20, 26, 0.95) !important; border-radius: 16px !important; }
            .brand-logo-container { text-align: center; margin-bottom: 1rem; }
            .brand-logo-img { max-width: 70px; height: auto; }
        </style>
    """, unsafe_allow_html=True)

    _, center_col, _ = st.columns([1, 1.2, 1])
    with center_col:
        st.write("")
        st.markdown('<div class="brand-logo-container"><img src="https://resmim.net/cdn/2026/08/05/EYU08h.webp" class="brand-logo-img"></div>', unsafe_allow_html=True)

        with st.form("login_form"):
            password_input = st.text_input("GİRİŞ ŞİFRESİ", type="password", placeholder="••••••••••••")
            submit = st.form_submit_button("Sisteme Giriş Yap →", use_container_width=True)

            if submit:
                raw_users = st.secrets.get("USERS", {})
                typed_pass = password_input.strip()
                found_user = next((u for u, p in raw_users.items() if str(p).strip() == typed_pass), None)

                if found_user:
                    st.session_state["authenticated"] = True
                    st.session_state["current_user"] = found_user
                    st.session_state["login_time"] = time.time()
                    st.session_state["login_date"] = datetime.now().date()
                    st.rerun()
                else:
                    st.error("❌ Hatalı Şifre!")

if not st.session_state.get("authenticated", False):
    login_screen()
    st.stop()

# ==========================================
# 📌 SOL MENÜ VE NAVİGASYON
# ==========================================
with st.sidebar:
    st.write(f"👤 **Kullanıcı:** {st.session_state.get('current_user', 'Bilinmeyen')}")
    page = st.radio("📌 Navigasyon", ["🚀 Rapor Çalıştır", "📈 Yüklenecek Kişiler & Miktarlar", "📅 Aylık Raporlar"], index=0)
    
    if st.button("🚪 Çıkış Yap"):
        st.session_state["authenticated"] = False
        st.rerun()

# Creds okuma
creds_input = None
if hasattr(st, "secrets") and len(st.secrets) > 0:
    for k in st.secrets:
        if k.lower() in ["gcp_service_account", "credentials", "service_account"]:
            creds_input = dict(st.secrets[k])
            break

# ==========================================
# PAGE 1: RAPOR ÇALIŞTIR
# ==========================================
if page == "🚀 Rapor Çalıştır":
    st.title("📊 QA Rapor Otomasyonu")
    
    sheets_data = get_available_spreadsheets(creds_input)
    all_sheets = sheets_data.get("all", {})

    filtered_source_sheets = {name: sid for name, sid in all_sheets.items() if "global perf" not in name.lower()}
    filtered_report_sheets = {name: sid for name, sid in all_sheets.items() if "global perf" in name.lower()}

    col_src, col_rep = st.columns(2)
    with col_src:
        selected_source_name = st.selectbox("📁 Kaynak Dosya:", options=sorted(list(filtered_source_sheets.keys())))
        source_id = filtered_source_sheets.get(selected_source_name, "")
    with col_rep:
        selected_report_name = st.selectbox("🎯 Hedef Dosya:", options=sorted(list(filtered_report_sheets.keys())))
        report_id = filtered_report_sheets.get(selected_report_name, "")

    col_month, col_year = st.columns(2)
    with col_month:
        months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        selected_month = st.selectbox("📅 Ay:", options=months)
    with col_year:
        years = [2026, 2027, 2028, 2029, 2030]
        selected_year = st.selectbox("📆 Yıl:", options=years)

    log_container = st.empty()
    log_messages = []
    def append_log(msg):
        log_messages.append(msg)
        log_container.text_area("📋 İşlem Canlı Logları", value="\n".join(log_messages), height=200)

    progress_bar = st.progress(0)

    if st.button("🚀 Raporu Çalıştır", type="primary", use_container_width=True):
        worker = QAReportWorker(
            creds_input=creds_input,
            source_id=source_id,
            report_id=report_id,
            selected_year=selected_year,
            selected_month=selected_month,
            log_callback=append_log,
            progress_callback=progress_bar.progress
        )
        updated_df = worker.process()
        if updated_df is not None and not updated_df.empty:
            st.session_state["last_processed_df"] = updated_df
            st.success("🎉 Veriler başarıyla işlendi! 'Yüklenecek Kişiler' sekmesinden performans tablosuna göz atabilirsiniz.")
        else:
            st.error("❌ Veri bulunamadı veya aktarım başarısız.")

# ==========================================
# PAGE 2: PERFORMANS & YÜKLENECEK KİŞİLER
# ==========================================
elif page == "📈 Yüklenecek Kişiler & Miktarlar":
    st.title("📈 Yüklenecek Kişiler ve Puan/Miktar Tablosu")
    
    df = st.session_state.get("last_processed_df", None)
    if df is not None and not df.empty:
        # Sadece sayı verisi veya işlemi olan kişileri süz
        st.subheader("📋 Yükleme Yapılacak Personel Listesi")
        
        # Filtreleme
        search_query = st.text_input("🔍 Personel / Nick Arama:", "")
        if search_query:
            df = df[df.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)]

        st.dataframe(df, use_container_width=True)

        # İndirme Seçeneği (Excel / CSV)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Performans Listesini CSV Olarak İndir",
            data=csv,
            file_name=f"qa_yuklenecek_kisi_ve_miktarlar_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("ℹ️ Henüz işlenmiş bir veri yok. Lütfen önce 'Rapor Çalıştır' sayfasından işlemi başlatın.")

# ==========================================
# PAGE 3: AYLIK RAPORLAR & GEÇMİŞ
# ==========================================
elif page == "📅 Aylık Raporlar":
    st.title("📅 Aylık Konsolide Rapor Görünümü")
    st.write("Aylık bazda genel QA performans durum raporları.")

    sheets_data = get_available_spreadsheets(creds_input)
    filtered_report_sheets = {name: sid for name, sid in sheets_data.get("all", {}).items() if "global perf" in name.lower()}
    
    if filtered_report_sheets:
        selected_rep = st.selectbox("Özetini Görmek İstediğiniz Ana Dosyayı Seçin:", sorted(list(filtered_report_sheets.keys())))
        rep_id = filtered_report_sheets[selected_rep]
        
        try:
            # Doğrudan gspread ile istemci oluşturma (Credentials çakışması engellendi)
            import gspread
            if isinstance(creds_input, dict):
                client = gspread.service_account_from_dict(creds_input)
            else:
                client = gspread.service_account(filename=creds_input)

            wb = client.open_by_key(rep_id)
            sheet_names = [ws.title for ws in wb.worksheets()]
            selected_ws_name = st.selectbox("📆 İncelemek İstediğiniz Ay Sekmesini Seçin:", sheet_names)
            
            if st.button("📊 Aylık Verileri Getir", type="primary"):
                ws = wb.worksheet(selected_ws_name)
                monthly_data = ws.get_all_values()
                
                if monthly_data and len(monthly_data) > 0:
                    raw_headers = monthly_data[0]
                    cleaned_headers = []
                    seen_headers = {}
                    
                    for idx, h in enumerate(raw_headers):
                        h_str = str(h).strip()
                        if not h_str:
                            h_str = f"Sütun_{idx+1}"
                        
                        if h_str in seen_headers:
                            seen_headers[h_str] += 1
                            h_str = f"{h_str}_{seen_headers[h_str]}"
                        else:
                            seen_headers[h_str] = 0
                        cleaned_headers.append(h_str)

                    if len(monthly_data) > 1:
                        m_df = pd.DataFrame(monthly_data[1:], columns=cleaned_headers)
                    else:
                        m_df = pd.DataFrame(columns=cleaned_headers)
                        
                    st.subheader(f"📑 {selected_ws_name} Sekmesi Performans Tablosu")
                    st.dataframe(m_df, use_container_width=True)
                else:
                    st.warning("⚠️ Seçilen sekme boş!")
        except Exception as e:
            st.error(f"❌ Rapor okuma hatası: {e}")

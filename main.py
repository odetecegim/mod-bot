import streamlit as st
import pandas as pd
import time
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread

from backend import (
    QAReportWorker, 
    get_available_spreadsheets, 
    process_za_and_insert_month
)

st.set_page_config(
    page_title="QA Report Automation",
    page_icon="📊",
    layout="wide"
)

ONE_HOUR_SECONDS = 3600

# Sabit Google Sheets Log Dosyası ID'si
TARGET_LOG_SHEET_ID = "1WMyChax15-VD7o-39FYVcA10NDYwi_M_7zpIn0fFJOE"

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
if "active_report_id" not in st.session_state:
    st.session_state["active_report_id"] = TARGET_LOG_SHEET_ID

creds_input = None
if hasattr(st, "secrets") and len(st.secrets) > 0:
    for k in st.secrets:
        if k.lower() in ["gcp_service_account", "credentials", "service_account"]:
            creds_input = dict(st.secrets[k])
            break

# ==========================================
# 📜 SABİT GOOGLE SHEETS 'ModBot.log' SEKMESİNE LOG YAZMA
# ==========================================
def append_log_to_modbot_sheet(action_type, details, user_name=None):
    """
    Log verilerini belirtilen sabit Google Sheets belgesinin 'ModBot.log' sekmesine yazar.
    """
    try:
        active_user = user_name or st.session_state.get("current_user") or "Bilinmeyen Kullanıcı"

        if isinstance(creds_input, dict):
            client = gspread.service_account_from_dict(creds_input)
        else:
            client = gspread.service_account(filename=creds_input)

        wb = client.open_by_key(TARGET_LOG_SHEET_ID)

        try:
            log_ws = wb.worksheet("ModBot.log")
        except gspread.WorksheetNotFound:
            log_ws = wb.add_worksheet(title="ModBot.log", rows="1000", cols="4")
            log_ws.append_row(["Tarih / Saat", "Oturum Açan Kullanıcı", "İşlem Türü", "Detaylar"])

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_ws.append_row([now_str, str(active_user), str(action_type), str(details)])
    except Exception as e:
        print(f"ModBot.log yazma hatası: {e}")

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
            .brand-logo-container {
                text-align: center;
                margin-bottom: 1rem;
            }
            .brand-logo-img {
                max-width: 70px;
                height: auto;
                filter: drop-shadow(0px 0px 8px rgba(245, 158, 11, 0.4));
            }
        </style>
    """, unsafe_allow_html=True)

    _, center_col, _ = st.columns([1, 1.2, 1])

    with center_col:
        st.write("")
        st.write("")
        st.markdown('''
            <div class="brand-logo-container">
                <img src="https://resmim.net/cdn/2026/08/05/EYU08h.webp" class="brand-logo-img" alt="Zula Logo">
            </div>
        ''', unsafe_allow_html=True)

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
                    append_log_to_modbot_sheet("GİRİŞ", "Sisteme giriş yaptı.", user_name=found_user)
                    st.rerun()
                else:
                    st.error("❌ Hatalı veya Geçersiz Şifre!")

        st.markdown('<div class="footer-text">🔒 Oturum süresi: <strong>1 Saat / Gece 00:00 Çıkışlı</strong></div>', unsafe_allow_html=True)

if not st.session_state.get("authenticated", False):
    login_screen()
    st.stop()

# ==========================================
# 📌 SOL MENÜ & NAVİGASYON
# ==========================================
with st.sidebar:
    st.write(f"👤 **Oturum Açan:** `{st.session_state.get('current_user', 'Bilinmeyen')}`")
    page = st.radio("📌 Navigasyon", ["🚀 Rapor Çalıştır", "📈 Yüklenecek Kişiler & Miktarlar", "📅 Aylık Raporlar"], index=0)
    
    if st.button("🚪 Çıkış Yap"):
        append_log_to_modbot_sheet("ÇIKIŞ", "Sistemden çıkış yapıldı.")
        st.session_state["authenticated"] = False
        st.session_state["current_user"] = None
        st.rerun()

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
        report_id = filtered_report_sheets.get(selected_report_name, TARGET_LOG_SHEET_ID)
        st.session_state["active_report_id"] = report_id

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
        st.session_state["active_report_id"] = report_id
        append_log_to_modbot_sheet("RAPOR ÇALIŞTIRILDI", f"Kaynak: {selected_source_name}, Hedef: {selected_report_name}, Dönem: {selected_month} {selected_year}")
        
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
            st.session_state["selected_month"] = selected_month
            st.success("🎉 Veriler başarıyla işlendi!")
        else:
            st.error("❌ Veri bulunamadı veya aktarım başarısız.")

# ==========================================
# PAGE 2: PERFORMANS & YÜKLEYİCİ LİSTESİ
# ==========================================
elif page == "📈 Yüklenecek Kişiler & Miktarlar":
    st.title("📈 Yüklenecek Kişiler ve Puan/Miktar Tablosu")
    
    if "last_processed_df" in st.session_state and st.session_state["last_processed_df"] is not None and not st.session_state["last_processed_df"].empty:
        
        st.subheader("📋 Genel Performans Tablosu (Canlı Kanaat Düzenleme & Anlık Hesap)")
        
        # 1. Personel / Nick Arama
        search_query = st.text_input("🔍 Personel / Nick Arama:", "")
        
        df_base = st.session_state["last_processed_df"].copy()
        
        if search_query:
            df_display = df_base[df_base.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)].copy()
        else:
            df_display = df_base.copy()

        # 2. Düzenlenebilir Tablo
        edited_raw_df = st.data_editor(
            df_display,
            num_rows="dynamic",
            use_container_width=True,
            key="genel_performans_editor_v3",
            disabled=["Toplam", "ZA"]
        )

        # ------------------------------------------------------------------
        # 🧮 ANLIK REAKTİF FORMÜL HESAPLAMA (GİRİLEN SON DEĞERİ ANINDA İŞLER)
        # ------------------------------------------------------------------
        score_cols = [
            "Zula Pass", "0 Kul. TESTİ", "Genel Check", "Hata bildirimi", 
            "Öneri Bildirimi", "Discord PC", "Hakemlik", "Diğer/Kanaat"
        ]
        
        valid_score_cols = [c for c in edited_raw_df.columns if any(sc.lower() in str(c).lower() for sc in score_cols)]

        # Tablodan gelen verileri temizle, sayı yap (Silinirse veya geçersizse 0 yap)
        for col in valid_score_cols:
            edited_raw_df[col] = pd.to_numeric(
                edited_raw_df[col].astype(str).str.replace(',', '.').str.strip(), 
                errors='coerce'
            ).fillna(0)

        # Toplam ve ZA sütunlarını ANINDA canlı hesapla
        if valid_score_cols:
            edited_raw_df["Toplam"] = edited_raw_df[valid_score_cols].sum(axis=1).astype(int)
            edited_raw_df["ZA"] = edited_raw_df["Toplam"] * 500

        # Kullanıcı/Nick bazlı eşleştirip st.session_state verisini ezilmeden güncelle
        id_col = None
        for col in ["Nick", "Personel", "Kullanıcı", "Ad Soyad"]:
            if col in df_base.columns:
                id_col = col
                break

        if id_col and search_query:
            df_base.set_index(id_col, inplace=True)
            edited_temp = edited_raw_df.set_index(id_col)
            df_base.update(edited_temp)
            df_base.reset_index(inplace=True)
            st.session_state["last_processed_df"] = df_base
        else:
            st.session_state["last_processed_df"] = edited_raw_df.copy()

        # ------------------------------------------------------------------
        # 💾 GOOGLE SHEETS & MODBOT.LOG SENKRONİZASYON BUTONU
        # ------------------------------------------------------------------
        st.write("")
        col_save, _ = st.columns([1, 2])
        with col_save:
            if st.button("💾 Değişiklikleri Google Sheets'e Kaydet", type="primary", use_container_width=True):
                with st.spinner("Kanaat ve puan verileri Google Sheets'e işleniyor..."):
                    try:
                        sheets_data = get_available_spreadsheets(creds_input)
                        all_sheets = sheets_data.get("all", {})
                        
                        rep_id = st.session_state.get("active_report_id")
                        if not rep_id or rep_id not in all_sheets.values():
                            for name, sid in all_sheets.items():
                                if "global perf" in name.lower():
                                    rep_id = sid
                                    break
                        if not rep_id:
                            rep_id = TARGET_LOG_SHEET_ID

                        if isinstance(creds_input, dict):
                            client = gspread.service_account_from_dict(creds_input)
                        else:
                            client = gspread.service_account(filename=creds_input)
                        
                        wb = client.open_by_key(rep_id)
                        ws = wb.active
                        
                        # Güncel hafızadaki veriyi Google Sheets'e aktar
                        updated_df_to_save = st.session_state["last_processed_df"]
                        data_to_write = [updated_df_to_save.columns.tolist()] + updated_df_to_save.astype(str).values.tolist()
                        
                        ws.clear()
                        ws.update('A1', data_to_write)
                        
                        append_log_to_modbot_sheet(
                            "KANAAT/PUAN GÜNCELLEME", 
                            f"Toplam {len(updated_df_to_save)} personelin puan ve kanaat verileri kaydedildi."
                        )
                        st.success("✅ Tüm Kanaat puanları ve yeni hesaplamalar Google Sheets'e başarıyla kaydedildi!")
                    except Exception as e:
                        st.error(f"❌ Google Sheets kaydetme hatası: {e}")

        st.markdown("---")
        
        # ⚡ İŞLE BUTONU (AY TABLOSUNA AKTAR)
        st.subheader("⚡ ZA Miktarlarını Ay Tablosuna Aktar & Son Miktarı Hesapla")
        
        col_month_sel, col_btn = st.columns([2, 1])
        with col_month_sel:
            target_month_to_process = st.selectbox(
                "İşlenecek Hedef Ayı Seçin:", 
                ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"],
                index=6
            )

        with col_btn:
            st.write("")
            st.write("")
            process_btn = st.button("⚡ ZA Miktarlarını İşle", type="primary", use_container_width=True)

        if process_btn:
            append_log_to_modbot_sheet("ZA MİKTARLARI İŞLENDİ", f"Hedef Ay: {target_month_to_process}")
            with st.spinner("ZA verileri işleniyor..."):
                try:
                    sheets_data = get_available_spreadsheets(creds_input)
                    all_sheets = sheets_data.get("all", {})
                    
                    rep_id = st.session_state.get("active_report_id")
                    if not rep_id or rep_id not in all_sheets.values():
                        for name, sid in all_sheets.items():
                            if "global perf" in name.lower():
                                rep_id = sid
                                break
                    if not rep_id:
                        rep_id = TARGET_LOG_SHEET_ID

                    if isinstance(creds_input, dict):
                        client = gspread.service_account_from_dict(creds_input)
                    else:
                        client = gspread.service_account(filename=creds_input)

                    wb = client.open_by_key(rep_id)
                    ws = wb.active
                    
                    log_msgs = []
                    success = process_za_and_insert_month(ws, target_month_to_process, log_func=lambda m: log_msgs.append(m))
                    
                    for m in log_msgs:
                        st.write(m)
                        
                    if success:
                        st.balloons()
                        st.success(f"🎉 ZA verileri [{target_month_to_process}] sütununa işlendi!")
                except gspread.exceptions.SpreadsheetNotFound:
                    st.error(f"❌ Google Sheets Dosyası Bulunamadı! Lütfen Service Account e-postanıza bu tablo için 'Düzenleyen' yetkisi verdiğinizden emin olun.")
                except Exception as e:
                    st.error(f"❌ İşlem sırasında bir hata oluştu: {e}")

        st.markdown("---")
        
        # 🎁 YÜKLEYİCİ CANLI DÜZENLEME TABLOSU
        st.subheader("🚀 Yükleyici İçin Temiz Liste (Düzenlenebilir)")
        
        current_df = st.session_state["last_processed_df"]
        cols = current_df.columns.tolist()
        user_col = "Nick" if "Nick" in cols else (cols[1] if len(cols) > 1 else cols[0])
        za_col = "ZA" if "ZA" in cols else cols[-1]

        df_loader_base = current_df[[user_col, za_col]].copy()
        df_loader_base.columns = ["Kullanıcı / Personel", "Yüklenecek Son ZA Miktarı"]
        
        def clean_za_val(val):
            if pd.isna(val):
                return 0
            val_str = str(val).strip().replace('.', '').replace(',', '')
            if val_str.isdigit():
                return int(val_str)
            return 0

        df_loader_base["numeric_za"] = df_loader_base["Yüklenecek Son ZA Miktarı"].apply(clean_za_val)
        df_loader_base = df_loader_base[df_loader_base["numeric_za"] > 0]
        df_editable = df_loader_base[["Kullanıcı / Personel", "Yüklenecek Son ZA Miktarı"]].reset_index(drop=True)

        edited_loader_df = st.data_editor(
            df_editable,
            num_rows="dynamic",
            use_container_width=True,
            key="za_loader_editor_v3"
        )

        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            csv_edited = edited_loader_df.to_csv(index=False, sep="\t").encode('utf-8')
            if st.download_button(
                label="📋 Yükleyici Listesini İndir (Güncel)",
                data=csv_edited,
                file_name=f"yukleyici_guncel_liste_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain",
                use_container_width=True
            ):
                append_log_to_modbot_sheet("İNDİRME", "Yükleyici TXT listesi indirildi.")

        with col_dl2:
            csv_full = current_df.to_csv(index=False).encode('utf-8')
            if st.download_button(
                label="📥 Tüm Genel Performans Tablosunu İndir",
                data=csv_full,
                file_name=f"qa_tam_tablo_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            ):
                append_log_to_modbot_sheet("İNDİRME", "Genel Performans CSV indirildi.")
    else:
        st.info("ℹ️ Henüz işlenmiş bir veri yok. Lütfen önce 'Rapor Çalıştır' sayfasından işlemi başlatın.")

# ==========================================
# PAGE 3: AYLIK RAPORLAR
# ==========================================
elif page == "📅 Aylık Raporlar":
    st.title("📅 Aylık Konsolide Rapor Görünümü")
    
    sheets_data = get_available_spreadsheets(creds_input)
    filtered_report_sheets = {name: sid for name, sid in sheets_data.get("all", {}).items() if "global perf" in name.lower()}
    
    if filtered_report_sheets:
        selected_rep = st.selectbox("Özetini Görmek İstediğiniz Ana Dosyayı Seçin:", sorted(list(filtered_report_sheets.keys())))
        rep_id = filtered_report_sheets[selected_rep]
        
        try:
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

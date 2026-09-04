import json
import os
import hmac

import streamlit as st

from backend import (
    QAReportWorker,
    get_available_spreadsheets,
    get_member_za_summary,
    get_visible_worksheet_titles,
    read_visible_worksheet,
    update_visible_worksheet,
    append_audit_log,
)


DEFAULT_AUDIT_LOG_SHEET_ID = "1WMyChax15-VD7o-39FYVcA10NDYwi_M_7zpIn0fFJOE"


st.set_page_config(page_title="QA Raporlama Paneli", page_icon="📊", layout="centered")
st.title("📊 QA Görev Raporlama Paneli")
st.caption("Açık sekmelerdeki e-posta adreslerini seçilen ay ve yıla göre eşleştirip güncelleyin.")


def setup_credentials():
    if "GOOGLE_CREDENTIALS" in st.secrets:
        credentials = dict(st.secrets["GOOGLE_CREDENTIALS"])
        with open("temp_credentials.json", "w") as credential_file:
            json.dump(credentials, credential_file)
        return "temp_credentials.json"
    return "credentials.json" if os.path.exists("credentials.json") else None


active_json_path = setup_credentials()
if not active_json_path:
    st.error("❌ 'credentials.json' dosyası bulunamadı!")
    st.stop()


def get_user_passwords():
    if "USERS" in st.secrets:
        return dict(st.secrets["USERS"])
    if "ADMIN_USERS" in st.secrets:
        return dict(st.secrets["ADMIN_USERS"])
    return {}


def audit_log(user_name, action, details="", status="Başarılı"):
    audit_spreadsheet_id = st.secrets.get("AUDIT_LOG_SHEET_ID", DEFAULT_AUDIT_LOG_SHEET_ID)
    append_audit_log(
        active_json_path,
        str(st.secrets["AUDIT_LOG_SHEET_ID"]),
        str(audit_spreadsheet_id),
        str(st.secrets.get("AUDIT_LOG_WORKSHEET", "İşlem Logları")),
        user_name,
        action,
        details,
        status,
    )


user_passwords = get_user_passwords()
if not user_passwords:
    st.error("❌ Kullanıcı hesapları ayarlanmamış. Streamlit Secrets'a USERS ekleyin.")
    st.stop()
if "AUDIT_LOG_SHEET_ID" not in st.secrets:
    st.error("❌ Log tablosu ayarlanmamış. Streamlit Secrets'a AUDIT_LOG_SHEET_ID ekleyin.")
    st.stop()

if "authenticated_user" not in st.session_state:
    st.session_state.authenticated_user = None

if not st.session_state.authenticated_user:
    st.subheader("🔐 Kullanıcı Girişi")
    with st.form("login_form"):
        login_user_name = st.text_input("Kullanıcı adı")
        login_password = st.text_input("Şifre", type="password")
        login_submit = st.form_submit_button("Giriş Yap", use_container_width=True)
    if login_submit:
        expected_password = str(user_passwords.get(login_user_name.strip(), ""))
        if expected_password and hmac.compare_digest(login_password, expected_password):
            st.session_state.authenticated_user = login_user_name.strip()
            try:
                audit_log(st.session_state.authenticated_user, "Giriş yaptı")
            except Exception as error:
                st.error(f"❌ Giriş logu yazılamadı: {error}")
                st.stop()
            st.rerun()
        else:
            try:
                audit_log(login_user_name.strip() or "Bilinmeyen", "Başarısız giriş denemesi", status="Başarısız")
            except Exception:
                pass
            st.error("❌ Kullanıcı adı veya şifre hatalı.")
    st.stop()

current_user = st.session_state.authenticated_user
st.sidebar.success(f"Giriş yapan kullanıcı: {current_user}")
if st.sidebar.button("Çıkış Yap"):
    try:
        audit_log(current_user, "Çıkış yaptı")
    except Exception as error:
        st.warning(f"Çıkış logu yazılamadı: {error}")
    finally:
        st.session_state.authenticated_user = None
        st.rerun()


@st.cache_data(ttl=600)
def fetch_spreadsheets(credentials_path):
    return get_available_spreadsheets(credentials_path)


try:
    with st.spinner("Google Drive tabloları yükleniyor..."):
        spreadsheet_dict = fetch_spreadsheets(active_json_path)["all"]
except Exception as error:
    st.error(f"Google Drive bağlantı hatası: {error}")
    st.stop()

sheet_names = list(spreadsheet_dict)

with st.expander("✏️ Açık Google Sheets Sekmesini Canlı Düzenle"):
    st.caption("Gizli sekmeler listelenmez. Kaydet düğmesi, yaptığınız değişiklikleri doğrudan seçilen sekmeye yazar.")
    editor_spreadsheet_name = st.selectbox("Düzenlenecek tablo", sheet_names, key="editor_spreadsheet")
    try:
        editor_spreadsheet_id = spreadsheet_dict[editor_spreadsheet_name]
        visible_worksheets = get_visible_worksheet_titles(active_json_path, editor_spreadsheet_id)
        if not visible_worksheets:
            st.info("Bu tabloda açık sekme bulunamadı.")
        else:
            editor_worksheet_name = st.selectbox("Açık sekme", visible_worksheets, key=f"worksheet_{editor_spreadsheet_id}")
            editor_data = read_visible_worksheet(active_json_path, editor_spreadsheet_id, editor_worksheet_name)
            viewed_editor_key = f"viewed_{editor_spreadsheet_id}_{editor_worksheet_name}"
            if not st.session_state.get(viewed_editor_key):
                audit_log(current_user, "Sekme görüntüledi", f"{editor_spreadsheet_name} / {editor_worksheet_name}")
                st.session_state[viewed_editor_key] = True
            updated_editor_data = st.data_editor(
                editor_data,
                num_rows="dynamic",
                hide_index=True,
                use_container_width=True,
                key=f"data_editor_{editor_spreadsheet_id}_{editor_worksheet_name}",
            )
            if st.button("💾 Değişiklikleri Canlı Kaydet", key=f"save_{editor_spreadsheet_id}_{editor_worksheet_name}"):
                update_visible_worksheet(active_json_path, editor_spreadsheet_id, editor_worksheet_name, updated_editor_data)
                audit_log(current_user, "Sekme düzenledi", f"{editor_spreadsheet_name} / {editor_worksheet_name}")
                st.success(f"✅ [{editor_worksheet_name}] sekmesindeki değişiklikler kaydedildi.")
    except Exception as error:
        try:
            audit_log(current_user, "Sekme işlemi hatası", str(error), "Başarısız")
        except Exception:
            pass
        st.error(f"❌ Sekme düzenleme hatası: {error}")

with st.form("qa_form"):
    source_name, report_name = st.columns(2)
    with source_name:
        selected_source = st.selectbox("Kaynak Tablo", options=sheet_names)
    with report_name:
        selected_report = st.selectbox("Rapor Tablosu", options=sheet_names)
    language, month, year = st.columns(3)
    with language:
        selected_language = st.selectbox("Dil", ["Tümü", "ENG", "ESP", "POR", "TR"])
    with month:
        selected_month = st.selectbox("Ay", ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"], index=6)
    with year:
        selected_year = st.selectbox("Yıl", ["2025", "2026", "2027"], index=1)
    submit_button = st.form_submit_button("🚀 Raporu Güncelle", use_container_width=True)


if submit_button:
    progress_bar = st.progress(0)
    log_box = st.code("> İşlem başlatıldı...\n", language="text")
    logs = []

    def log_callback(message):
        logs.append(f"> {message}")
        log_box.code("\n".join(logs), language="text")

    try:
        audit_log(current_user, "Rapor güncelleme başlattı", f"{selected_month} {selected_year} / {selected_language}")
        worker = QAReportWorker(
            creds_input=active_json_path,
            source_id=spreadsheet_dict[selected_source],
            report_id=spreadsheet_dict[selected_report],
            selected_year=selected_year,
            selected_month=selected_month,
            selected_language=selected_language,
            log_callback=log_callback,
            progress_callback=progress_bar.progress,
        )
        report_data = worker.process()
        if report_data is None:
            audit_log(current_user, "Rapor güncelleme", "İşlem tamamlanamadı", "Başarısız")
            st.error("❌ Rapor güncellenemedi; ayrıntılar işlem günlüğünde.")
        else:
            audit_log(current_user, "Rapor güncelledi", f"{worker.used_worksheet_title} sekmesi güncellendi")
            st.success("✅ Rapor başarıyla güncellendi!")
            st.subheader("👤 Aylık Oyuncu ZA Özeti")
            member_za_summary, has_member_id_and_za = get_member_za_summary(report_data)
            if not has_member_id_and_za:
                st.warning("Bu rapor sekmesinde 'Member ID' veya 'ZA' sütunu bulunamadı.")
            st.dataframe(member_za_summary, hide_index=True, use_container_width=True)
    except Exception as error:
        try:
            audit_log(current_user, "Rapor güncelleme hatası", str(error), "Başarısız")
        except Exception:
            pass
        st.error(f"❌ İşlem sırasında bir hata oluştu: {error}")

import json
import os
import hmac
from datetime import datetime

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

MONTH_NAMES = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


st.set_page_config(page_title="QA Raporlama Paneli", page_icon="📊", layout="wide")
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


def get_user_from_password(password, user_passwords):
    matched_users = [
        user_name
        for user_name, expected_password in user_passwords.items()
        if hmac.compare_digest(password, str(expected_password))
    ]
    return matched_users[0] if len(matched_users) == 1 else None


def audit_log(user_name, action, details="", status="Başarılı"):
    audit_spreadsheet_id = st.secrets.get("AUDIT_LOG_SHEET_ID", DEFAULT_AUDIT_LOG_SHEET_ID)
    append_audit_log(
        active_json_path,
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
if "authenticated_user" not in st.session_state:
    st.session_state.authenticated_user = None

if not st.session_state.authenticated_user:
    st.subheader("🔐 Kullanıcı Girişi")
    with st.form("login_form"):
        login_password = st.text_input("Şifre", type="password")
        login_submit = st.form_submit_button("Giriş Yap", use_container_width=True)
    if login_submit:
        matched_user = get_user_from_password(login_password, user_passwords)
        if matched_user:
            st.session_state.authenticated_user = matched_user
            try:
                audit_log(st.session_state.authenticated_user, "Giriş yaptı")
            except Exception as error:
                st.error(f"❌ Giriş logu yazılamadı: {error}")
                st.stop()
            st.rerun()
        else:
            try:
                audit_log("Bilinmeyen", "Başarısız giriş denemesi", status="Başarısız")
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

st.sidebar.markdown("---")
selected_page = st.sidebar.radio(
    "Menü",
    ["🚀 QA Rapor Güncelleme", "✏️ Canlı Tablo Düzenle"],
    index=0,
)


@st.cache_data(ttl=600)
def fetch_spreadsheets(credentials_path):
    return get_available_spreadsheets(credentials_path)


try:
    with st.spinner("Google Drive tabloları yükleniyor..."):
        spreadsheet_dict = fetch_spreadsheets(active_json_path)["all"]
except Exception as error:
    st.error(f"❌ Google Drive bağlantı hatası: {error}")
    st.info(
        "Kontrol edin: 1) credentials.json / GOOGLE_CREDENTIALS geçerli bir "
        "servis hesabına mı ait, 2) Google Sheets API ve Google Drive API bu "
        "projede etkin mi, 3) servis hesabının e-posta adresi ile en az bir "
        "tablo paylaşıldı mı."
    )
    st.stop()

sheet_names = list(spreadsheet_dict)

if not sheet_names:
    st.error(
        "❌ Bu servis hesabına paylaşılmış hiçbir Google Sheets tablosu bulunamadı."
    )
    try:
        service_account_email = json.load(open(active_json_path)).get("client_email", "bilinmiyor")
    except Exception:
        service_account_email = "bilinmiyor"
    st.info(
        f"Çözüm: Kullanmak istediğiniz Google Sheets dosyalarını şu servis "
        f"hesabı e-postasıyla paylaşın (Düzenleyen olarak): **{service_account_email}**"
    )
    st.stop()

@st.cache_data(ttl=600)
def fetch_visible_worksheets(credentials_path, spreadsheet_id):
    return get_visible_worksheet_titles(credentials_path, spreadsheet_id)


def _default_index(options, preferred):
    return options.index(preferred) if preferred in options else 0


def _candidate_index(options, month_name, year):
    probe = month_name.casefold()[:5]
    for index, option in enumerate(options):
        normalized = str(option).casefold()
        if str(year) in normalized and probe in normalized:
            return index
    return 0


if selected_page == "✏️ Canlı Tablo Düzenle":
    st.subheader("✏️ Açık Google Sheets Sekmesini Canlı Düzenle")
    st.caption(
        "Gizli ve araç günlük sekmeleri listelenmez. Kaydet düğmesi, yaptığınız "
        "değişiklikleri doğrudan seçilen sekmeye yazar."
    )
    editor_spreadsheet_name = st.selectbox("Düzenlenecek tablo", sheet_names, key="editor_spreadsheet")
    try:
        editor_spreadsheet_id = spreadsheet_dict[editor_spreadsheet_name]
        visible_worksheets = fetch_visible_worksheets(active_json_path, editor_spreadsheet_id)
        if not visible_worksheets:
            st.info("Bu tabloda düzenlenebilir açık sekme bulunamadı.")
        else:
            editor_worksheet_name = st.selectbox(
                "Açık sekme", visible_worksheets, key=f"editor_worksheet_{editor_spreadsheet_id}"
            )
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
                update_visible_worksheet(
                    active_json_path, editor_spreadsheet_id, editor_worksheet_name, updated_editor_data
                )
                audit_log(current_user, "Sekme düzenledi", f"{editor_spreadsheet_name} / {editor_worksheet_name}")
                st.success(f"✅ [{editor_worksheet_name}] sekmesindeki değişiklikler kaydedildi.")
                fetch_visible_worksheets.clear()
    except Exception as error:
        try:
            audit_log(current_user, "Sekme işlemi hatası", str(error), "Başarısız")
        except Exception:
            pass
        st.error(f"❌ Sekme düzenleme hatası: {error}")

else:
    st.subheader("🚀 QA Rapor Güncelleme")
    st.caption(
        "Kaynak form sekmeleri 'Zaman damgası' sütununa göre seçilen aya filtrelenir; "
        "isim/nick eşleşmesiyle hedef sekmedeki ilgili puan sütunlarına yazılır. "
        "'Toplam' ve 'ZA' sütunlarına dokunulmaz (formülleriniz korunur)."
    )
    source_column, report_column = st.columns(2)
    with source_column:
        selected_source = st.selectbox(
            "Kaynak Tablo (form yanıtları)", sheet_names, index=_default_index(sheet_names, "Error Reporting ENG")
        )
    with report_column:
        selected_report = st.selectbox(
            "Rapor Tablosu", sheet_names, index=_default_index(sheet_names, "Global Perf Tablosu")
        )

    month_column, year_column, target_column = st.columns([1, 1, 2])
    with month_column:
        selected_month = st.selectbox("Ay", MONTH_NAMES, index=datetime.now().month - 1)
    with year_column:
        year_options = [str(year) for year in range(datetime.now().year - 1, datetime.now().year + 3)]
        selected_year = st.selectbox("Yıl", year_options, index=1)
    with target_column:
        try:
            report_worksheets = fetch_visible_worksheets(active_json_path, spreadsheet_dict[selected_report])
        except Exception as error:
            report_worksheets = []
            st.error(f"❌ Sekme listesi alınamadı: {error}")
        if not report_worksheets:
            selected_target = None
            st.info("Bu tabloda düzenlenebilir açık sekme bulunamadı.")
        else:
            selected_target = st.selectbox(
                "Hedef Sekme",
                report_worksheets,
                index=_candidate_index(report_worksheets, selected_month, selected_year),
                key=f"target_{spreadsheet_dict[selected_report]}",
            )
            st.caption(f"Ay/yıl ile eşleşen sekme otomatik önerilir: **{selected_target}**")

    submit_button = st.button("🚀 Raporu Güncelle", use_container_width=True, type="primary")


    if submit_button:
        if not selected_target:
            st.error("❌ Hedef sekme seçilmedi.")
            st.stop()
        progress_bar = st.progress(0)
        log_box = st.code("> İşlem başlatıldı...\n", language="text")
        logs = []

        def log_callback(message):
            logs.append(f"> {message}")
            log_box.code("\n".join(logs), language="text")

        try:
            audit_log(
                current_user,
                "Rapor güncelleme başlattı",
                f"{selected_report} / {selected_target} ({selected_month} {selected_year})",
            )
            worker = QAReportWorker(
                creds_input=active_json_path,
                source_id=spreadsheet_dict[selected_source],
                report_id=spreadsheet_dict[selected_report],
                selected_year=selected_year,
                selected_month=selected_month,
                target_worksheet_title=selected_target,
                log_callback=log_callback,
                progress_callback=progress_bar.progress,
            )
            report_data = worker.process()
            if report_data is None:
                audit_log(current_user, "Rapor güncelleme", "İşlem tamamlanamadı", "Başarısız")
                st.error("❌ Rapor güncellenemedi; ayrıntılar işlem günlüğünde.")
            else:
                audit_log(
                    current_user,
                    "Rapor güncelledi",
                    f"{worker.used_worksheet_title} sekmesi güncellendi ({selected_month} {selected_year})",
                )
                st.success(f"✅ [{worker.used_worksheet_title}] sekmesi başarıyla güncellendi!")
                st.subheader("👤 Aylık Oyuncu ZA Özeti")
                member_za_summary, has_member_id_and_za = get_member_za_summary(report_data)
                if not has_member_id_and_za:
                    st.warning("Bu rapor sekmesinde 'Member ID' veya 'ZA' sütunu bulunamadı.")
                st.dataframe(member_za_summary, hide_index=True, use_container_width=True)
                fetch_visible_worksheets.clear()
        except Exception as error:
            try:
                audit_log(current_user, "Rapor güncelleme hatası", str(error), "Başarısız")
            except Exception:
                pass
            st.error(f"❌ İşlem sırasında bir hata oluştu: {error}")

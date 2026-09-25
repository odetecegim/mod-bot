import importlib
import json
import os
import hmac
import re
import inspect
from datetime import datetime

import pandas as pd
import streamlit as st

import backend
importlib.reload(backend)
from backend import (
    QAReportWorker,
    get_available_spreadsheets,
    get_member_za_summary,
    get_visible_worksheet_titles,
    read_visible_worksheet,
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
    ["🚀 QA Rapor Güncelleme", "📊 Aylık Perf Listesi"],
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
def fetch_visible_worksheets(credentials_path, spreadsheet_id, filter_performance=False):
    return get_visible_worksheet_titles(credentials_path, spreadsheet_id, filter_performance=filter_performance)


@st.cache_data(ttl=300)
def fetch_worksheet_data(credentials_path, spreadsheet_id, worksheet_title):
    """Yan panel ZA listesi için sekme verisini önbellekli okur."""
    return read_visible_worksheet(credentials_path, spreadsheet_id, worksheet_title)


def _default_index(options, preferred):
    return options.index(preferred) if preferred in options else 0


def _candidate_index(options, month_name, year):
    probe = month_name.casefold()[:5]
    for index, option in enumerate(options):
        normalized = str(option).casefold()
        if str(year) in normalized and probe in normalized:
            return index
    return 0


def _za_number(value):
    """ZA değerini sayıya çevirir; okunamayan değerler sıralamanın en altına iner."""
    try:
        return float(str(value).strip().replace(",", ".").replace(" ", ""))
    except Exception:
        return float("-inf")


def _tab_matches_month(title, month_name, year):
    """Sekme başlığı seçilen ay (TR/EN/ES adları dahil) ve yıla göre eşleşir mi?"""
    normalized = str(title).casefold()
    if str(year) not in normalized:
        return False
    month_key = str(month_name).casefold()
    aliases = backend.MONTH_ALIASES.get(month_key, (month_key,))
    return any(re.search(rf"\b{re.escape(alias)}", normalized) for alias in aliases)


if selected_page == "📊 Aylık Perf Listesi":
    st.subheader("📊 Aylık Perf Listesi (Toplu)")
    st.caption(
        "Global Perf Tablosu'ndaki açık performans sekmelerinden yalnızca seçilen "
        "ay ve yıla ait olanlar taranır; kimin o ay ne kadar perf (ZA) aldığını "
        "gösterir. ZA girişi olmayan kişiler listelenmez."
    )
    if st.button("🔄 Yenile", key="bulk_perf_refresh"):
        fetch_worksheet_data.clear()
        fetch_visible_worksheets.clear()
        st.rerun()

    # Ay / yıl seçimi: yalnızca seçilen dönemin perf verisi okunur.
    perf_month_column, perf_year_column, perf_spacer = st.columns([2, 1, 2])
    with perf_month_column:
        perf_month = st.selectbox("Ay", MONTH_NAMES, index=datetime.now().month - 1, key="perf_month")
    with perf_year_column:
        year_options = [str(year) for year in range(datetime.now().year - 2, datetime.now().year + 2)]
        perf_year = st.selectbox(
            "Yıl", year_options, index=year_options.index(str(datetime.now().year)), key="perf_year"
        )

    try:
        bulk_spreadsheet_name = "Global Perf Tablosu" if "Global Perf Tablosu" in sheet_names else sheet_names[0]
        bulk_spreadsheet_id = spreadsheet_dict[bulk_spreadsheet_name]
        all_perf_tabs = fetch_visible_worksheets(active_json_path, bulk_spreadsheet_id, filter_performance=True)
        bulk_tabs = [tab for tab in all_perf_tabs if _tab_matches_month(tab, perf_month, perf_year)]
    except Exception as error:
        bulk_tabs = []
        st.error(f"❌ Sekme listesi alınamadı: {error}")
    if not bulk_tabs:
        st.info(f"🔍 {perf_month} {perf_year} dönemi için açık performans sekmesi bulunamadı.")
    else:
        parts = []
        skipped = []
        with st.spinner("Aylık perf sekmeleri okunuyor..."):
            for tab_title in bulk_tabs:
                try:
                    frame = fetch_worksheet_data(active_json_path, bulk_spreadsheet_id, tab_title)
                    summary, has_columns = get_member_za_summary(frame)
                    if not has_columns:
                        skipped.append(f"{tab_title} — Member ID veya ZA sütunu bulunamadı")
                        continue
                    if summary.empty:
                        continue
                    za_column = "ZA" if "ZA" in summary.columns else summary.columns[-1]
                    part = summary.rename(columns={za_column: "ZA"}).copy()
                    part.insert(0, "Sekme", tab_title)
                    part["_za_sort"] = part["ZA"].map(_za_number)
                    parts.append(part)
                except Exception as error:
                    skipped.append(f"{tab_title} — {error}")
        if skipped:
            with st.expander(f"⚠️ Atlanan sekmeler ({len(skipped)})"):
                for line in skipped:
                    st.caption(line)
        if not parts:
            st.info("Hiçbir sekmede ZA kaydı bulunamadı.")
        else:
            # Toplu sıralama: bölge/dil fark etmez — tüm sekmeler birleştirilip
            # en çok ZA alandan en az ZA alana sıralanır (yalnızca ZA alanlar).
            bulk_table = pd.concat(parts, ignore_index=True)
            bulk_table = bulk_table.sort_values(
                "_za_sort", ascending=False, kind="stable"
            ).reset_index(drop=True)
            monthly_summary = []
            for tab_title in bulk_tabs:
                rows = bulk_table[bulk_table["Sekme"] == tab_title]
                if rows.empty:
                    continue
                values = [float(value) for value in rows["_za_sort"] if value != float("-inf")]
                monthly_summary.append({
                    "Sekme": tab_title,
                    "Kişi": len(rows),
                    "Toplam ZA": sum(values),
                    "En yüksek ZA": max(values) if values else 0,
                    "Ortalama ZA": round(sum(values) / len(values), 1) if values else 0,
                })
            df_month = pd.DataFrame(monthly_summary)
            if not df_month.empty and "Toplam ZA" in df_month.columns:
                df_month = df_month.sort_values(
                    "Toplam ZA", ascending=False, kind="stable"
                ).reset_index(drop=True)

            group_cols = [col for col in bulk_table.columns if col not in ("Sekme", "ZA", "_za_sort")]
            group_frame = bulk_table.copy()
            for col in group_cols:
                # Aynı kişi farklı sekmelerde boş e-posta/NaN olarak bölünmesin.
                group_frame[col] = group_frame[col].fillna("").astype(str).str.strip()
            person_totals = (
                group_frame.groupby(group_cols, dropna=False, sort=False)["_za_sort"]
                .agg(Toplam_ZA="sum", Kaç_Ay="count")
                .reset_index()
                .rename(columns={"Toplam_ZA": "Toplam ZA", "Kaç_Ay": "Aldığı ay"})
                .sort_values("Toplam ZA", ascending=False, kind="stable")
                .reset_index(drop=True)
            )

            total_za = sum(float(value) for value in bulk_table["_za_sort"] if value != float("-inf"))
            st.caption(
                f"📈 Genel toplam: {total_za:,.0f} ZA · {len(bulk_table)} kayıt · "
                f"{len(person_totals)} kişi · {len(df_month)} sekme"
            )
            tab_month, tab_bulk, tab_person = st.tabs(
                ["📅 Aylık Özet", "📋 Toplu Liste", "👤 Kişi Toplamları"]
            )
            with tab_month:
                st.dataframe(df_month, hide_index=True, use_container_width=True)
            with tab_bulk:
                st.dataframe(bulk_table.drop(columns=["_za_sort"]), hide_index=True, use_container_width=True)
            with tab_person:
                st.dataframe(person_totals, hide_index=True, use_container_width=True)
            st.download_button(
                "📥 Toplu listeyi CSV indir",
                bulk_table.drop(columns=["_za_sort"]).to_csv(index=False).encode("utf-8-sig"),
                file_name="aylik_perf_listesi.csv",
                mime="text/csv",
            )

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
        # Rapor tablosunu Global Perf Tablosu'na sabitle
        perf_sheet_name = "Global Perf Tablosu" if "Global Perf Tablosu" in sheet_names else sheet_names[0]
        selected_report = st.selectbox(
            "Rapor Tablosu", [perf_sheet_name], index=0, disabled=True,
            help="Raporlama her zaman Global Perf Tablosu'na işlenir."
        )

    month_column, year_column, target_column = st.columns([1, 1, 2])
    with month_column:
        selected_month = st.selectbox("Ay", MONTH_NAMES, index=datetime.now().month - 1)
    with year_column:
        year_options = [str(year) for year in range(datetime.now().year - 1, datetime.now().year + 3)]
        selected_year = st.selectbox("Yıl", year_options, index=1)
    with target_column:
        try:
            report_worksheets = fetch_visible_worksheets(
                active_json_path, spreadsheet_dict[selected_report], filter_performance=True
            )
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
        progress_bar = st.progress(1, text="İşlem başlatılıyor... (%1)")
        log_box = None
        logs = []

        def log_callback(message):
            logs.append(f"> {message}")

        def update_progress(val, text=None):
            val = max(1, min(100, int(val)))
            status_text = text or f"İşlem sürüyor... (%{val})"
            progress_bar.progress(val, text=status_text)

        try:
            audit_log(
                current_user,
                "Rapor güncelleme başlattı",
                f"{selected_report} / {selected_target} ({selected_month} {selected_year})",
            )
            worker_kwargs = {
                "creds_input": active_json_path,
                "source_id": spreadsheet_dict[selected_source],
                "report_id": spreadsheet_dict[selected_report],
                "selected_year": selected_year,
                "selected_month": selected_month,
                "log_callback": log_callback,
                "progress_callback": update_progress,
            }
            if "target_worksheet_title" not in inspect.signature(QAReportWorker.__init__).parameters:
                st.error(
                    "❌ Bellekte eski bir backend.py sürümü var. Python, import edilen modülü "
                    "uygulama yeniden başlatılmadan yenilemez; bu yüzden işlem güvenlik için "
                    "başlatılmadı. Streamlit'i tamamen durdurup yeniden başlatın "
                    "(Ctrl+C → `streamlit run main.py`). Cloud'da: Manage app → Reboot."
                )
                st.stop()
            worker_kwargs["target_worksheet_title"] = selected_target
            worker = QAReportWorker(**worker_kwargs)
            report_data = worker.process()
            if report_data is None:
                audit_log(current_user, "Rapor güncelleme", "İşlem tamamlanamadı", "Başarısız")
                st.error("❌ Rapor güncellenemedi; bir hata oluştu.")
                if logs:
                    with st.expander("Detaylı Hata Günlüğü"):
                        st.code("\n".join(logs), language="text")
            else:
                progress_bar.progress(100, text="Tamamlandı! (%100)")
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
                fetch_worksheet_data.clear()
        except Exception as error:
            try:
                audit_log(current_user, "Rapor güncelleme hatası", str(error), "Başarısız")
            except Exception:
                pass
            st.error(f"❌ İşlem sırasında bir hata oluştu: {error}")
            if logs:
                with st.expander("Detaylı Hata Günlüğü"):
                    st.code("\n".join(logs), language="text")

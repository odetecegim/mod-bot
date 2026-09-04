import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone


MONTH_ALIASES = {
    "ocak": ("ocak", "january", "jan"), "şubat": ("şubat", "subat", "february", "feb"),
    "mart": ("mart", "march", "mar"), "nisan": ("nisan", "april", "apr"),
    "mayıs": ("mayıs", "mayis", "may"), "haziran": ("haziran", "june", "jun"),
    "temmuz": ("temmuz", "july", "jul"), "ağustos": ("ağustos", "agustos", "august", "aug"),
    "eylül": ("eylül", "eylul", "september", "sep"), "ekim": ("ekim", "october", "oct"),
    "kasım": ("kasım", "kasim", "november", "nov"), "aralık": ("aralık", "aralik", "december", "dec"),
}


def _normalized(value):
    return str(value or "").strip().casefold()


def _is_hidden(worksheet):
    is_hidden = getattr(worksheet, "is_hidden", None)
    if is_hidden is not None:
        return bool(is_hidden)
    return bool(getattr(worksheet, "_properties", {}).get("hidden", False))


def _is_internal_log_name(title):
    return _normalized(title) in {"modbot.log", "modbot log"}


def _find_column(columns, names=(), contains=()):
    for column in columns:
        normalized = _normalized(column)
        if normalized in names or any(value in normalized for value in contains):
            return column
    return None


def _email_column(columns):
    return _find_column(
        columns,
        names={"email", "e-mail", "e posta", "e-posta", "eposta", "mail"},
        contains=("email", "e-posta", "eposta"),
    )


def _unique_headers(headers):
    used_headers = set()
    unique_headers = []
    for index, header in enumerate(headers, start=1):
        base_header = str(header).strip() or f"Adsız Sütun {index}"
        candidate = base_header
        duplicate_number = 2
        while candidate in used_headers:
            candidate = f"{base_header} ({duplicate_number})"
            duplicate_number += 1
        used_headers.add(candidate)
        unique_headers.append(candidate)
    return unique_headers


def _month_terms(month_name):
    clean_month = _normalized(month_name)
    return MONTH_ALIASES.get(clean_month, (clean_month,))


def _matches_period(worksheet, month_name, year, language=None):
    title = _normalized(worksheet.title)
    if str(year).strip() not in title or not any(term in title for term in _month_terms(month_name)):
        return False
    language = _normalized(language)
    return not language or language == "tümü" or language in title


def get_available_spreadsheets(creds_input):
    spreadsheets = {"all": {}}
    try:
        client = _authorized_client(creds_input)
        for spreadsheet in client.openall():
            if _is_internal_log_name(spreadsheet.title):
                continue
            spreadsheets["all"][spreadsheet.title] = spreadsheet.id
    except Exception as error:
        print(f"Spreadsheet listeleme hatası: {error}")
    return spreadsheets


def _authorized_client(creds_input):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    if isinstance(creds_input, dict):
        credentials = Credentials.from_service_account_info(creds_input, scopes=scopes)
    else:
        credentials = Credentials.from_service_account_file(creds_input, scopes=scopes)
    return gspread.authorize(credentials)


def get_visible_worksheet_titles(creds_input, spreadsheet_id):
    workbook = _authorized_client(creds_input).open_by_key(spreadsheet_id)
    return [
        worksheet.title
        for worksheet in workbook.worksheets()
        if not _is_hidden(worksheet) and not _is_internal_log_name(worksheet.title)
    ]


def read_visible_worksheet(creds_input, spreadsheet_id, worksheet_title):
    workbook = _authorized_client(creds_input).open_by_key(spreadsheet_id)
    worksheet = workbook.worksheet(worksheet_title)
    if _is_hidden(worksheet) or _is_internal_log_name(worksheet.title):
        raise ValueError("Bu sekme araç içinden görüntülenemez veya düzenlenemez.")
    values = worksheet.get_all_values(value_render_option="FORMULA")
    if not values:
        return pd.DataFrame()
    original_headers = [str(header).strip() for header in values[0]]
    headers = _unique_headers(original_headers)
    data = pd.DataFrame(values[1:], columns=headers)
    data.attrs["renamed_headers"] = headers != original_headers
    return data


def update_visible_worksheet(creds_input, spreadsheet_id, worksheet_title, data):
    workbook = _authorized_client(creds_input).open_by_key(spreadsheet_id)
    worksheet = workbook.worksheet(worksheet_title)
    if _is_hidden(worksheet) or _is_internal_log_name(worksheet.title):
        raise ValueError("Bu sekme araç içinden düzenlenemez.")
    worksheet.clear()
    worksheet.update(
        range_name="A1",
        values=[data.columns.tolist()] + data.fillna("").astype(str).values.tolist(),
    )


def get_member_za_summary(data):
    member_id_column = _find_column(
        data.columns,
        names={"member id", "memberid", "üye id", "uye id", "discord id"},
        contains=("member id", "memberid", "üye id", "uye id", "discord id"),
    )
    user_column = _find_column(data.columns, names={"nick", "personel", "kullanıcı", "ad soyad"})
    email_column = _email_column(data.columns)
    za_column = _find_column(data.columns, names={"za"})
    selected_columns = [column for column in (user_column, email_column, member_id_column, za_column) if column]
    return data[selected_columns].copy(), bool(member_id_column and za_column)


def append_audit_log(creds_input, spreadsheet_id, worksheet_title, user_name, action,
                     details="", status="Başarılı"):
    workbook = _authorized_client(creds_input).open_by_key(spreadsheet_id)
    try:
        worksheet = workbook.worksheet(worksheet_title)
    except gspread.WorksheetNotFound:
        worksheet = workbook.add_worksheet(title=worksheet_title, rows="1000", cols="7")
        worksheet.update(
            range_name="A1",
            values=[["Tarih", "Kullanıcı", "İşlem", "Detay", "Durum", "Tablo ID", "Sekme"]],
        )
    if _is_hidden(worksheet):
        raise ValueError("Log sekmesi gizli olmamalıdır.")
    worksheet.append_row([
        datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        user_name,
        action,
        details,
        status,
        spreadsheet_id,
        worksheet_title,
    ])


def _find_target_worksheet(wb, language, month_name, year, log_callback=print, create_if_missing=True, source_columns=None):
    candidates = [
        worksheet for worksheet in wb.worksheets()
        if not _is_hidden(worksheet) and "rapor" not in _normalized(worksheet.title)
    ]
    for worksheet in candidates:
        if _matches_period(worksheet, month_name, year, language):
            return worksheet
    for worksheet in candidates:
        if _matches_period(worksheet, month_name, year):
            log_callback(f"⚠️ Tam dil eşleşmesi bulunamadı; [{worksheet.title}] sekmesi kullanılıyor.")
            return worksheet
    if not create_if_missing:
        return None

    title = f"{language} {month_name} {year}"
    log_callback(f"🆕 '{title}' sekmesi bulunamadı, yeni oluşturuluyor...")
    worksheet = wb.add_worksheet(title=title, rows="1000", cols=str(max(len(source_columns or []), 10)))
    if source_columns:
        worksheet.update(range_name="A1", values=[list(source_columns)])
    return worksheet


class QAReportWorker:
    def __init__(self, creds_input, source_id, report_id, selected_year, selected_month,
                 selected_language="ENG", log_callback=print, progress_callback=None):
        self.creds_input = creds_input
        self.source_id = source_id
        self.report_id = report_id
        self.selected_year = selected_year
        self.selected_month = selected_month
        self.selected_language = selected_language
        self.log_callback = log_callback
        self.progress_callback = progress_callback or (lambda value: None)
        self.used_worksheet_title = None

    def process(self):
        try:
            self.log_callback("⚙️ Google Sheets bağlantısı kuruluyor...")
            self.progress_callback(10)
            source_workbook = _authorized_client(self.creds_input).open_by_key(self.source_id)

            report_counts = {}
            display_names = {}
            scanned_sheets = 0
            for worksheet in source_workbook.worksheets():
                if _is_hidden(worksheet):
                    self.log_callback(f"🙈 Gizli sekme atlandı: [{worksheet.title}]")
                    continue
                if not _matches_period(worksheet, self.selected_month, self.selected_year, self.selected_language):
                    self.log_callback(f"⏭️ Seçili dönem dışındaki açık sekme atlandı: [{worksheet.title}]")
                    continue

                scanned_sheets += 1
                self.log_callback(f"✅ Açık sekme taranıyor: [{worksheet.title}]")
                values = worksheet.get_all_values()
                if len(values) < 2:
                    continue
                headers = [str(header).strip() for header in values[0]]
                email_column = _email_column(headers)
                if not email_column:
                    self.log_callback(f"⚠️ [{worksheet.title}] sekmesinde e-posta sütunu bulunamadı; atlandı.")
                    continue

                sheet_data = pd.DataFrame(values[1:], columns=headers)
                name_column = _find_column(
                    headers,
                    names={"nick", "personel", "kullanıcı", "ad soyad", "qa_member"},
                )
                for _, row in sheet_data.iterrows():
                    email = _normalized(row[email_column])
                    if not email or email in {"nan", "none", "email", "e-mail", "mail"}:
                        continue
                    report_counts[email] = report_counts.get(email, 0) + 1
                    if name_column and str(row[name_column]).strip():
                        display_names[email] = str(row[name_column]).strip()

            self.log_callback(f"📊 {scanned_sheets} açık dönem sekmesinden {len(report_counts)} e-posta için rapor sayısı toplandı.")
            self.progress_callback(45)

            report_workbook = _authorized_client(self.creds_input).open_by_key(self.report_id)
            report_sheet = _find_target_worksheet(
                report_workbook, self.selected_language, self.selected_month, self.selected_year, self.log_callback
            )
            self.used_worksheet_title = report_sheet.title
            values = report_sheet.get_all_values()
            if values:
                headers = [str(header).strip() for header in values[0]]
                report_data = pd.DataFrame(values[1:], columns=headers)
            else:
                headers = ["Nick", "E-posta", "Hata bildirimi", "Toplam", "ZA"]
                report_data = pd.DataFrame(columns=headers)

            email_column = _email_column(headers)
            user_column = _find_column(headers, names={"nick", "personel", "kullanıcı", "ad soyad"}) or headers[0]
            if not email_column:
                email_column = "E-posta"
                report_data[email_column] = ""
                headers.append(email_column)
            report_column = _find_column(headers, names={"hata bildirimi", "hata raporu"}, contains=("hata",))
            if not report_column:
                report_column = "Hata bildirimi"
                report_data[report_column] = 0
                headers.append(report_column)

            report_data[email_column] = report_data[email_column].map(_normalized)
            known_emails = set(report_data[email_column])
            for email in report_counts:
                if email not in known_emails:
                    new_row = {column: "" for column in report_data.columns}
                    new_row[email_column] = email
                    new_row[user_column] = display_names.get(email, email)
                    report_data = pd.concat([report_data, pd.DataFrame([new_row])], ignore_index=True)

            report_data[report_column] = report_data[email_column].map(report_counts).fillna(0).astype(int)
            score_columns = [column for column in report_data.columns if _normalized(column) in {
                "zula pass", "0 kul. testi", "genel check", "hata bildirimi", "öneri bildirimi",
                "discord pc", "hakemlik", "diğer/kanaat"
            }]
            for column in score_columns:
                report_data[column] = pd.to_numeric(report_data[column].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
            if score_columns:
                report_data["Toplam"] = report_data[score_columns].sum(axis=1).astype(int)
                report_data["ZA"] = report_data["Toplam"] * 500

            self.progress_callback(85)
            output = report_data.fillna("")
            report_sheet.clear()
            report_sheet.update(range_name="A1", values=[output.columns.tolist()] + output.astype(str).values.tolist())
            self.progress_callback(100)
            self.log_callback(f"✅ E-posta eşleştirmesi [{report_sheet.title}] sekmesine yazıldı.")
            return report_data
        except Exception as error:
            self.log_callback(f"❌ Rapor işleme hatası: {error}")
            return None


def process_za_and_insert_month(main_ws, target_month_name, selected_year=2026, selected_language="ENG", log_func=print):
    try:
        target_ws = _find_target_worksheet(main_ws.spreadsheet, selected_language, target_month_name, selected_year, log_func, False)
        if not target_ws:
            log_func("❌ Hedef açık sekme bulunamadı!")
            return False
        raw_main = main_ws.get_all_values()
        if len(raw_main) < 2:
            log_func("⚠️ Ana çalışma sayfasında işlenecek veri bulunamadı!")
            return False
        main_data = pd.DataFrame(raw_main[1:], columns=[str(header).strip() for header in raw_main[0]])
        user_column = _find_column(main_data.columns, names={"nick", "personel", "kullanıcı", "ad soyad"}) or main_data.columns[0]
        za_column = "ZA" if "ZA" in main_data.columns else main_data.columns[-1]
        target_rows = target_ws.get_all_values()
        headers = target_rows[0] if target_rows else [user_column]
        za_header = f"{target_month_name} ZA"
        if za_header not in headers:
            headers.append(za_header)
        za_index = headers.index(za_header)
        za_by_user = dict(zip(main_data[user_column].astype(str).str.strip(), main_data[za_column].astype(str).str.strip()))
        rows = [headers]
        for row in target_rows[1:]:
            row.extend([""] * (len(headers) - len(row)))
            if row[0].strip() in za_by_user:
                row[za_index] = za_by_user[row[0].strip()]
            rows.append(row)
        target_ws.clear()
        target_ws.update(range_name="A1", values=rows)
        log_func(f"✅ Veriler başarıyla [{target_ws.title}] sekmesine yazıldı!")
        return True
    except Exception as error:
        log_func(f"❌ İşlem Hatası: {error}")
        return False

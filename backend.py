import difflib
import re
import unicodedata

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

MONTH_NUMBERS = {month_name: index for index, month_name in enumerate(MONTH_ALIASES, start=1)}

# Kaynak (form) sekmelerini hedef puan sütunlarına bağlayan kategoriler.
CATEGORY_LABELS = {
    "mission_card": "G. Kartı / Zula Pass",
    "new_user_test": "0 Kul. TESTİ",
    "general_check": "Genel Check",
    "error_report": "Hata bildirimi",
}

# Kaynak sekme başlığından kategori çıkarımı (üç dildeki form adları).
CATEGORY_TITLE_KEYWORDS = (
    ("new_user_test", ("0 kullanıcı", "0 kullanici", "0 kul", "new user test", "usuario nuevo", "novo usu")),
    ("mission_card", ("mission", "misión", "missao", "missão", "zula pass", "kart", "cart", "görev", "gorev", "tarea", "pase de batalla", "passe de batalha")),
    ("general_check", ("genel", "general", "geral", "revision", "revisión", "revisao", "revisão", "verificacao", "verificação", "kontrol", "check")),
    ("error_report", ("hata", "error", "erro", "relatorio", "relatório", "reporte", "relat")),
)

# Hedef (rapor) sekmesindeki sütun adlarından kategori çıkarımı.
REPORT_COLUMN_KEYWORDS = {
    "mission_card": ("zula pass", "zula", "kart", "pass", "mission", "misyon", "görev", "gorev", "pase"),
    "new_user_test": ("0 kul", "0 kullan", "new user", "yeni kullanıcı", "yeni kullanici", "usuario nuevo", "novo usu"),
    "general_check": ("genel check", "general check", "genel", "general", "geral", "verificação", "verificacao", "revisión"),
    "error_report": ("hata bildirimi", "hata raporu", "error report", "reporte de error", "relatorio", "error", "erro"),
}

DATE_HEADER_KEYWORDS = ("zaman", "timestamp", "tarih", "date", "fecha", "data em que", "marca de tiempo")
NICK_HEADER_KEYWORDS = ("nick", "apodo", "apelido", "personaje", "personagem", "character")
NAME_HEADER_KEYWORDS = (
    "name-surname", "nome e sobrenome", "nombre y apellido", "ad soyad", "isim soyisim",
    "personel ad", "personel", "nombre del personal",
)

# Puan sütunu olmayan (kimlik/özet) sütunlar.
NON_SCORE_EXACT = {
    "", "member id", "memberid", "ad soyad", "isim soyisim", "nick",
    "e-posta", "e posta", "e mail", "eposta", "email", "mail",
    "toplam", "za", "not", "notlar", "not:", "notes",
}
NON_SCORE_CONTAINS = ("member id", "ad soyad", "isim soyisim", "e-posta", "eposta", "email", "toplam", "nick")

# Önceki hatalı çalışmaların sütunlara yazdığı "0.0" metinleri temizlenir.
ARTIFACT_ZERO_TEXTS = {"0.0", "0,0"}

_DATE_DMY_RE = re.compile(r"^\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})")
_DATE_YMD_RE = re.compile(r"^\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")


def _normalized(value):
    return str(value or "").strip().casefold()


def _cell(row, index):
    if index is None or index < 0 or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _month_number(month_name):
    clean_month = _normalized(month_name)
    for index, month_key in enumerate(MONTH_ALIASES, start=1):
        if clean_month == month_key or clean_month in MONTH_ALIASES[month_key]:
            return index
    return None


def _ascii_casefold(value):
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(character for character in decomposed if not unicodedata.combining(character)).casefold()


def _name_tokens(value):
    """İsim karşılaştırması için aksan/boşluk bağımsız kelime kümesi üretir."""
    return frozenset(re.findall(r"[a-z0-9]+", _ascii_casefold(value)))


def _nick_key(value):
    """Nick karşılaştırması için sadece harf/rakam bırakır (çok kısa değerler eşleşmez)."""
    key = re.sub(r"[^a-z0-9]", "", _ascii_casefold(value))
    return key if len(key) >= 3 else ""


def _name_match(source_tokens, report_tokens):
    """İki isim kümesi aynı kişiye mi ait? (kelime alt kümesi veya yazım hatası toleransı)"""
    if not source_tokens or not report_tokens:
        return False
    if source_tokens <= report_tokens or report_tokens <= source_tokens:
        return True
    common_tokens = source_tokens & report_tokens
    if not common_tokens:
        return False
    if len(source_tokens) <= len(report_tokens):
        shorter, longer = source_tokens, report_tokens
    else:
        shorter, longer = report_tokens, source_tokens
    for token in longer - common_tokens:
        best_ratio = max(difflib.SequenceMatcher(None, token, candidate).ratio() for candidate in shorter)
        if best_ratio < 0.75:
            return False
    return True


def _looks_like_date(value):
    text = str(value or "").strip()
    if not text:
        return False
    return bool(_DATE_DMY_RE.match(text) or _DATE_YMD_RE.match(text))


def _date_parts(value):
    """'16.09.2026', '2026-09-16' gibi değerlerden (yıl, ay) döndürür."""
    text = str(value or "").strip()
    if not text:
        return None
    match = _DATE_YMD_RE.match(text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
    else:
        match = _DATE_DMY_RE.match(text)
        if not match:
            return None
        month, year = int(match.group(2)), int(match.group(3))
        if year < 100:
            year += 2000
    if not 1 <= month <= 12 or not 1990 <= year <= 2100:
        return None
    return year, month


def _index_of_keyword(columns, keywords):
    for index, column in enumerate(columns):
        normalized = _normalized(column)
        if any(keyword in normalized for keyword in keywords):
            return index
    return None


def _find_person_columns(headers):
    """Personel adı ve nick sütunlarının indekslerini döndürür."""
    nick_index = _index_of_keyword(headers, NICK_HEADER_KEYWORDS)
    name_index = _index_of_keyword(headers, NAME_HEADER_KEYWORDS)
    if name_index is None:
        for index, header in enumerate(headers):
            if index == nick_index:
                continue
            if any(term in _normalized(header) for term in ("nombre", "nome", "name", "soyad", "apellido", "sobrenome")):
                name_index = index
                break
    return name_index, nick_index


def _find_date_column_index(headers, rows, skip_indexes=()):
    """Önce başlık adına, bulunamazsa verinin tarih formatına göre tarih sütununu bulur."""
    by_header = _index_of_keyword(headers, DATE_HEADER_KEYWORDS)
    if by_header is not None and by_header not in skip_indexes:
        return by_header
    best_index, best_hits = None, 0
    for index in range(len(headers)):
        if index in skip_indexes:
            continue
        checked, hits = 0, 0
        for row in rows[:300]:
            value = _cell(row, index)
            if not value:
                continue
            checked += 1
            if _looks_like_date(value):
                hits += 1
        if checked < 3 or hits < 3:
            continue
        if hits / checked >= 0.6 and hits > best_hits:
            best_index, best_hits = index, hits
    return best_index


def _category_for_title(title):
    normalized = _normalized(title)
    for category, keywords in CATEGORY_TITLE_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return category
    return None


def _is_non_score_column(column):
    normalized = _normalized(column)
    if normalized in NON_SCORE_EXACT:
        return True
    return any(term in normalized for term in NON_SCORE_CONTAINS)


def _map_report_columns(headers):
    """Kategori -> hedef sütun indeksi eşlemesini üretir."""
    column_map = {}
    used_indexes = set()
    for category in ("mission_card", "new_user_test", "general_check", "error_report"):
        for index, header in enumerate(headers):
            if index in used_indexes:
                continue
            if any(keyword in _normalized(header) for keyword in REPORT_COLUMN_KEYWORDS[category]):
                column_map[category] = index
                used_indexes.add(index)
                break
    return column_map


def _column_letter(index):
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _is_artifact_zero(value):
    """Sadece metin olarak yazılmış '0.0' artıklarını yakalar (gerçek sayısal 0'lar etkilenmez)."""
    return isinstance(value, str) and value.strip() in ARTIFACT_ZERO_TEXTS


def _to_number(value):
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _display_number(value):
    """'34.000' / '11.500' gibi görüntülenen sayıları Python sayısına çevirir (sadece özet gösterimi için)."""
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", text) or re.fullmatch(r"-?\d{1,3}(,\d{3})+", text):
        text = text.replace(".", "").replace(",", "")
    try:
        number = float(text.replace(",", "."))
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def _find_report_row(row_records, tokens, nick):
    """Kaynak kaydına karşılık gelen hedef satırı bulur (dolu satırlar tercih edilir)."""
    best_index = None
    for index, (row_tokens, row_nick, has_identity_cell) in enumerate(row_records):
        if nick and row_nick and nick == row_nick:
            matched = True
        else:
            matched = _name_match(tokens, row_tokens)
        if not matched:
            continue
        if best_index is None or (has_identity_cell and not row_records[best_index][2]):
            best_index = index
        if row_records[best_index][2]:
            break
    return best_index


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
    if not language:
        return True
    language = _normalized(language)
    return language == "tümü" or language in title


def get_available_spreadsheets(creds_input):
    """Erişilebilir tabloları döndürür. Bir hata olursa sessizce yutmak yerine
    fırlatır, böylece arayüz gerçek nedeni kullanıcıya gösterebilir."""
    spreadsheets = {"all": {}}
    client = _authorized_client(creds_input)
    for spreadsheet in client.openall():
        if _is_internal_log_name(spreadsheet.title):
            continue
        spreadsheets["all"][spreadsheet.title] = spreadsheet.id
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
        values=[data.columns.tolist()] + data.fillna("").astype(str).values.tolist(),
        range_name="A1",
    )


def get_member_za_summary(data):
    member_id_column = _find_column(
        data.columns,
        names={"member id", "memberid", "üye id", "uye id", "discord id"},
        contains=("member id", "memberid", "üye id", "uye id", "discord id"),
    )
    rename_columns = {}
    if member_id_column is None and len(data.columns):
        # Başlığı boş bırakılmış ilk sütun genelde Member ID olur (ör. ESP/POR sekmeleri).
        first_column = data.columns[0]
        normalized_first = _normalized(first_column)
        if not normalized_first or normalized_first.startswith("adsız sütun"):
            member_id_column = first_column
            rename_columns[first_column] = "Member ID"
    user_column = _find_column(data.columns, names={"nick", "personel", "kullanıcı", "ad soyad"})
    email_column = _email_column(data.columns)
    za_column = _find_column(data.columns, names={"za"})
    selected_columns = [column for column in (user_column, email_column, member_id_column, za_column) if column]
    summary = data[selected_columns].copy()
    if rename_columns:
        summary = summary.rename(columns=rename_columns)
    return summary, bool(member_id_column and za_column)


def append_audit_log(creds_input, spreadsheet_id, worksheet_title, user_name, action,
                     details="", status="Başarılı"):
    workbook = _authorized_client(creds_input).open_by_key(spreadsheet_id)
    try:
        worksheet = workbook.worksheet(worksheet_title)
    except gspread.WorksheetNotFound:
        worksheet = workbook.add_worksheet(title=worksheet_title, rows=1000, cols=7)
        worksheet.update(
            values=[["Tarih", "Kullanıcı", "İşlem", "Detay", "Durum", "Tablo ID", "Sekme"]],
            range_name="A1",
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
    if language:
        for worksheet in candidates:
            if _matches_period(worksheet, month_name, year, language):
                return worksheet
    for worksheet in candidates:
        if _matches_period(worksheet, month_name, year):
            if language:
                log_callback(f"⚠️ Tam dil eşleşmesi bulunamadı; [{worksheet.title}] sekmesi kullanılıyor.")
            return worksheet
    if not create_if_missing:
        return None

    title = f"{language} {month_name} {year}".strip() if language else f"{month_name} {year}"
    log_callback(f"🆕 '{title}' sekmesi bulunamadı, yeni oluşturuluyor...")
    worksheet = wb.add_worksheet(title=title, rows=1000, cols=max(len(source_columns or []), 10))
    if source_columns:
        worksheet.update(values=[list(source_columns)], range_name="A1")
    return worksheet


class QAReportWorker:
    def __init__(self, creds_input, source_id, report_id, selected_year, selected_month,
                 selected_language=None, log_callback=print, progress_callback=None,
                 target_worksheet_title=None):
        self.creds_input = creds_input
        self.source_id = source_id
        self.report_id = report_id
        self.selected_year = selected_year
        self.selected_month = selected_month
        self.selected_language = selected_language
        self.target_worksheet_title = target_worksheet_title
        self.log_callback = log_callback
        self.progress_callback = progress_callback or (lambda value: None)
        self.used_worksheet_title = None

    def _collect_source_records(self, client, target_month, target_year):
        """Kaynak form sekmelerini (tarih sütununa göre) tarar ve kategori bazlı kayıt toplar."""
        source_workbook = client.open_by_key(self.source_id)
        records = {category: [] for category in CATEGORY_LABELS}
        scanned_sheets = 0
        for worksheet in source_workbook.worksheets():
            if _is_hidden(worksheet):
                self.log_callback(f"🙈 Gizli sekme atlandı: [{worksheet.title}]")
                continue
            category = _category_for_title(worksheet.title)
            if not category:
                self.log_callback(f"⏭️ Kategori belirlenemedi, atlandı: [{worksheet.title}]")
                continue
            values = worksheet.get_all_values()
            if len(values) < 2:
                self.log_callback(f"⚠️ [{worksheet.title}] sekmesinde veri yok; atlandı.")
                continue
            headers = [str(header).strip() for header in values[0]]
            data_rows = [row for row in values[1:] if any(str(cell).strip() for cell in row)]
            name_index, nick_index = _find_person_columns(headers)
            date_index = _find_date_column_index(headers, data_rows, skip_indexes=(name_index, nick_index))
            if date_index is None:
                self.log_callback(f"⚠️ [{worksheet.title}] tarih sütunu bulunamadı; atlandı.")
                continue
            if name_index is None and nick_index is None:
                self.log_callback(f"⚠️ [{worksheet.title}] personel adı/nick sütunu bulunamadı; atlandı.")
                continue
            selected = 0
            for row in data_rows:
                if _date_parts(_cell(row, date_index)) != (target_year, target_month):
                    continue
                name = _cell(row, name_index)
                nick = _cell(row, nick_index)
                if not _name_tokens(name) and not _nick_key(nick):
                    continue
                records[category].append((_name_tokens(name), _nick_key(nick), name, nick))
                selected += 1
            scanned_sheets += 1
            self.log_callback(
                f"📥 [{worksheet.title}] → {CATEGORY_LABELS[category]}: {selected} kayıt "
                f"({self.selected_month} {self.selected_year})"
            )
        self.log_callback(
            f"📊 {scanned_sheets} kaynak sekme tarandı, toplam "
            f"{sum(len(entries) for entries in records.values())} kayıt bulundu."
        )
        return records

    def process(self, dry_run=False):
        try:
            self.log_callback("⚙️ Google Sheets bağlantısı kuruluyor...")
            self.progress_callback(10)
            target_month = _month_number(self.selected_month)
            if not target_month:
                self.log_callback(f"❌ '{self.selected_month}' ayı tanınamadı.")
                return None
            try:
                target_year = int(str(self.selected_year).strip())
            except ValueError:
                self.log_callback(f"❌ '{self.selected_year}' yılı geçersiz.")
                return None

            client = _authorized_client(self.creds_input)
            records = self._collect_source_records(client, target_month, target_year)
            if sum(len(entries) for entries in records.values()) == 0:
                self.log_callback("⚠️ Seçilen dönem için kaynak sekmelerde hiç kayıt bulunamadı; hedef sekme değiştirilmedi.")
                return None
            self.progress_callback(45)

            report_workbook = client.open_by_key(self.report_id)
            if self.target_worksheet_title:
                report_sheet = report_workbook.worksheet(self.target_worksheet_title)
            else:
                report_sheet = _find_target_worksheet(
                    report_workbook, self.selected_language, self.selected_month, self.selected_year, self.log_callback
                )
            self.used_worksheet_title = report_sheet.title
            self.log_callback(f"🎯 Hedef sekme: [{report_sheet.title}]")

            report_formulas = report_sheet.get_all_values(value_render_option="FORMULA")
            if not report_formulas:
                self.log_callback(f"❌ [{report_sheet.title}] sekmesi boş.")
                return None
            headers = [str(header) for header in report_formulas[0]]
            data_rows = report_formulas[1:]
            last_content_index = max(
                (index for index, row in enumerate(data_rows) if any(str(cell).strip() for cell in row)),
                default=-1,
            )
            data_rows = data_rows[: last_content_index + 1] if last_content_index >= 0 else []

            name_index, nick_index = _find_person_columns(headers)
            if name_index is None and nick_index is None:
                self.log_callback(f"❌ [{report_sheet.title}] sekmesinde 'Ad Soyad' veya 'Nick' sütunu bulunamadı.")
                return None
            column_map = _map_report_columns(headers)
            if not column_map:
                self.log_callback(f"❌ [{report_sheet.title}] sekmesinde eşleşen puan sütunu bulunamadı.")
                return None
            self.log_callback("🎯 Sütun eşleşmeleri: " + " | ".join(
                f"{CATEGORY_LABELS[category]} → {headers[index] or _column_letter(index)}"
                for category, index in column_map.items()
            ))
            score_indexes = [index for index, header in enumerate(headers) if not _is_non_score_column(header)]
            toplam_index = next((index for index, header in enumerate(headers) if _normalized(header) == "toplam"), None)
            za_index = next((index for index, header in enumerate(headers) if _normalized(header) == "za"), None)

            row_records = [
                (_name_tokens(_cell(row, name_index)), _nick_key(_cell(row, nick_index)), bool(_cell(row, 0)))
                for row in data_rows
            ]
            pending = {}
            unmatched = {category: [] for category in CATEGORY_LABELS}
            for category in CATEGORY_LABELS:
                entries = records[category]
                column_index = column_map.get(category)
                if not entries:
                    continue
                if column_index is None:
                    self.log_callback(
                        f"⚠️ {CATEGORY_LABELS[category]} için hedef sütun bulunamadı; {len(entries)} kayıt atlandı."
                    )
                    continue
                counts = {}
                for tokens, nick, name, raw_nick in entries:
                    row_index = _find_report_row(row_records, tokens, nick)
                    if row_index is None:
                        unmatched[category].append((name, raw_nick, tokens, nick))
                        continue
                    counts[row_index] = counts.get(row_index, 0) + 1
                for row_index, count in counts.items():
                    pending.setdefault(row_index, {})[column_index] = count
                self.log_callback(
                    f"🔗 {CATEGORY_LABELS[category]}: {sum(counts.values())} kayıt {len(counts)} satıra eşleşti."
                )

            cleaned = 0
            for row_index, row in enumerate(data_rows):
                for column_index in score_indexes:
                    if column_index in pending.get(row_index, {}):
                        continue
                    if _is_artifact_zero(row[column_index] if column_index < len(row) else ""):
                        pending.setdefault(row_index, {})[column_index] = ""
                        cleaned += 1
            if cleaned:
                self.log_callback(f"🧹 Önceki hatalı çalışmadan kalan {cleaned} adet '0.0' metni temizlendi.")

            # Toplam ve ZA sütunlarına ASLA yazılmaz: bu sütunlar kullanıcıya/sekme
            # formüllerine aittir, raporlama sadece puan sütunlarını günceller.
            new_entries = {}
            for category, items in unmatched.items():
                column_index = column_map.get(category)
                if column_index is None:
                    continue
                for name, raw_nick, tokens, nick in items:
                    entry = new_entries.setdefault((tokens, nick), {"counts": {}, "name": name, "nick": raw_nick})
                    if not entry["name"] and name:
                        entry["name"] = name
                    if not entry["nick"] and raw_nick:
                        entry["nick"] = raw_nick
                    entry["counts"][column_index] = entry["counts"].get(column_index, 0) + 1

            self.progress_callback(85)
            appended_names = []
            if not dry_run:
                updates = []
                for row_index in sorted(pending):
                    for column_index in sorted(pending[row_index]):
                        if column_index in (toplam_index, za_index):
                            continue
                        updates.append({
                            "range": f"{_column_letter(column_index)}{row_index + 2}",
                            "values": [[pending[row_index][column_index]]],
                        })
                next_row_index = len(data_rows)
                for entry in new_entries.values():
                    sheet_row = next_row_index + 2
                    row_values = [""] * len(headers)
                    if name_index is not None and entry["name"]:
                        row_values[name_index] = entry["name"]
                    if nick_index is not None and entry["nick"]:
                        row_values[nick_index] = entry["nick"]
                    for column_index, count in entry["counts"].items():
                        if column_index in (toplam_index, za_index):
                            continue
                        row_values[column_index] = count
                    updates.append({
                        "range": f"A{sheet_row}:{_column_letter(len(headers) - 1)}{sheet_row}",
                        "values": [row_values],
                    })
                    appended_names.append(entry["name"] or entry["nick"])
                    next_row_index += 1
                if updates:
                    try:
                        for start in range(0, len(updates), 100):
                            report_sheet.batch_update(updates[start:start + 100], value_input_option="USER_ENTERED")
                    except Exception as error:
                        self.log_callback(f"❌ Sekmeye yazma hatası: {error}")
                        return None

            display_headers = _unique_headers(headers)
            current_values = None
            try:
                current_values = report_sheet.get_all_values()
            except Exception as error:
                self.log_callback(f"⚠️ Güncel değerler okunamadı: {error}")

            display_rows = []
            for row_index, row in enumerate(data_rows):
                display_row = [row[column] if column < len(row) else "" for column in range(len(headers))]
                for column_index, value in pending.get(row_index, {}).items():
                    display_row[column_index] = value
                if not dry_run and current_values and row_index + 1 < len(current_values):
                    sheet_row = current_values[row_index + 1]
                    for column_index in (toplam_index, za_index):
                        if column_index is not None and column_index < len(sheet_row):
                            display_row[column_index] = sheet_row[column_index]
                if score_indexes:
                    computed_total = sum(_to_number(display_row[column]) for column in score_indexes)
                    for column_index, multiplier in ((toplam_index, 1), (za_index, 500)):
                        if column_index is None:
                            continue
                        current = str(display_row[column_index]).strip()
                        if current and not current.startswith("="):
                            display_row[column_index] = _display_number(display_row[column_index])
                        else:
                            display_row[column_index] = int(computed_total * multiplier)
                display_rows.append(display_row)
            for entry in new_entries.values():
                display_row = [""] * len(headers)
                if name_index is not None and entry["name"]:
                    display_row[name_index] = entry["name"]
                if nick_index is not None and entry["nick"]:
                    display_row[nick_index] = entry["nick"]
                total = 0
                for column_index, count in entry["counts"].items():
                    display_row[column_index] = count
                    total += count
                if toplam_index is not None:
                    display_row[toplam_index] = int(total)
                if za_index is not None:
                    display_row[za_index] = int(total * 500)
                display_rows.append(display_row)

            self.progress_callback(100)
            state = "hesaplandı (yazılmadı)" if dry_run else "yazıldı"
            self.log_callback(
                f"✅ [{report_sheet.title}] sekmesi: {len(pending)} satır hücresi güncellendi, "
                f"{len(new_entries)} yeni satır {state}. Toplam/ZA sütunlarına dokunulmadı."
            )
            if appended_names:
                self.log_callback(
                    "➕ Hedef listede bulunmayan kayıtlar için yeni satır açıldı (Toplam/ZA boş bırakıldı): "
                    + ", ".join(sorted(name for name in appended_names if name))
                )
            return pd.DataFrame(display_rows, columns=display_headers)
        except Exception as error:
            self.log_callback(f"❌ Rapor işleme hatası: {error}")
            return None


def process_za_and_insert_month(main_ws, target_month_name, selected_year=2026, selected_language=None, log_func=print):
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
        target_ws.update(values=rows, range_name="A1")
        log_func(f"✅ Veriler başarıyla [{target_ws.title}] sekmesine yazıldı!")
        return True
    except Exception as error:
        log_func(f"❌ İşlem Hatası: {error}")
        return False

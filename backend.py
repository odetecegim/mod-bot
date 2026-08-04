import datetime
import re
import time
import unicodedata
from collections import Counter
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

MONTH_MAP = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "janeiro": 1, "fevereiro": 2, "marco": 3, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12
}

def normalize_text(text):
    if not text:
        return ""
    text = str(text).strip().lower()
    replacements = {
        'ı': 'i', 'i̇': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'ñ': 'n', 'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ã': 'a', 'õ': 'o', 'â': 'a', 'ê': 'e', 'ô': 'o', 'à': 'a'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-z0-9]', '', text)
    return text

def calculate_name_similarity(target_name, src_name):
    t_norm = normalize_text(target_name)
    s_norm = normalize_text(src_name)
    
    if not t_norm or not s_norm:
        return 0.0
    
    if t_norm == s_norm or s_norm in t_norm or t_norm in s_norm:
        return 1.0

    t_tokens = set(re.findall(r'\w+', str(target_name).lower()))
    s_tokens = set(re.findall(r'\w+', str(src_name).lower()))
    
    if not t_tokens or not s_tokens:
        return 0.0

    intersection = t_tokens.intersection(s_tokens)
    if intersection:
        return 0.85

    return 0.0

def safe_batch_update(sheet, updates, log_func, batch_size=40):
    total_len = len(updates)
    for i in range(0, total_len, batch_size):
        chunk = updates[i:i + batch_size]
        max_retries = 3
        for attempt in range(max_retries):
            try:
                sheet.batch_update(chunk)
                break
            except APIError as e:
                if attempt < max_retries - 1:
                    log_func(f"⚠️ API yoğunluğu tespiti. 2 saniye içinde tekrar deneniyor...")
                    time.sleep(2)
                else:
                    raise e

def get_available_spreadsheets(creds_input):
    if isinstance(creds_input, dict):
        creds = Credentials.from_service_account_info(creds_input, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(creds_input, scopes=SCOPES)
    
    client = gspread.authorize(creds)
    files = client.list_spreadsheet_files()
    all_sheets = {f['name']: f['id'] for f in files}

    return {
        "all": all_sheets,
        "source": all_sheets,
        "report": all_sheets
    }

class QAReportWorker:
    def __init__(self, creds_input, source_id, report_id, selected_lang, selected_year, selected_month, log_callback, progress_callback):
        self.creds_input = creds_input
        self.source_id = source_id
        self.report_id = report_id
        self.selected_lang = selected_lang
        self.selected_year = int(selected_year)
        self.selected_month_num = MONTH_MAP.get(selected_month.lower(), 1)
        self.selected_month_str = selected_month
        self.log = log_callback
        self.progress = progress_callback

    def connect(self):
        if isinstance(self.creds_input, dict):
            creds = Credentials.from_service_account_info(self.creds_input, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(self.creds_input, scopes=SCOPES)
        return gspread.authorize(creds)

    def parse_date(self, date_val):
        if not date_val:
            return None
        date_str = str(date_val).strip()
        clean_date = re.split(r'\s+', date_str)[0]
        
        formats = (
            "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
            "%d.%m.%y", "%d/%m/%y", "%Y/%m/%d"
        )
        for fmt in formats:
            try:
                return datetime.datetime.strptime(clean_date, fmt)
            except ValueError:
                continue
        return None

    def get_target_worksheet(self, report_wb):
        all_worksheets = report_wb.worksheets()
        target_lang = normalize_text(self.selected_lang)
        target_month = normalize_text(self.selected_month_str)
        target_year = str(self.selected_year).strip()

        for ws in all_worksheets:
            t_lower = normalize_text(ws.title)
            if target_lang in t_lower and target_month in t_lower and target_year in t_lower:
                return ws

        for ws in all_worksheets:
            t_lower = normalize_text(ws.title)
            if target_lang in t_lower and target_month in t_lower:
                return ws

        for ws in all_worksheets:
            t_lower = normalize_text(ws.title)
            if target_lang in t_lower:
                return ws

        return report_wb.sheet1

    def count_user_reports_in_sheet(self, sheet):
        """Sadece seçilen Ay ve Yıl için katı (strict) filtreleme yapar."""
        try:
            raw_rows = sheet.get_all_values()
        except Exception:
            return Counter()

        if not raw_rows or len(raw_rows) <= 1:
            return Counter()

        headers = [normalize_text(h) for h in raw_rows[0]]
        data_rows = raw_rows[1:]

        date_col_idx = 0
        user_col_idx = -1

        for idx, h in enumerate(headers):
            if any(u in h for u in ["apelido", "nome", "user", "kullanici", "name", "reporter", "nick"]):
                user_col_idx = idx
                break
        if user_col_idx == -1:
            user_col_idx = 1

        counts = Counter()

        for row_vals in data_rows:
            if not any(row_vals):
                continue
            
            # 1. Tarih Kontrolü (Katı Filtreleme: Tarih yoksa veya farkı aysa ELENİR)
            if date_col_idx >= len(row_vals):
                continue
                
            date_val = row_vals[date_col_idx]
            dt = self.parse_date(date_val)
            
            # Yalnızca seçili Ay (örn: 7) ve Yıl (örn: 2026) ile tam uyuşan satırlar işlenir
            if not dt or dt.year != self.selected_year or dt.month != self.selected_month_num:
                continue

            # 2. Kullanıcı Adı Kontrolü
            user_name = ""
            if user_col_idx < len(row_vals):
                val = str(row_vals[user_col_idx]).strip()
                if val:
                    user_name = val

            if not user_name:
                continue

            # Şartlar sağlandıysa geçerli satır olarak 1 ekle
            counts[user_name] += 1

        return counts

    def process(self):
        self.log(f"Google Sheets servisine bağlanılıyor... (Dil: {self.selected_lang}, Dönem: {self.selected_month_str} {self.selected_year})")
        self.progress(10)
        client = self.connect()

        source_wb = client.open_by_key(self.source_id)
        report_wb = client.open_by_key(self.report_id)
        
        target_sheet = self.get_target_worksheet(report_wb)
        self.log(f"Kaynak Tablo: [{source_wb.title}] ➔ Ana Tablo Sekmesi: [{target_sheet.title}]")
        self.progress(25)

        source_worksheets = source_wb.worksheets()
        category_counts = {}

        for ws in source_worksheets:
            ws_title = ws.title.strip()
            norm_title = normalize_text(ws_title)

            # Test sekmelerini atla
            if "0kullanici" in norm_title or "testedenovo" in norm_title or "pruebadeusuario" in norm_title or "0kul" in norm_title:
                self.log(f"🚫 Pas geçildi: [{ws_title}]")
                continue

            target_col_name = ""
            if any(k in norm_title for k in ["cartaodemissao", "missao", "gkarti", "gunluk", "tarjetademision", "missioncard", "pass"]):
                target_col_name = "G. Kartı (Günlük)"
            elif any(k in norm_title for k in ["verificacaogeral", "relatoriodeerros", "genelcheck", "genel", "geral", "revisiongeneral", "generalcheck"]):
                target_col_name = "Genel Check"
            else:
                target_col_name = ws_title

            self.log(f"📊 İşleniyor ({self.selected_month_str} {self.selected_year}): [{ws_title}] ➔ Sütun: '{target_col_name}'")
            user_counts = self.count_user_reports_in_sheet(ws)
            
            if target_col_name not in category_counts:
                category_counts[target_col_name] = Counter()
            category_counts[target_col_name].update(user_counts)

        self.progress(60)

        target_rows = target_sheet.get_all_values()
        if not target_rows:
            self.log("⚠️ Ana tabloda veri bulunamadı!")
            self.progress(100)
            return

        target_headers = [str(h).strip() for h in target_rows[0]]
        
        user_col_in_target = 0
        for idx, h in enumerate(target_headers):
            h_norm = normalize_text(h)
            if any(k in h_norm for k in ["kullanici", "user", "name", "qa", "ad", "apelido", "nombre"]):
                user_col_in_target = idx
                break

        col_index_map = {}
        for cat_name in category_counts.keys():
            cat_norm = normalize_text(cat_name)
            for idx, h in enumerate(target_headers):
                h_norm = normalize_text(h)
                if cat_norm in h_norm or h_norm in cat_norm:
                    col_index_map[cat_name] = idx
                    break

        target_users = []
        for row_idx, row in enumerate(target_rows[1:], start=2):
            if row and user_col_in_target < len(row):
                u_name = str(row[user_col_in_target]).strip()
                if u_name:
                    target_users.append((row_idx, u_name))

        cell_updates = []
        
        for cat_name, u_counts in category_counts.items():
            if cat_name not in col_index_map:
                continue
                
            target_c_idx = col_index_map[cat_name]
            
            for row_idx, t_name in target_users:
                total_score = 0
                for src_name, count in u_counts.items():
                    sim_score = calculate_name_similarity(t_name, src_name)
                    if sim_score >= 0.50:
                        total_score += count

                if total_score > 0:
                    cell_updates.append({
                        'range': gspread.utils.rowcol_to_a1(row_idx, target_c_idx + 1),
                        'values': [[total_score]]
                    })

        self.progress(85)

        if cell_updates:
            self.log(f"[{self.selected_month_str} {self.selected_year}] verileri 'G. Kartı (Günlük)' ve 'Genel Check' sütunlarına yazılıyor...")
            safe_batch_update(target_sheet, cell_updates, self.log)
            self.progress(100)
            self.log(f"✅ İŞLEM BAŞARILI! Sadece {self.selected_month_str} {self.selected_year} dönemine ait veriler ana tabloya işlendi.")
        else:
            self.progress(100)
            self.log(f"⚠️ Uyarı: Seçilen tarihe ({self.selected_month_str} {self.selected_year}) ait hiçbir satır bulunamadı.")

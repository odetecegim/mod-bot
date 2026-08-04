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

# ==========================================
# 🧹 METİN TEMİZLEME VE TARİH FONKSİYONLARI
# ==========================================

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
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return " ".join(text.split())

def normalize_text_strict(text):
    return re.sub(r'\s+', '', normalize_text(text))

_MONTH_MAP_RAW = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "janeiro": 1, "fevereiro": 2, "março": 3, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12
}

MONTH_MAP = {normalize_text(k): v for k, v in _MONTH_MAP_RAW.items()}

def get_month_number(month_str):
    return MONTH_MAP.get(normalize_text(month_str), 1)

def calculate_name_similarity(target_name, src_name):
    t_norm = normalize_text(target_name)
    s_norm = normalize_text(src_name)
    if not t_norm or not s_norm:
        return 0.0
    t_strict = normalize_text_strict(target_name)
    s_strict = normalize_text_strict(src_name)
    if t_strict == s_strict or s_strict in t_strict or t_strict in s_strict:
        return 1.0
    t_tokens = set(t_norm.split())
    s_tokens = set(s_norm.split())
    if not t_tokens or not s_tokens:
        return 0.0
    return 0.85 if t_tokens.intersection(s_tokens) else 0.0

def safe_batch_update(sheet, updates, log_func, batch_size=20):
    total_len = len(updates)
    for i in range(0, total_len, batch_size):
        chunk = updates[i:i + batch_size]
        max_retries = 3
        for attempt in range(max_retries):
            try:
                sheet.batch_update(chunk)
                time.sleep(0.4)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    log_func(f"⚠️ API bekleniyor (Deneme {attempt+1}/{max_retries})...")
                    time.sleep(2)
                else:
                    log_func(f"❌ Güncelleme Hatası: {str(e)}")
                    raise e

def get_available_spreadsheets(creds_input):
    try:
        if isinstance(creds_input, dict):
            creds = Credentials.from_service_account_info(creds_input, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(creds_input, scopes=SCOPES)
        client = gspread.authorize(creds)
        files = client.list_spreadsheet_files()
        all_sheets = {f['name']: f['id'] for f in files}
        return {"all": all_sheets, "source": all_sheets, "report": all_sheets}
    except Exception as e:
        return {"error": str(e), "all": {}, "source": {}, "report": {}}

# ==========================================
# 🌐 DİL BAĞIMSIZ HASSAS HARİTALAMA (HANDLER)
# ==========================================

class UniversalLanguageHandler:
    def is_test_sheet(self, norm_title):
        return any(k in norm_title for k in ["0kullanici", "0kul", "testedenovo", "pruebadeusuario", "test"])

    def parse_date(self, date_val):
        if not date_val:
            return None
        clean_date = re.split(r'\s+', str(date_val).strip())[0]
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%y", "%d/%m/%y"):
            try:
                return datetime.datetime.strptime(clean_date, fmt)
            except ValueError:
                continue
        return None

    def map_category(self, ws_title):
        norm = normalize_text_strict(ws_title)
        
        # Test Sekmelerini pas geç
        if self.is_test_sheet(norm):
            return None

        # 1. Görev Kartı / Zula Pass / Mission Card Grubu -> 'ZULA_PASS_KEY'
        if any(k in norm for k in ["missioncard", "mission", "zulapass", "gkarti", "gunluk", "cartaodemissao", "tarjetademision"]):
            return "ZULA_PASS_KEY"

        # 2. Genel Check Grubu -> 'GENEL_CHECK_KEY'
        if any(k in norm for k in ["generalcheck", "general", "genelcheck", "genel", "verificacaogeral", "revisiongeneral"]):
            return "GENEL_CHECK_KEY"

        # 3. Hata Raporlama / Error Reporting Grubu -> 'ERROR_KEY'
        if any(k in norm for k in ["errorreporting", "error", "bug", "hata", "relatoriodeerros", "reportedeerrores"]):
            return "ERROR_KEY"

        return re.sub(r'\(.*?\)', '', ws_title).strip()

def get_language_handler(lang_code):
    return UniversalLanguageHandler()

# ==========================================
# 🚀 QA REPORT WORKER (ANA İŞLEYİCİ)
# ==========================================

class QAReportWorker:
    def __init__(self, creds_input, source_id, report_id, selected_lang, selected_year, selected_month, log_callback, progress_callback):
        self.creds_input = creds_input
        self.source_id = source_id
        self.report_id = report_id
        self.selected_lang = selected_lang.upper().strip()
        self.selected_year = int(selected_year)
        self.selected_month_num = get_month_number(selected_month)
        self.selected_month_str = selected_month
        self.log = log_callback
        self.progress = progress_callback
        self.handler = get_language_handler(self.selected_lang)

    def connect(self):
        if isinstance(self.creds_input, dict):
            creds = Credentials.from_service_account_info(self.creds_input, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(self.creds_input, scopes=SCOPES)
        return gspread.authorize(creds)

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
        try:
            raw_rows = sheet.get_all_values()
        except Exception:
            return Counter()

        if not raw_rows or len(raw_rows) <= 1:
            return Counter()

        headers = [normalize_text(h) for h in raw_rows[0]]
        data_rows = raw_rows[1:]

        date_col_idx = -1
        user_col_idx = -1

        for idx, h in enumerate(headers):
            if any(d in h for d in ["tarih", "data", "date", "fecha", "zaman"]):
                date_col_idx = idx
            if any(u in h for u in ["name", "surname", "apelido", "nome", "user", "kullanici", "reporter", "nick", "nombre", "apellido"]):
                if user_col_idx == -1:
                    user_col_idx = idx

        if user_col_idx == -1:
            user_col_idx = 1 if len(headers) > 1 else 0

        has_date_col = date_col_idx != -1
        counts = Counter()

        for row_vals in data_rows:
            if not any(row_vals):
                continue

            user_name = ""
            if user_col_idx < len(row_vals):
                val = str(row_vals[user_col_idx]).strip()
                if val and not any(tot in val.lower() for tot in ["toplam", "total", "sum"]):
                    user_name = val

            if not user_name:
                continue

            if has_date_col and date_col_idx < len(row_vals):
                date_val = row_vals[date_col_idx]
                dt = self.handler.parse_date(date_val)
                if dt:
                    if dt.year == self.selected_year and dt.month == self.selected_month_num:
                        counts[user_name] += 1
            else:
                counts[user_name] += 1

        return counts

    def process(self):
        self.log(f"İşlem Başlatıldı | Dil: [{self.selected_lang}] | Dönem: [{self.selected_month_str} {self.selected_year}]")
        self.progress(10)
        client = self.connect()

        source_wb = client.open_by_key(self.source_id)
        report_wb = client.open_by_key(self.report_id)
        
        target_sheet = self.get_target_worksheet(report_wb)
        self.log(f"Hedef Sekme: [{target_sheet.title}]")
        self.progress(25)

        source_worksheets = source_wb.worksheets()
        category_counts = {}

        for ws in source_worksheets:
            ws_title = ws.title.strip()
            target_col_key = self.handler.map_category(ws_title)

            if not target_col_key:
                self.log(f"🚫 Pas geçildi (Test Sekmesi): [{ws_title}]")
                continue

            self.log(f"📊 Sekme Okunuyor: [{ws_title}] ➔ Anahtarlanıyor...")
            user_counts = self.count_user_reports_in_sheet(ws)
            
            if target_col_key not in category_counts:
                category_counts[target_col_key] = Counter()
            category_counts[target_col_key].update(user_counts)

        self.progress(60)

        target_rows = target_sheet.get_all_values()
        if not target_rows:
            self.log("⚠️ Ana tabloda veri bulunamadı!")
            self.progress(100)
            return

        target_headers = [str(h).strip() for h in target_rows[0]]
        self.log(f"🔍 Ana Tabloda Bulunan Başlıklar: {target_headers}")

        user_col_in_target = 0
        for idx, h in enumerate(target_headers):
            h_norm = normalize_text(h)
            if any(k in h_norm for k in ["kullanici", "user", "name", "qa", "ad", "apelido", "nombre", "sobrenome", "apellido"]):
                user_col_in_target = idx
                break

        # SÜTUN BAŞLIKLARINI AKILLI DİL EŞLEŞTİRME
        col_index_map = {}
        
        for cat_key in category_counts.keys():
            matched_idx = None

            for idx, h in enumerate(target_headers):
                h_norm = normalize_text_strict(h)
                
                # Zula Pass / Mission Card Eşleştirme
                if cat_key == "ZULA_PASS_KEY":
                    if any(k in h_norm for k in ["zulapass", "pass", "mission", "card", "gkart"]):
                        matched_idx = idx
                        break

                # Genel Check Eşleştirme
                elif cat_key == "GENEL_CHECK_KEY":
                    if any(k in h_norm for k in ["genel", "general", "check", "verificacao", "revision"]):
                        matched_idx = idx
                        break

                # Error Reporting Eşleştirme
                elif cat_key == "ERROR_KEY":
                    if any(k in h_norm for k in ["error", "bug", "hata", "relatorio", "reporte"]):
                        matched_idx = idx
                        break
                
                # Standart Başlık Eşleşmesi
                elif cat_key.lower() in h_norm:
                    matched_idx = idx
                    break

            if matched_idx is not None:
                col_index_map[cat_key] = matched_idx
                self.log(f"🎯 Sütun Başarıyla Bulundu: Sütun {matched_idx + 1} -> ({target_headers[matched_idx]})")
            else:
                self.log(f"❌ UYARI: Hedef tabloda bu kategoriye ait sütun bulunamadı: '{cat_key}'")

        target_users = []
        for row_idx, row in enumerate(target_rows[1:], start=2):
            if row and user_col_in_target < len(row):
                u_name = str(row[user_col_in_target]).strip()
                if u_name:
                    target_users.append((row_idx, u_name))

        cell_updates = []
        
        for cat_key, u_counts in category_counts.items():
            if cat_key not in col_index_map:
                continue
                
            target_c_idx = col_index_map[cat_key]
            
            for row_idx, t_name in target_users:
                total_score = 0
                for src_name, count in u_counts.items():
                    sim_score = calculate_name_similarity(t_name, src_name)
                    if sim_score >= 0.50:
                        total_score += count

                if total_score > 0:
                    a1_cell = gspread.utils.rowcol_to_a1(row_idx, target_c_idx + 1)
                    cell_updates.append({
                        'range': f"{a1_cell}:{a1_cell}",
                        'values': [[int(total_score)]]
                    })

        self.progress(85)

        if cell_updates:
            self.log(f"Veriler [{target_sheet.title}] sekmesine yazılıyor... ({len(cell_updates)} hücre)")
            safe_batch_update(target_sheet, cell_updates, self.log)
            self.progress(100)
            self.log(f"✅ İŞLEM TAMAMLANDI! Tüm sütunlar başarıyla işlendi.")
        else:
            self.progress(100)
            self.log(f"⚠️ Seçilen tarih/dil kriterine uygun aktarılacak veri bulunamadı.")

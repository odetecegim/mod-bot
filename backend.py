import datetime
import re
import time
import unicodedata
from collections import Counter
import pandas as pd
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ==========================================
# 🧹 YARDIMCI FONKSİYONLAR & İSİM TEMİZLEME
# ==========================================

def clean_name_string(text):
    """İsimleri karşılaştırmadan önce tüm aksan, özel karakter ve boşluklardan arındırır."""
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
    norm = normalize_text(month_str)
    if norm.isdigit():
        return int(norm)
    return MONTH_MAP.get(norm, 1)

def match_names(target_name, src_name):
    t_clean = clean_name_string(target_name)
    s_clean = clean_name_string(src_name)

    if not t_clean or not s_clean:
        return False

    if t_clean == s_clean:
        return True

    if len(t_clean) >= 3 and len(s_clean) >= 3:
        if t_clean in s_clean or s_clean in t_clean:
            return True

    t_words = set(normalize_text(target_name).split())
    s_words = set(normalize_text(src_name).split())

    if t_words and s_words:
        common = t_words.intersection(s_words)
        if len(common) >= 1 and any(len(w) >= 3 for w in common):
            return True

    return False

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
# 🌐 DİL BAZLI ÖZEL SÜRÜCÜLER (HANDLERS)
# ==========================================

class BaseLanguageHandler:
    def is_ignored_sheet(self, norm_title):
        ignore_keywords = ["0kullanici", "0kul", "test", "old"]
        return any(k in norm_title for k in ignore_keywords)

    def parse_date(self, date_val):
        if not date_val:
            return None, None
        
        str_val = str(date_val).strip()
        if not str_val:
            return None, None

        clean_date = re.split(r'\s+', str_val)[0]
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%y", "%d/%m/%y"):
            try:
                dt = datetime.datetime.strptime(clean_date, fmt)
                return dt.month, dt.year
            except ValueError:
                continue

        return None, None

class AllLanguagesHandler(BaseLanguageHandler):
    """ENG, ESP ve POR sekmelerini destekleyen birleşik handler."""
    def map_category(self, ws_title):
        norm = normalize_text(ws_title)
        if self.is_ignored_sheet(norm):
            return None
        
        # Günlük Görev / Mission Card
        if any(k in norm for k in ["mision", "mission", "cartaodemissao", "tarjeta", "zulapass", "gunluk", "gkarti", "pass", "kart"]):
            return "G. Kartı (Günlük)"
        # Genel Check
        elif any(k in norm for k in ["verificacaogeral", "generalcheck", "genelcheck", "revision", "general", "geral", "check", "genel"]):
            return "Genel Check"
            
        return None

def get_language_handler(lang_code):
    return AllLanguagesHandler()

# ==========================================
# 🚀 QA REPORT WORKER (ANA İŞLEYİCİ)
# ==========================================

class QAReportWorker:
    def __init__(self, creds_input, source_id, report_id, selected_lang="Tümü", selected_year=2026, selected_month="Ocak", log_callback=None, progress_callback=None):
        self.creds_input = creds_input
        self.source_id = source_id
        self.report_id = report_id
        self.selected_lang = str(selected_lang).upper().strip()
        self.selected_year = int(selected_year)
        self.selected_month_num = get_month_number(selected_month)
        self.selected_month_str = selected_month
        self.log = log_callback if log_callback else print
        self.progress = progress_callback if progress_callback else (lambda x: None)
        self.handler = get_language_handler(self.selected_lang)

    def connect(self):
        if isinstance(self.creds_input, dict):
            creds = Credentials.from_service_account_info(self.creds_input, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(self.creds_input, scopes=SCOPES)
        return gspread.authorize(creds)

    def get_target_worksheet(self, report_wb, source_title=""):
        all_worksheets = report_wb.worksheets()
        target_month = normalize_text(self.selected_month_str)
        target_year = str(self.selected_year).strip()

        # Dili belirle (ENG, ESP, POR)
        detected_lang = ""
        if self.selected_lang in ["ENG", "ESP", "POR"]:
            detected_lang = self.selected_lang.lower()
        else:
            # "Tümü" seçildiyse kaynak dosyanın başlığından tespit et
            s_title_upper = source_title.upper()
            for lang in ["ENG", "ESP", "POR"]:
                if lang in s_title_upper:
                    detected_lang = lang.lower()
                    break

        # 1. Aşama: Hem Dil, hem Ay hem de Yıl geçen tam eşleşen sekme (Örn: "ENG TEMMUZ 2026")
        if detected_lang:
            for ws in all_worksheets:
                t_lower = normalize_text(ws.title)
                if detected_lang in t_lower and target_month in t_lower and target_year in t_lower:
                    return ws

            # 1.b Aşama: Dil ve Ay geçen sekme
            for ws in all_worksheets:
                t_lower = normalize_text(ws.title)
                if detected_lang in t_lower and target_month in t_lower:
                    return ws

        # 2. Aşama: Dil bulunamadıysa sadece Ay ve Yıl adının geçtiği sekme
        for ws in all_worksheets:
            t_lower = normalize_text(ws.title)
            if target_month in t_lower and target_year in t_lower:
                return ws

        # 3. Aşama: Sadece Ay adının geçtiği sekme
        for ws in all_worksheets:
            t_lower = normalize_text(ws.title)
            if target_month in t_lower:
                return ws

        return report_wb.sheet1

    def count_user_reports_in_sheet(self, sheet):
        try:
            raw_rows = sheet.get_all_values()
        except Exception as e:
            self.log(f"⚠️ Sekme okuma hatası [{sheet.title}]: {e}")
            return Counter()

        if not raw_rows or len(raw_rows) <= 1:
            return Counter()

        headers = [normalize_text(h) for h in raw_rows[0]]
        data_rows = raw_rows[1:]

        date_col_idx = 0
        user_col_indices = []

        for idx, h in enumerate(headers):
            if any(u in h for u in ["nombre", "apellido", "nick", "personaje", "kullanici", "user", "name", "qa", "reporter"]):
                user_col_indices.append(idx)

        if not user_col_indices:
            user_col_indices = [1, 2]

        counts = Counter()

        for row_vals in data_rows:
            if not any(row_vals):
                continue

            date_val = row_vals[date_col_idx] if date_col_idx < len(row_vals) else None
            m_num, y_num = self.handler.parse_date(date_val)

            if y_num and y_num != self.selected_year:
                continue
            if m_num and m_num != self.selected_month_num:
                continue

            primary_name = ""
            for u_idx in user_col_indices:
                if u_idx < len(row_vals):
                    val = str(row_vals[u_idx]).strip()
                    if val and not any(tot in val.lower() for tot in ["toplam", "total", "sum", "nombre", "nick"]):
                        primary_name = val
                        break

            if primary_name:
                counts[primary_name] += 1

        return counts

    def process(self):
        self.log(f"İşlem Modülü: [{self.handler.__class__.__name__}] | Filtre: [{self.selected_month_str} (Ay: {self.selected_month_num}) {self.selected_year}]")
        self.progress(10)
        client = self.connect()

        source_wb = client.open_by_key(self.source_id)
        report_wb = client.open_by_key(self.report_id)
        
        # Hedef sekmeyi kaynak dosya ismine/dile göre akıllı bul
        target_sheet = self.get_target_worksheet(report_wb, source_title=source_wb.title)
        self.log(f"Hedef Rapor Sekmesi: [{target_sheet.title}]")
        self.progress(25)

        source_worksheets = source_wb.worksheets()
        category_counts = {}

        for ws in source_worksheets:
            try:
                if ws.is_hidden():
                    self.log(f"🙈 Gizli Sekme Pas Geçildi: [{ws.title}]")
                    continue
            except Exception:
                pass

            ws_title = ws.title.strip()
            target_col_name = self.handler.map_category(ws_title)

            if not target_col_name:
                self.log(f"🚫 Pas geçildi (Kategori Dışı veya OLD Sekme): [{ws_title}]")
                continue

            self.log(f"📊 Sekme Okunuyor: [{ws_title}] ➔ Hedef Kategori: '{target_col_name}'")
            user_counts = self.count_user_reports_in_sheet(ws)
            
            if target_col_name not in category_counts:
                category_counts[target_col_name] = Counter()
            category_counts[target_col_name].update(user_counts)

        self.progress(60)

        target_rows = target_sheet.get_all_values()
        if not target_rows:
            self.log("⚠️ Hedef raporda yazılacak veri alanı bulunamadı!")
            self.progress(100)
            return None

        target_headers = [str(h).strip() for h in target_rows[0]]

        user_col_in_target = 0
        for idx, h in enumerate(target_headers):
            h_norm = normalize_text(h)
            if any(k in h_norm for k in ["kullanici", "user", "name", "qa", "ad", "apelido", "nombre", "sobrenome", "apellido", "oyuncu", "tester"]):
                user_col_in_target = idx
                break

        col_index_map = {}
        for cat_name in category_counts.keys():
            cat_norm = normalize_text(cat_name)
            matched_idx = None
            
            if "kart" in cat_norm or "günlük" in cat_norm or "pass" in cat_norm:
                matched_idx = 3   # D Sütunu (G. Kartı)
            elif "genel" in cat_norm or "check" in cat_norm:
                matched_idx = 5   # F Sütunu (Genel Check)

            if matched_idx is not None:
                col_index_map[cat_name] = matched_idx
                col_letter = chr(65 + matched_idx)
                self.log(f"🎯 Hedef Sütun Kilitlendi: '{cat_name}' ➔ [{col_letter} Sütunu]")

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
                matched_sources = []
                for src_name, count in u_counts.items():
                    if match_names(t_name, src_name):
                        total_score += count
                        matched_sources.append(src_name)

                if total_score > 0:
                    a1_cell = gspread.utils.rowcol_to_a1(row_idx, target_c_idx + 1)
                    cell_updates.append({
                        'range': f"{a1_cell}:{a1_cell}",
                        'values': [[int(total_score)]]
                    })
                    self.log(f"    ✓ {t_name} = {total_score} (Eşleşen: {', '.join(matched_sources)})")

        self.progress(85)

        if cell_updates:
            self.log(f"Veriler [{target_sheet.title}] sekmesine yazılıyor... ({len(cell_updates)} hücre)")
            safe_batch_update(target_sheet, cell_updates, self.log)
            self.progress(100)
            self.log(f"✅ İŞLEM BAŞARILI! Gerçek rapor sayıları D ve F sütunlarına aktarıldı.")
        else:
            self.progress(100)
            self.log(f"⚠️ Uyarı: Seçilen filtre kriterlerine uyan kayıt bulunamadı.")

        final_rows = target_sheet.get_all_values()
        if final_rows and len(final_rows) > 1:
            return pd.DataFrame(final_rows[1:], columns=final_rows[0])
        return pd.DataFrame(final_rows)

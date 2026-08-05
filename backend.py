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
# 🧹 METİN TEMİZLEME VE NORMALİZASYON
# ==========================================

def clean_name_string(text):
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
    "temmuz": 7, "ağustos": 8, "eylül": 9, "eylul": 9, "ekim": 10, "kasım": 11, "aralık": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
}

MONTH_MAP = {normalize_text(k): v for k, v in _MONTH_MAP_RAW.items()}

def get_month_number(month_str):
    norm = normalize_text(month_str)
    if norm.isdigit():
        return int(norm)
    return MONTH_MAP.get(norm, 1)

# ==========================================
# 🎯 HASSAS VE SIKI İSİM EŞLEŞTİRME MANTIĞI
# ==========================================

def match_names(target_name, src_name):
    t_clean = clean_name_string(target_name)
    s_clean = clean_name_string(src_name)

    if not t_clean or not s_clean:
        return False

    if t_clean == s_clean:
        return True

    t_words = [w for w in normalize_text(target_name).split() if len(w) > 1]
    s_words = [w for w in normalize_text(src_name).split() if len(w) > 1]

    if len(t_words) >= 2 and len(s_words) >= 2:
        return sorted(t_words) == sorted(s_words)

    if len(s_clean) >= 3 and len(t_clean) >= 3:
        if s_clean == t_clean:
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
# 🌐 DİL VE KATEGORİ HANDLER
# ==========================================

class AllLanguagesHandler:
    def is_ignored_sheet(self, norm_title):
        ignore_keywords = ["0kullanici", "0kul", "0usuario", "0jugador", "test", "old"]
        return any(k in norm_title for k in ignore_keywords)

    def parse_date(self, date_val):
        if not date_val:
            return None, None
        str_val = str(date_val).strip()
        if not str_val:
            return None, None
        clean_date = re.split(r'\s+', str_val)[0]
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%y", "%d/%m/%y", "%Y/%m/%d"):
            try:
                dt = datetime.datetime.strptime(clean_date, fmt)
                return dt.month, dt.year
            except ValueError:
                continue
        return None, None

    def map_category(self, ws_title):
        norm = normalize_text(ws_title)
        if self.is_ignored_sheet(norm):
            return None
        
        if any(k in norm for k in ["mision", "misiones", "mission", "cartaodemissao", "tarjeta", "tarjetas", "zulapass", "pase", "gunluk", "gkarti", "pass", "kart"]):
            return "G. Kartı (Günlük)"
        elif any(k in norm for k in ["verificacaogeral", "generalcheck", "genelcheck", "revision", "revisiones", "chequeo", "general", "geral", "check", "genel", "errores", "error"]):
            return "Genel Check"
            
        return None

# ==========================================
# 🚀 QA REPORT WORKER
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
        self.handler = AllLanguagesHandler()

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

        detected_lang = ""
        if self.selected_lang in ["ENG", "ESP", "POR"]:
            detected_lang = self.selected_lang.lower()
        else:
            s_title_upper = source_title.upper()
            for lang in ["ENG", "ESP", "POR"]:
                if lang in s_title_upper:
                    detected_lang = lang.lower()
                    break

        if detected_lang:
            for ws in all_worksheets:
                t_lower = normalize_text(ws.title)
                if detected_lang in t_lower and target_month in t_lower and target_year in t_lower:
                    return ws

        for ws in all_worksheets:
            t_lower = normalize_text(ws.title)
            if target_month in t_lower and target_year in t_lower:
                return ws

        raise ValueError(f"Hedef dosyada '{self.selected_month_str} {self.selected_year}' dönemine ait sekme bulunamadı!")

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
            if any(u in h for u in [
                "nombre", "apellido", "nick", "personaje", "kullanici", "user", 
                "name", "qa", "reporter", "jugador", "usuario", "reportador", "tester"
            ]):
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
                    if val and not val.startswith("#") and not any(tot in val.lower() for tot in ["toplam", "total", "sum", "nombre", "nick"]):
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
            if any(k in h_norm for k in [
                "kullanici", "user", "name", "qa", "ad", "apelido", "nombre", 
                "sobrenome", "apellido", "oyuncu", "tester", "jugador", "usuario", "nick"
            ]):
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
                if u_name and not u_name.startswith("#"):
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
            final_rows = target_sheet.get_all_values()
            if final_rows and len(final_rows) > 1:
                return pd.DataFrame(final_rows[1:], columns=final_rows[0])
            return pd.DataFrame(final_rows)
        else:
            self.progress(100)
            self.log(f"⚠️ Uyarı: Seçilen {self.selected_month_str} {self.selected_year} filtresine uyan veri bulunamadı.")
            return None

# ==========================================
# ⚡ OTOMATİK ZA MİKTARI İŞLEME VE TOPLAM HESAPLAMA
# ==========================================

def process_za_and_insert_month(target_sheet, selected_month, log_func=print):
    """
    1. Seçilen ay sütununa ZA miktarlarını aktarır.
    2. SON MİKTARI OTOMATİK TOPLAR: Personelin tüm aylık ZA'larını veya puanlarını 
       toplayıp en sağdaki 'Toplanacak Miktar / Yüklenecek ZA' sütununa yazar.
    """
    try:
        all_data = target_sheet.get_all_values()
        if not all_data or len(all_data) < 2:
            log_func("⚠️ Hedef tabloda işlenecek veri bulunamadı.")
            return False

        headers = [str(h).strip() for h in all_data[0]]
        
        # ZA ve Toplam Sütunlarını Bul
        za_col_idx = None
        total_col_idx = None
        
        for idx, h in enumerate(headers):
            h_upper = h.upper()
            if "ZA" in h_upper and za_col_idx is None:
                za_col_idx = idx
            if any(k in h_upper for k in ["TOPLAM", "YÜKLENECEK", "SON MİKTAR", "REWARD", "ÖDÜL"]):
                total_col_idx = idx

        if za_col_idx is None:
            log_func("❌ Hedef tabloda 'ZA' sütunu bulunamadı!")
            return False

        norm_selected_month = normalize_text(selected_month)
        month_col_idx = None

        for idx, h in enumerate(headers):
            if norm_selected_month == normalize_text(h):
                month_col_idx = idx + 1
                log_func(f"ℹ️ [{selected_month}] sütunu tabloda zaten mevcut. Mevcut sütuna yazılıyor...")
                break

        if not month_col_idx:
            month_order = ["ocak", "subat", "mart", "nisan", "mayis", "haziran", 
                           "temmuz", "agustos", "eylul", "ekim", "kasim", "aralik"]
            
            target_idx_in_order = month_order.index(norm_selected_month) if norm_selected_month in month_order else -1
            
            next_month_col_idx = None
            if target_idx_in_order != -1:
                for idx, h in enumerate(headers):
                    h_norm = normalize_text(h)
                    if h_norm in month_order:
                        if month_order.index(h_norm) > target_idx_in_order:
                            next_month_col_idx = idx + 1
                            break

            if next_month_col_idx:
                target_sheet.insert_cols([selected_month], col=next_month_col_idx)
                month_col_idx = next_month_col_idx
                log_func(f"➕ [{selected_month}] sütunu sonraki ayın SOLUNA açıldı.")
            else:
                insert_position = za_col_idx + 1 if za_col_idx else len(headers) + 1
                target_sheet.insert_cols([selected_month], col=insert_position)
                month_col_idx = insert_position
                log_func(f"➕ [{selected_month}] sütunu yeni olarak eklendi.")

        all_data_updated = target_sheet.get_all_values()
        updates = []

        for row_idx, row in enumerate(all_data_updated[1:], start=2):
            if not row:
                continue

            name = str(row[1]).strip() if len(row) > 1 else ""
            if not name or name.startswith("#"):
                continue

            za_value = str(row[za_col_idx]).strip() if za_col_idx < len(row) else ""
            
            # Ay Sütununa Veriyi Aktar
            if za_value and za_value != "0" and not za_value.startswith("#"):
                a1_cell = gspread.utils.rowcol_to_a1(row_idx, month_col_idx)
                updates.append({
                    'range': f"{a1_cell}:{a1_cell}",
                    'values': [[za_value]]
                })

            # 🧮 SON MİKTARI OTOMATİK HESAPLA & TOPLA
            if total_col_idx is not None:
                # Satırdaki sayısal değerleri topla
                total_val = 0
                for cell in row[2:]:
                    clean_c = re.sub(r'[^\d]', '', str(cell))
                    if clean_c.isdigit():
                        total_val += int(clean_c)

                if total_val > 0:
                    tot_cell = gspread.utils.rowcol_to_a1(row_idx, total_col_idx + 1)
                    updates.append({
                        'range': f"{tot_cell}:{tot_cell}",
                        'values': [[str(total_val)]]
                    })

        if updates:
            safe_batch_update(target_sheet, updates, log_func)
            log_func(f"✅ ZA miktarları işlendi ve Toplam Miktar sütunları otomatik güncellendi! ({len(updates)} kayıt)")
            return True
        else:
            log_func(f"⚠️ [{selected_month}] için aktarılacak geçerli ZA miktarı bulunamadı.")
            return False

    except Exception as e:
        log_func(f"❌ İşleme hatası: {str(e)}")
        return False

import datetime
import re
import unicodedata
from collections import Counter
import gspread
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
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}

def normalize_text(text):
    """Metinleri küçük harfe çevirir, Türkçe, İspanyolca ve Portekizce karakterleri temizler."""
    if not text:
        return ""
    text = str(text).strip().lower()
    replacements = {
        'ı': 'i', 'İ': 'i', 'ğ': 'g', 'Ğ': 'g', 'ü': 'u', 'Ü': 'u',
        'ş': 's', 'Ş': 's', 'ö': 'o', 'Ö': 'o', 'ç': 'c', 'Ç': 'c',
        'ñ': 'n', 'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ã': 'a', 'õ': 'o', 'â': 'a', 'ê': 'e', 'ô': 'o'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def calculate_name_similarity(target_name, src_name):
    """
    İki isim arasındaki benzerlik puanını hesaplar.
    "Mert Efe Künç" vs "Efe Künç" -> Yüksek Puan
    "Mert Efe Künç" vs "Mert Künç" -> Yüksek Puan
    """
    t_norm = normalize_text(target_name)
    s_norm = normalize_text(src_name)
    
    if not t_norm or not s_norm:
        return 0.0
    
    if t_norm == s_norm:
        return 1.0
    
    t_tokens = set(t_norm.split())
    s_tokens = set(s_norm.split())
    
    if not t_tokens or not s_tokens:
        return 0.0

    # Ortak kelime sayısı
    intersection = t_tokens.intersection(s_tokens)
    if not intersection:
        return 0.0

    # Kaynaktaki tüm kelimeler hedefte varsa tam uyum kabul et
    if s_tokens.issubset(t_tokens):
        return 0.95
    if t_tokens.issubset(s_tokens):
        return 0.90

    # Jaccard benzerlik skoru
    return len(intersection) / float(len(t_tokens.union(s_tokens)))

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
        target_lang = self.selected_lang.lower().strip()
        target_month = self.selected_month_str.lower().strip()
        target_year = str(self.selected_year).strip()

        for ws in all_worksheets:
            t_lower = ws.title.lower().strip()
            if target_lang in t_lower and target_month in t_lower and target_year in t_lower:
                return ws

        for ws in all_worksheets:
            t_lower = ws.title.lower().strip()
            if target_lang in t_lower and target_month in t_lower:
                return ws

        for ws in all_worksheets:
            t_lower = ws.title.lower().strip()
            if target_lang in t_lower:
                return ws

        return report_wb.sheet1

    def count_user_reports_in_sheet(self, sheet):
        raw_rows = sheet.get_all_values()
        if not raw_rows or len(raw_rows) <= 1:
            return Counter()

        headers = [str(h).strip().lower() for h in raw_rows[0]]
        data_rows = raw_rows[1:]

        date_col_idx = 0
        user_col_idx = -1

        for idx, h in enumerate(headers):
            if any(u in h for u in ["name-surname", "name", "surname", "ad soyad", "kullanıcı", "user", "reporter", "nombre", "apelido", "nick"]):
                user_col_idx = idx
                break
        if user_col_idx == -1:
            user_col_idx = 1

        counts = Counter()
        fallback_counts = Counter()

        for row_vals in data_rows:
            if not any(row_vals):
                continue
            
            user_name = "Bilinmeyen Kullanıcı"
            if user_col_idx < len(row_vals):
                val = str(row_vals[user_col_idx]).strip()
                if val:
                    user_name = val

            if date_col_idx < len(row_vals):
                date_val = row_vals[date_col_idx]
                dt = self.parse_date(date_val)
                if dt:
                    if dt.year == self.selected_year and dt.month == self.selected_month_num:
                        counts[user_name] += 1
                    elif dt.month == self.selected_month_num:
                        fallback_counts[user_name] += 1

        return counts if sum(counts.values()) > 0 else fallback_counts

    def process(self):
        self.log(f"Google Sheets servisine bağlanılıyor... (Seçilen Dil: {self.selected_lang})")
        self.progress(10)
        client = self.connect()

        source_wb = client.open_by_key(self.source_id)
        report_wb = client.open_by_key(self.report_id)
        
        target_sheet = self.get_target_worksheet(report_wb)
        self.log(f"Kaynak Tablo: [{source_wb.title}] ➔ Ana Tablo Sekmesi: [{target_sheet.title}]")
        self.progress(25)

        source_worksheets = source_wb.worksheets()
        category_counts = {}

        # 1. POR ve ESP İçin Tüm Sekmelerin Sütun Haritasını Çıkar
        for ws in source_worksheets:
            ws_title = ws.title.strip()
            title_lower = ws_title.lower()

            if any(term in title_lower for term in ["0 kullanıcı", "0 kul", "new user test", "prueba de usuario nuevo"]):
                self.log(f"🚫 Pas geçildi: [{ws_title}] (0 Kullanıcı Testi işlenmeyecek)")
                continue

            # ESP & POR sekmelerini Türkçe başlıklarla eşleştir
            target_col_name = ""
            if any(term in title_lower for term in ["tarjeta de misión", "mission card", "zula pass", "g.görev", "pass", "missao"]):
                target_col_name = "Zula Pass"
            elif any(term in title_lower for term in ["revisión general", "relatório de erros", "general check", "genel", "g.kontrol", "geral"]):
                target_col_name = "Genel"
            else:
                target_col_name = ws_title

            self.log(f"📊 Kaynak Sekme: [{ws_title}] ➔ Ana Tablo Sütun: '{target_col_name}'")
            user_counts = self.count_user_reports_in_sheet(ws)
            
            if target_col_name not in category_counts:
                category_counts[target_col_name] = Counter()
            category_counts[target_col_name].update(user_counts)

        self.progress(60)

        target_rows = target_sheet.get_all_values()
        if not target_rows:
            self.log("⚠️ Ana tabloda veri/başlık bulunamadı!")
            self.progress(100)
            return

        target_headers = [str(h).strip() for h in target_rows[0]]
        
        user_col_in_target = 0
        for idx, h in enumerate(target_headers):
            if any(k in h.lower() for k in ["kullanıcı", "user", "name", "qa", "ad", "nombre", "apelido"]):
                user_col_in_target = idx
                break

        col_index_map = {}
        for cat_name in category_counts.keys():
            for idx, h in enumerate(target_headers):
                if cat_name.lower() in h.lower():
                    col_index_map[cat_name] = idx
                    break

        # Ana tablodaki kullanıcı isimlerini topla
        target_users = []
        for row_idx, row in enumerate(target_rows[1:], start=2):
            if row and user_col_in_target < len(row):
                u_name = str(row[user_col_in_target]).strip()
                if u_name:
                    target_users.append((row_idx, u_name))

        cell_updates = []
        
        # 2. Her Sütun ve Kullanıcı İçin En İyi Eşleşmeyi Hesapla
        for cat_name, u_counts in category_counts.items():
            if cat_name not in col_index_map:
                continue
                
            target_c_idx = col_index_map[cat_name]
            
            # Ana tablodaki her kullanıcı için kaynak verileri tarayarak puan topla
            for row_idx, t_name in target_users:
                total_score = 0
                for src_name, count in u_counts.items():
                    sim_score = calculate_name_similarity(t_name, src_name)
                    # Benzerlik eşiği 0.50 ve üzeri ise eşleşmiş kabul et
                    if sim_score >= 0.50:
                        total_score += count

                cell_updates.append({
                    'range': gspread.utils.rowcol_to_a1(row_idx, target_c_idx + 1),
                    'values': [[total_score if total_score > 0 else ""]]
                })

        self.progress(85)

        if cell_updates:
            self.log(f"İsimler ve kategoriler eşleştirildi. Veriler [{target_sheet.title}] sekmesine aktarılıyor...")
            target_sheet.batch_update(cell_updates)
            self.progress(100)
            self.log(f"✅ İŞLEM BAŞARILI! POR ve ESP verileri tüm sütunlara doğru şekilde yazıldı.")
        else:
            self.progress(100)
            self.log(f"⚠️ [{target_sheet.title}] sekmesinde işlenecek veri bulunamadı.")

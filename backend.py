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
    """Metinleri küçük harfe çevirir, Türkçe/Özel karakterleri ve fazla boşlukları temizler."""
    if not text:
        return ""
    text = str(text).strip().lower()
    replacements = {
        'ı': 'i', 'i̇': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'ñ': 'n', 'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def are_names_matching(name1, name2):
    """
    Hatalı eşleşmeleri önlemek için daha güvenli isim karşılaştırması.
    """
    n1 = normalize_text(name1)
    n2 = normalize_text(name2)
    
    if not n1 or not n2:
        return False
    
    # Tam eşitlik
    if n1 == n2:
        return True
    
    tokens1 = set(n1.split())
    tokens2 = set(n2.split())
    
    # Kümelerden biri diğerinin tamamen içindeyse (Örn: 'ahmet' -> 'ahmet can')
    if tokens1.issubset(tokens2) or tokens2.issubset(tokens1):
        return True
        
    return False

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

    def get_target_worksheets(self, report_wb):
        """
        Eğer dil 'Tümü' / 'All' seçildiyse eşleşen tüm sekmeleri, 
        spesifik dil seçildiyse tek sekmeyi döndürür.
        """
        all_worksheets = report_wb.worksheets()
        target_lang = self.selected_lang.lower().strip()
        
        if target_lang in ["tümü", "tumu", "all", ""]:
            return all_worksheets

        matched_sheets = []
        for ws in all_worksheets:
            t_lower = ws.title.lower().strip()
            if target_lang in t_lower:
                matched_sheets.append(ws)

        return matched_sheets if matched_sheets else [report_wb.sheet1]

    def count_user_reports_in_sheet(self, sheet):
        """Kullanıcı rapor sayılarını toplar."""
        try:
            raw_rows = sheet.get_all_values()
        except Exception as e:
            self.log(f"⚠️ Sekme okunamadı [{sheet.title}]: {str(e)}")
            return Counter()

        if not raw_rows or len(raw_rows) <= 1:
            return Counter()

        headers = [str(h).strip().lower() for h in raw_rows[0]]
        data_rows = raw_rows[1:]

        date_col_idx = 0
        user_col_idx = -1

        for idx, h in enumerate(headers):
            if any(u in h for u in ["name-surname", "name", "surname", "ad soyad", "kullanıcı", "user", "reporter", "nombre"]):
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
        self.log(f"Google Sheets servisine bağlanılıyor... (Dil Filtresi: {self.selected_lang})")
        self.progress(10)
        client = self.connect()

        source_wb = client.open_by_key(self.source_id)
        report_wb = client.open_by_key(self.report_id)
        
        target_sheets = self.get_target_worksheets(report_wb)
        self.progress(20)

        # 1. Kaynak Tablo Sekmelerini İşle
        source_worksheets = source_wb.worksheets()
        category_counts = {}

        for ws in source_worksheets:
            ws_title = ws.title.strip()
            title_lower = ws_title.lower()

            if any(term in title_lower for term in ["0 kullanıcı", "0 kul", "new user test", "prueba de usuario nuevo"]):
                self.log(f"🚫 Pas geçildi: [{ws_title}] (0 Kullanıcı Testi)")
                continue

            target_col_name = ""
            if any(term in title_lower for term in ["tarjeta de misión", "mission card", "pass", "g.görev"]):
                target_col_name = "Zula Pass"
            elif any(term in title_lower for term in ["revisión general", "general check", "genel", "g.kontrol"]):
                target_col_name = "Genel"
            else:
                target_col_name = ws_title

            self.log(f"📊 Taranıyor: [{ws_title}] ➔ Hedef Sütun: '{target_col_name}'")
            user_counts = self.count_user_reports_in_sheet(ws)
            category_counts[target_col_name] = user_counts

        self.progress(60)

        # 2. Seçilen / Eşleşen Hedef Sekmeleri Güncelle
        for target_sheet in target_sheets:
            self.log(f"📝 İşleniyor: Hedef Sekme [{target_sheet.title}]")
            target_rows = target_sheet.get_all_values()
            if not target_rows:
                continue

            target_headers = [str(h).strip() for h in target_rows[0]]
            
            user_col_in_target = 0
            for idx, h in enumerate(target_headers):
                if any(k in h.lower() for k in ["kullanıcı", "user", "name", "qa", "ad", "nombre"]):
                    user_col_in_target = idx
                    break

            col_index_map = {}
            for cat_name in category_counts.keys():
                for idx, h in enumerate(target_headers):
                    if cat_name.lower() in h.lower():
                        col_index_map[cat_name] = idx
                        break

            cell_updates = []
            
            for row_idx, row in enumerate(target_rows[1:], start=2):
                if not row or user_col_in_target >= len(row):
                    continue
                
                target_user_name = str(row[user_col_in_target]).strip()
                if not target_user_name:
                    continue

                for cat_name, u_counts in category_counts.items():
                    if cat_name in col_index_map:
                        target_c_idx = col_index_map[cat_name]
                        
                        matched_count = 0
                        for src_user_name, count in u_counts.items():
                            if are_names_matching(target_user_name, src_user_name):
                                matched_count += count
                        
                        cell_updates.append({
                            'range': gspread.utils.rowcol_to_a1(row_idx, target_c_idx + 1),
                            'values': [[matched_count if matched_count > 0 else ""]]
                        })

            if cell_updates:
                target_sheet.batch_update(cell_updates)
                self.log(f"✅ [{target_sheet.title}] sekmesine puanlar aktarıldı.")

        self.progress(100)
        self.log(f"🚀 TÜM İŞLEMLER BAŞARIYLA TAMAMLANDI!")

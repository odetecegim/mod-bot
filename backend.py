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
    # Türkçe özel harf dönüşümleri
    replacements = {
        'ı': 'i', 'İ': 'i', 'ğ': 'g', 'Ğ': 'g', 'ü': 'u', 'Ü': 'u',
        'ş': 's', 'Ş': 's', 'ö': 'o', 'Ö': 'o', 'ç': 'c', 'Ç': 'c',
        'ñ': 'n', 'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    # Sadece harf ve rakamları tut
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def are_names_matching(name1, name2):
    """
    Tek isim / çift isim ve küçük-büyük harf uyumsuzluklarını akıllıca karşılaştırır.
    Örn: "Ahmet Can" <-> "ahmet", "Mehmet Ali" <-> "mehmet ali"
    """
    n1 = normalize_text(name1)
    n2 = normalize_text(name2)
    
    if not n1 or not n2:
        return False
    
    # Tam eşitlik
    if n1 == n2:
        return True
    
    # Kelimelere ayır (Kelime bazlı kontrol)
    tokens1 = set(n1.split())
    tokens2 = set(n2.split())
    
    # Kelime kümesi alt kümesi mi? (Örn: 'ahmet' kelimesi {'ahmet', 'can'} kümesinde var mı?)
    if tokens1.issubset(tokens2) or tokens2.issubset(tokens1):
        return True
        
    # Herhangi bir ortak isim 3 harften uzunsa ve eşleşiyorsa
    common_tokens = tokens1.intersection(tokens2)
    for token in common_tokens:
        if len(token) >= 3:
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

    def get_target_worksheet(self, report_wb):
        """Dile uygun hedef sekemeyi otomatik bulur."""
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
        """Kullanıcı rapor sayılarını toplar."""
        raw_rows = sheet.get_all_values()
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
        self.log(f"Google Sheets servisine bağlanılıyor... (Dil: {self.selected_lang})")
        self.progress(10)
        client = self.connect()

        source_wb = client.open_by_key(self.source_id)
        report_wb = client.open_by_key(self.report_id)
        
        target_sheet = self.get_target_worksheet(report_wb)
        self.log(f"Kaynak Tablo: [{source_wb.title}] ➔ Hedef Sekme: [{target_sheet.title}]")
        self.progress(25)

        # 1. Kaynak Tablo Sekmelerini İşle
        source_worksheets = source_wb.worksheets()
        category_counts = {}

        for ws in source_worksheets:
            ws_title = ws.title.strip()
            title_lower = ws_title.lower()

            # 0 Kullanıcı Testi Tamamen Atlanır
            if any(term in title_lower for term in ["0 kullanıcı", "0 kul", "new user test", "prueba de usuario nuevo"]):
                self.log(f"🚫 Pas geçildi: [{ws_title}] (0 Kullanıcı Testi işlenmeyecek)")
                continue

            # Hedef Sütun Eşleştirmesi
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

        # 2. Ana Tablo Yapısını Oku
        target_rows = target_sheet.get_all_values()
        if not target_rows:
            self.log("⚠️ Hedef sekmede veri/başlık yapısı bulunamadı!")
            self.progress(100)
            return

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
        
        # 3. Satır Bazlı İsim Eşleştirme ve Puan Yazma
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
                    # Esnek İsim Karşılaştırması Yapılır
                    for src_user_name, count in u_counts.items():
                        if are_names_matching(target_user_name, src_user_name):
                            matched_count += count  # Çift kayıt varsa puanları toplar
                    
                    cell_updates.append({
                        'range': gspread.utils.rowcol_to_a1(row_idx, target_c_idx + 1),
                        'values': [[matched_count if matched_count > 0 else ""]]
                    })

        self.progress(85)

        # 4. Güncellemeleri Biçimlendirmeleri KORUYARAK Yaz
        if cell_updates:
            self.log(f"İsimler eşleştirildi. Puanlar [{target_sheet.title}] sekmesine yazılıyor...")
            target_sheet.batch_update(cell_updates)
            self.progress(100)
            self.log(f"✅ İŞLEM BAŞARILI! Tek/çift isimli ve küçük harfle yazılan kullanıcı puanları doğru şekilde aktarıldı.")
        else:
            self.progress(100)
            self.log(f"⚠️ [{target_sheet.title}] sekmesinde eşleşen veri bulunamadı.")

import datetime
import re
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
        """ENG Temmuz 2026 gibi hedef sekleyi bulur."""
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
        """Verilen sekmedeki kullanıcı rapor sayılarını filtreleyerek hesaplar."""
        raw_rows = sheet.get_all_values()
        if not raw_rows or len(raw_rows) <= 1:
            return Counter()

        headers = [str(h).strip().lower() for h in raw_rows[0]]
        data_rows = raw_rows[1:]

        date_col_idx = 0
        user_col_idx = -1

        for idx, h in enumerate(headers):
            if any(u in h for u in ["name-surname", "name", "surname", "ad soyad", "kullanıcı", "user"]):
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
        self.log("Google Sheets servisine bağlanılıyor...")
        self.progress(10)
        client = self.connect()

        source_wb = client.open_by_key(self.source_id)
        report_wb = client.open_by_key(self.report_id)
        target_sheet = self.get_target_worksheet(report_wb)

        self.log(f"Hedef Sekme Tespit Edildi: [{target_sheet.title}]")
        self.progress(25)

        # 1. Kaynak Tablodaki Sekmeleri Oku (0 Kullanıcı Testi HARİÇ TUTULUR)
        source_worksheets = source_wb.worksheets()
        
        # Sekme İsimleri ➔ Hedef Tablo Sütun Adı Eşleşmesi
        category_counts = {}

        for ws in source_worksheets:
            ws_title = ws.title.strip()
            title_lower = ws_title.lower()

            # "0 Kullanıcı" testi tamamen atlanıyor (İşleme alınmayacak)
            if "0 kullanıcı" in title_lower or "0 kul" in title_lower or "new user test" in title_lower:
                self.log(f"🚫 Pas geçildi: [{ws_title}] (0 Kullanıcı Testi işlenmeyecek)")
                continue

            # Hedef Sütun İsmi Belirleme
            target_col_name = ""
            if "mission card" in title_lower or "pass" in title_lower:
                target_col_name = "Zula Pass"
            elif "general check" in title_lower or "genel" in title_lower:
                target_col_name = "Genel"
            else:
                target_col_name = ws_title

            self.log(f"📊 İşleniyor: [{ws_title}] ➔ Hedef Sütun: '{target_col_name}'")
            user_counts = self.count_user_reports_in_sheet(ws)
            category_counts[target_col_name] = user_counts

        self.progress(60)

        # 2. Ana Tablonun (ENG Temmuz 2026) Yapısını Oku ve Güncelle
        target_rows = target_sheet.get_all_values()
        if not target_rows:
            self.log("⚠️ Hedef sekmede başlık yapısı bulunamadı!")
            self.progress(100)
            return

        target_headers = [str(h).strip() for h in target_rows[0]]
        
        # Kullanıcı isimlerinin olduğu sütunu bul (Genelde A veya B)
        user_col_in_target = 0
        for idx, h in enumerate(target_headers):
            if any(k in h.lower() for k in ["kullanıcı", "user", "name", "qa", "ad"]):
                user_col_in_target = idx
                break

        self.log(f"Ana Tablo Sütunları: {target_headers}")

        # Her kategori için sütun indekslerini eşleştir
        col_index_map = {}
        for cat_name in category_counts.keys():
            for idx, h in enumerate(target_headers):
                if cat_name.lower() in h.lower():
                    col_index_map[cat_name] = idx
                    break

        # Hücre güncellemelerini hazırla
        cell_updates = []
        
        for row_idx, row in enumerate(target_rows[1:], start=2): # 2. satırdan itibaren veriler
            if not row or user_col_in_target >= len(row):
                continue
            
            user_name_in_target = str(row[user_col_in_target]).strip().lower()
            if not user_name_in_target:
                continue

            # Her kategori için eşleşen kullanıcı sayısını bul ve yaz
            for cat_name, u_counts in category_counts.items():
                if cat_name in col_index_map:
                    target_c_idx = col_index_map[cat_name]
                    
                    # İsmi esnek eşleştir
                    matched_count = 0
                    for u_src, count in u_counts.items():
                        if u_src.lower() in user_name_in_target or user_name_in_target in u_src.lower():
                            matched_count = count
                            break
                    
                    cell_updates.append({
                        'range': gspread.utils.rowcol_to_a1(row_idx, target_c_idx + 1),
                        'values': [[matched_count if matched_count > 0 else ""]]
                    })

        self.progress(85)

        # 3. Güncellemeleri Bozulma Olmadan Toplu Yaz
        if cell_updates:
            self.log("Veriler biçimlendirmeler korunarak ana tabloya aktarılıyor...")
            target_sheet.batch_update(cell_updates)
            self.progress(100)
            self.log(f"✅ İŞLEM BAŞARILI! [{target_sheet.title}] sekmesindeki 'Zula Pass' ve 'Genel' sütunları güncellendi ('0 Kul. TESTİ' sütununa dokunulmadı).")
        else:
            self.progress(100)
            self.log("⚠️ Eşleşen kullanıcı verisi bulunamadı veya güncellenecek veri yok.")

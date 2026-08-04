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
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
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
        """Tarih bilgisini çözümler."""
        if not date_val:
            return None
        date_str = str(date_val).strip()
        clean_date = re.split(r'\s+', date_str)[0]
        
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%y", "%d/%m/%y"):
            try:
                return datetime.datetime.strptime(clean_date, fmt)
            except ValueError:
                continue
        return None

    def get_target_worksheet(self, report_wb):
        """İlgili Dil + Ay + Yıl sekmesini bulur (örn: ESP Temmuz 2026)."""
        all_worksheets = report_wb.worksheets()
        
        target_lang = self.selected_lang.lower().strip()
        target_month = self.selected_month_str.lower().strip()
        target_year = str(self.selected_year).strip()

        # 1. Tam Eşleşme (Örn: "ESP Temmuz 2026")
        for ws in all_worksheets:
            t_lower = ws.title.lower().strip()
            if target_lang in t_lower and target_month in t_lower and target_year in t_lower:
                return ws

        # 2. Dil + Ay (Örn: "ESP Temmuz")
        for ws in all_worksheets:
            t_lower = ws.title.lower().strip()
            if target_lang in t_lower and target_month in t_lower:
                return ws

        # 3. Sadece Dil sekmesi (Örn: "ESP")
        for ws in all_worksheets:
            t_lower = ws.title.lower().strip()
            if target_lang in t_lower:
                return ws

        return report_wb.sheet1

    def process(self):
        self.log("Google Sheets servisine bağlanılıyor...")
        self.progress(10)
        client = self.connect()

        source_wb = client.open_by_key(self.source_id)
        source_sheet = source_wb.sheet1

        report_wb = client.open_by_key(self.report_id)
        report_sheet = self.get_target_worksheet(report_wb)

        self.log(f"Kaynak: [{source_wb.title}] ➔ Hedef Sekme: [{report_sheet.title}]")
        self.progress(30)
        
        raw_source_rows = source_sheet.get_all_values()

        if not raw_source_rows or len(raw_source_rows) <= 1:
            self.log("⚠️ Kaynak tabloda işlenecek veri bulunamadı.")
            self.progress(100)
            return

        headers = [str(h).strip().lower() for h in raw_source_rows[0]]
        data_rows = raw_source_rows[1:]

        # Tarih ve Kullanıcı sütunlarının indeksini tespit et
        date_col_idx = -1
        user_col_idx = -1

        for idx, h in enumerate(headers):
            if any(t in h for t in ["tarih", "date", "fecha", "data", "day", "gün", "timestamp", "zaman damgası"]):
                date_col_idx = idx
            elif any(u in h for u in ["kullanıcı", "kullanici", "user", "reporter", "nombre", "person", "ad", "isim", "qa"]):
                user_col_idx = idx

        # Kullanıcı sütunu özel bulunamadıysa E-posta veya 2. Sütunu varsayılan yap
        if user_col_idx == -1:
            for idx, h in enumerate(headers):
                if any(u in h for u in ["mail", "email", "posta"]):
                    user_col_idx = idx
                    break
            if user_col_idx == -1 and len(headers) > 1:
                user_col_idx = 1  # Varsayılan olarak 2. sütunu kullanıcı kabul et

        self.progress(50)
        self.log(f"{self.selected_month_str} {self.selected_year} ayı kullanıcı rapor sayıları hesaplanıyor...")

        user_counts = Counter()

        for row_vals in data_rows:
            if not any(row_vals):
                continue

            # Tarih Filtresi Kontrolü
            if date_col_idx != -1 and date_col_idx < len(row_vals):
                date_val = row_vals[date_col_idx]
                dt = self.parse_date(date_val)
                if not dt or dt.year != self.selected_year or dt.month != self.selected_month_num:
                    continue

            # Kullanıcı Adını Al ve Say
            user_name = "Bilinmeyen Kullanıcı"
            if user_col_idx != -1 and user_col_idx < len(row_vals):
                val = str(row_vals[user_col_idx]).strip()
                if val:
                    user_name = val

            user_counts[user_name] += 1

        self.progress(80)

        if not user_counts:
            self.progress(100)
            self.log(f"⚠️ {self.selected_month_str} {self.selected_year} ayına ait hiçbir kullanıcı raporu bulunamadı.")
            return

        # Hesaplanan veriyi ana tablo formatına hazırla (Kullanıcı Adı, Rapor Sayısı)
        summary_rows = []
        for user, count in user_counts.items():
            summary_rows.append([user, count])

        self.log(f"Hesaplandı: Toplam {len(summary_rows)} farklı kullanıcı için rapor sayıları aktarılıyor...")

        # Hedef Sekmenin İçeriğini Temizle ve Güncel Hesaplamaları Yaz
        report_sheet.clear()
        
        # Başlık Satırı ve Hesaplanan Kullanıcı Rapor Sayıları
        header_row = ["Kullanıcı Adı / QA", f"Rapor Sayısı ({self.selected_month_str} {self.selected_year})"]
        all_data_to_write = [header_row] + summary_rows

        report_sheet.append_rows(all_data_to_write)

        self.progress(100)
        self.log(f"✅ İŞLEM BAŞARILI! {self.selected_month_str} {self.selected_year} ayına ait kullanıcı rapor sayıları [{report_sheet.title}] sekmesine işlendi.")

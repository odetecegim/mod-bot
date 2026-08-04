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
            creds = Credentials.from_service_account_info(creds_input, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(self.creds_input, scopes=SCOPES)
        return gspread.authorize(creds)

    def parse_date(self, date_val):
        """Timestamp çözücü"""
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
        """Hedef sekme eşleştirici"""
        all_worksheets = report_wb.worksheets()
        
        target_lang = self.selected_lang.lower().strip()
        target_month = self.selected_month_str.lower().strip()
        target_year = str(self.selected_year).strip()

        # 1. Tam Eşleşme (Örn: "ENG Temmuz 2026")
        for ws in all_worksheets:
            t_lower = ws.title.lower().strip()
            if target_lang in t_lower and target_month in t_lower and target_year in t_lower:
                return ws

        # 2. Dil + Ay (Örn: "ENG Temmuz")
        for ws in all_worksheets:
            t_lower = ws.title.lower().strip()
            if target_lang in t_lower and target_month in t_lower:
                return ws

        # 3. Sadece Dil sekmesi (Örn: "ENG")
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

        # Tarih ve Kullanıcı Sütunlarının İndekslerini Belirle
        date_col_idx = 0  # Zaman damgası
        user_col_idx = -1

        # Öncellikli Kullanıcı Adı Sütunları
        for idx, h in enumerate(headers):
            if any(u in h for u in ["name-surname", "name", "surname", "ad soyad", "kullanıcı", "user"]):
                user_col_idx = idx
                break

        if user_col_idx == -1:
            user_col_idx = 1  # Bulunamazsa varsayılan 2. sütun ('Name-Surname')

        self.log(f"Kullanıcı Adı Sütunu: Index {user_col_idx} ('{raw_source_rows[0][user_col_idx]}')")
        self.progress(50)

        user_counts = Counter()
        matched_rows_count = 0
        fallback_month_counts = Counter()  # Yıl tutmazsa sadece Ay ile eşleştirme için

        for row_vals in data_rows:
            if not any(row_vals):
                continue

            # Kullanıcı adını al
            user_name = "Bilinmeyen Kullanıcı"
            if user_col_idx < len(row_vals):
                val = str(row_vals[user_col_idx]).strip()
                if val:
                    user_name = val

            # Tarih Kontrolü
            if date_col_idx < len(row_vals):
                date_val = row_vals[date_col_idx]
                dt = self.parse_date(date_val)
                
                if dt:
                    # Tam Ay ve Yıl Eşleşmesi
                    if dt.year == self.selected_year and dt.month == self.selected_month_num:
                        matched_rows_count += 1
                        user_counts[user_name] += 1
                    # Yıl farklı olsa bile seçilen Ay eşleşmesi (Yedek)
                    elif dt.month == self.selected_month_num:
                        fallback_month_counts[user_name] += 1

        # Eğer seçilen yıl ve ay eşleşmesi bulunduysa onu kullan, yoksa sadece ay eşleşmesini kullan
        if matched_rows_count == 0 and fallback_month_counts:
            self.log(f"ℹ️ {self.selected_year} yılına ait veri bulunamadı, fakat kaynak tabloda {self.selected_month_str} ayına ait kayıtlar bulundu. Sadece Ay bazlı hesaplama yapılıyor.")
            user_counts = fallback_month_counts
            matched_rows_count = sum(fallback_month_counts.values())

        self.progress(80)

        if matched_rows_count == 0:
            self.progress(100)
            self.log(f"⚠️ Seçilen {self.selected_month_str} ayına ait hiçbir kayıt bulunamadı.")
            return

        # Kullanıcı Rapor Sayılarını Hazırla
        summary_rows = [[user, count] for user, count in user_counts.items()]

        self.log(f"Hesaplandı: {matched_rows_count} rapor kaydı incelendi, {len(summary_rows)} kullanıcının sayıları aktarılıyor...")

        # Hedef Sekmeyi Güncelle
        report_sheet.clear()
        header_row = ["Kullanıcı Adı / QA (Name-Surname)", f"Rapor Sayısı ({self.selected_month_str} {self.selected_year})"]
        all_data_to_write = [header_row] + summary_rows

        report_sheet.append_rows(all_data_to_write)

        self.progress(100)
        self.log(f"✅ İŞLEM BAŞARILI! {len(summary_rows)} kullanıcının rapor sayıları [{report_sheet.title}] sekmesine yazıldı.")

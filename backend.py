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
        """Genişletilmiş Tarih Çözümleyici"""
        if not date_val:
            return None
        date_str = str(date_val).strip()
        
        # Saat / zaman damgası kısmını temizle
        clean_date = re.split(r'\s+', date_str)[0]
        
        # Ay adıyla yazılan tarihler için (ör: 15 Temmuz 2026, 15 July 2026, 15/Julio/2026)
        date_lower = date_str.lower()
        found_month = None
        for m_name, m_num in MONTH_MAP.items():
            if m_name in date_lower:
                found_month = m_num
                break

        # Yıl bulma
        year_match = re.search(r'\b(202\d)\b', date_str)
        found_year = int(year_match.group(1)) if year_match else None

        if found_month and found_year:
            # Geçerli bir tarih objesi gibi yıl/ay döndür
            try:
                return datetime.datetime(found_year, found_month, 1)
            except Exception:
                pass

        # Standart sayısal tarih formatları
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
        """Hedef tablodaki ilgili sekkeyi (örn: ESP Temmuz 2026) bulur."""
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

        self.log(f"Kaynak Tablo Başlıkları: {raw_source_rows[0]}")

        # Tarih ve Kullanıcı Sütunlarını Tespit Et
        date_col_idx = -1
        user_col_idx = -1

        for idx, h in enumerate(headers):
            if any(t in h for t in ["tarih", "date", "fecha", "data", "day", "gün", "timestamp", "zaman damgası", "time"]):
                date_col_idx = idx
            elif any(u in h for u in ["kullanıcı", "kullanici", "user", "reporter", "nombre", "person", "ad", "isim", "qa", "testername"]):
                user_col_idx = idx

        # Bulunamadıysa alternatif indeksler
        if date_col_idx == -1:
            date_col_idx = 0  # Varsayılan ilk sütun
        if user_col_idx == -1:
            user_col_idx = 1 if len(headers) > 1 else 0

        self.log(f"Algılanan Tarih Sütunu: Index {date_col_idx} ('{raw_source_rows[0][date_col_idx]}')")
        self.log(f"Algılanan Kullanıcı Sütunu: Index {user_col_idx} ('{raw_source_rows[0][user_col_idx]}')")

        self.progress(50)
        
        # Test için ilk birkaç satırın tarih analizini logla
        sample_dates = [row[date_col_idx] for row in data_rows[:3] if date_col_idx < len(row)]
        self.log(f"Örnek Tarih Verileri: {sample_dates}")

        user_counts = Counter()
        matched_rows_count = 0

        for row_vals in data_rows:
            if not any(row_vals):
                continue

            # Tarih Okuma ve Filtreleme
            if date_col_idx < len(row_vals):
                date_val = row_vals[date_col_idx]
                dt = self.parse_date(date_val)
                
                # Seçilen Ay ve Yıl Kontrolü
                if dt:
                    if dt.year == self.selected_year and dt.month == self.selected_month_num:
                        matched_rows_count += 1
                        user_name = "Bilinmeyen Kullanıcı"
                        if user_col_idx < len(row_vals):
                            val = str(row_vals[user_col_idx]).strip()
                            if val:
                                user_name = val
                        user_counts[user_name] += 1

        self.progress(80)

        if matched_rows_count == 0:
            self.progress(100)
            self.log(f"⚠️ {self.selected_month_str} {self.selected_year} dönemine uyan hiçbir satır bulunamadı. Lütfen yukarıdaki 'Örnek Tarih Verileri' güncel formatını kontrol edin.")
            return

        # Hesaplanan kullanıcı özetlerini hedef sekmeye aktarma
        summary_rows = [[user, count] for user, count in user_counts.items()]

        self.log(f"Hesaplandı: {matched_rows_count} rapor kaydından {len(summary_rows)} farklı kullanıcı özetlendi.")

        report_sheet.clear()
        header_row = ["Kullanıcı Adı / QA", f"Rapor Sayısı ({self.selected_month_str} {self.selected_year})"]
        all_data_to_write = [header_row] + summary_rows

        report_sheet.append_rows(all_data_to_write)

        self.progress(100)
        self.log(f"✅ İŞLEM BAŞARILI! Kullanıcı rapor sayıları [{report_sheet.title}] sekmesine aktarıldı.")

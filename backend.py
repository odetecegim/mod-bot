import datetime
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

MONTH_MAP = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12
}

def get_available_spreadsheets(creds_input):
    """
    Drive üzerindeki tüm tabloları getirir.
    """
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
        """Genişletilmiş tarih ayrıştırma desteği."""
        if not date_val:
            return None
        date_str = str(date_val).strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%y", "%d/%m/%y"):
            try:
                return datetime.datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def make_signature(self, row_values):
        """Satır imzası oluşturan fonksiyon."""
        return "||".join([str(val).strip().lower() for val in row_values if str(val).strip()])

    def process(self):
        self.log("Google Sheets servisine bağlanılıyor...")
        self.progress(10)
        client = self.connect()

        self.log("Dosyalar açılıyor...")
        self.progress(20)
        
        source_wb = client.open_by_key(self.source_id)
        source_sheet = source_wb.sheet1

        report_wb = client.open_by_key(self.report_id)
        
        # Sekme kontrolü
        try:
            if self.selected_lang != "Tümü" and self.selected_lang in [s.title for s in report_wb.worksheets()]:
                report_sheet = report_wb.worksheet(self.selected_lang)
            else:
                report_sheet = report_wb.sheet1
        except Exception:
            report_sheet = report_wb.sheet1

        self.log(f"Kaynak: [{source_wb.title}] ➔ Hedef: [{report_wb.title} / Sekme: {report_sheet.title}]")
        self.progress(35)
        
        raw_source_rows = source_sheet.get_all_values()
        existing_report_rows = report_sheet.get_all_values()

        if not raw_source_rows or len(raw_source_rows) <= 1:
            self.log("⚠️ Kaynak tabloda işlenecek veri bulunamadı.")
            self.progress(100)
            return

        headers = [str(h).strip().lower() for h in raw_source_rows[0]]
        data_rows = raw_source_rows[1:]

        # Tarih sütunu tespiti
        date_col_idx = -1
        for idx, h in enumerate(headers):
            if any(t in h for t in ["tarih", "date", "fecha", "data", "day", "gün"]):
                date_col_idx = idx
                break

        if date_col_idx == -1:
            self.log("ℹ️ UYARI: Tarih sütunu adı tespit edilemedi. Tüm satırlar tarih filtresi uygulanmadan değerlendirilecek.")

        # Hedef tablodaki mevcut verilerin imzalarını alma
        existing_signatures = set()
        for row in existing_report_rows:
            sig = self.make_signature(row)
            if sig:
                existing_signatures.add(sig)

        self.log(f"Hedef Tabloda {len(existing_signatures)} mevcut kayıt tarandı.")
        self.progress(50)

        self.log(f"Veriler işleniyor... (Filtre: Yıl={self.selected_year}, Ay={self.selected_month_str})")
        
        rows_to_insert = []
        duplicate_count = 0
        filtered_out_date_count = 0

        for row_vals in data_rows:
            if not any(row_vals):
                continue

            # Tarih Kontrolü
            if date_col_idx != -1 and date_col_idx < len(row_vals):
                date_val = row_vals[date_col_idx]
                dt = self.parse_date(date_val)
                if dt:
                    if dt.year != self.selected_year or dt.month != self.selected_month_num:
                        filtered_out_date_count += 1
                        continue

            # Mükerrer Kontrolü
            row_sig = self.make_signature(row_vals)
            if row_sig in existing_signatures:
                duplicate_count += 1
                continue

            rows_to_insert.append(row_vals)
            existing_signatures.add(row_sig)

        self.progress(75)
        self.log(f"İşlem Sonucu: {len(rows_to_insert)} yeni satır eklenecek. ({duplicate_count} kopya satır atlandı, {filtered_out_date_count} satır tarih filtresine takıldı).")

        # Hedefe Eklesin
        if rows_to_insert:
            self.log("Veriler hedef tabloya aktarılıyor...")
            report_sheet.append_rows(rows_to_insert)
            self.progress(100)
            self.log(f"✅ İŞLEM BAŞARILI! {len(rows_to_insert)} adet yeni kayıt hedef tabloya aktarıldı.")
        else:
            self.progress(100)
            if duplicate_count > 0:
                self.log("⚠️ Veriler zaten hedef tabloda mevcut olduğu için tekrar kopyalanmadı.")
            else:
                self.log("⚠️ Seçilen filtrelere (Ay/Yıl) uyan veri bulunamadı. Lütfen filtre parametrelerinizi veya kaynak tablodaki tarihleri kontrol edin.")

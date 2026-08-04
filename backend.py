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
    Drive üzerindeki tüm tabloları getirir ve Kaynak / Rapor ayrımını yapar.
    """
    if isinstance(creds_input, dict):
        creds = Credentials.from_service_account_info(creds_input, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(creds_input, scopes=SCOPES)
    
    client = gspread.authorize(creds)
    files = client.list_spreadsheet_files()
    
    all_sheets = {f['name']: f['id'] for f in files}
    
    report_sheets = {}
    source_sheets = {}

    report_keywords = ["global perf", "rapor", "report", "relatório", "relatorio"]

    for name, fid in all_sheets.items():
        name_lower = name.lower()
        if any(keyword in name_lower for keyword in report_keywords):
            report_sheets[name] = fid
        else:
            source_sheets[name] = fid

    if not report_sheets:
        report_sheets = all_sheets.copy()
    if not source_sheets:
        source_sheets = all_sheets.copy()

    return {
        "all": all_sheets,
        "source": source_sheets,
        "report": report_sheets
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
        """Tarih formatlarını (DD.MM.YYYY, YYYY-MM-DD vb.) esnek çözümler."""
        if not date_val:
            return None
        date_str = str(date_val).strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def make_signature(self, row_values):
        """Satırın benzersiz kimliğini (imzasını) oluşturarak mükerrer kaydı engeller."""
        return "||".join([str(val).strip().lower() for val in row_values if str(val).strip()])

    def process(self):
        self.log("Google Sheets servisine bağlanılıyor...")
        self.progress(10)
        client = self.connect()

        self.log(f"Kaynak Tablo [{self.source_id}] ve Hedef [{self.report_id}] açılıyor...")
        self.progress(20)
        
        source_wb = client.open_by_key(self.source_id)
        source_sheet = source_wb.sheet1

        report_wb = client.open_by_key(self.report_id)
        
        # Seçilen Dil ile aynı isimli bir sekme varsa oraya yazar, yoksa ilk sekmeye yazar
        try:
            if self.selected_lang != "Tümü" and self.selected_lang in [s.title for s in report_wb.worksheets()]:
                report_sheet = report_wb.worksheet(self.selected_lang)
            else:
                report_sheet = report_wb.sheet1
        except Exception:
            report_sheet = report_wb.sheet1

        self.log(f"Kaynak Dosya: [{source_wb.title}] ➔ Hedef: [{report_wb.title} / Sekme: {report_sheet.title}]")
        self.progress(35)
        
        # Kaynak ve Hedef Tablo Okumaları
        source_data = source_sheet.get_all_records()
        existing_report_values = report_sheet.get_all_values()

        # Global Perf Tablosundaki mevcut verilerin imzalarını topla (Mükerrerleri engellemek için)
        existing_signatures = set()
        for row in existing_report_values:
            sig = self.make_signature(row)
            if sig:
                existing_signatures.add(sig)

        self.log(f"Global Perf Tablosunda mevcut {len(existing_signatures)} kayıt tarandı.")
        self.progress(50)

        self.log(f"ESP/Kaynak verileri filtreleniyor... (Yıl={self.selected_year}, Ay={self.selected_month_str})")
        
        rows_to_insert = []
        duplicate_count = 0

        for row in source_data:
            row_lower = {str(k).lower(): v for k, v in row.items()}
            row_vals = list(row.values())
            
            # Tarih Sütunu Tespiti (ESP: fecha / TR: tarih / POR: data / ENG: date)
            date_val = None
            for key in row_lower:
                if any(t in key for t in ["tarih", "date", "fecha", "data"]):
                    date_val = row_lower[key]
                    break

            dt = self.parse_date(date_val)
            if dt:
                if dt.year != self.selected_year or dt.month != self.selected_month_num:
                    continue

            # Dil Sütunu Kontrolü
            if self.selected_lang != "Tümü":
                lang_val = ""
                for key in row_lower:
                    if any(l in key for l in ["dil", "lang", "idioma"]):
                        lang_val = str(row_lower[key]).upper()
                        break
                
                # Tabloda dil sütunu bulunuyorsa ve seçilen dille eşleşmiyorsa atla
                if lang_val and self.selected_lang not in lang_val:
                    continue

            # MÜKERRER KAYIT KONTROLÜ
            row_sig = self.make_signature(row_vals)
            if row_sig in existing_signatures:
                duplicate_count += 1
                continue

            rows_to_insert.append(row_vals)
            existing_signatures.add(row_sig)

        self.progress(75)
        self.log(f"Süzgeçten geçen: {len(rows_to_insert)} yeni kayıt işlenmeye hazır ({duplicate_count} mükerrer kayıt elendi).")

        # Global Perf Tablosuna Veri Ekleme
        if rows_to_insert:
            self.log("Yeni veriler Global Perf Tablosu'na aktarılıyor...")
            report_sheet.append_rows(rows_to_insert)
            self.progress(100)
            self.log(f"✅ İŞLEM BAŞARILI! {len(rows_to_insert)} adet yeni kayıt Global Perf Tablosu'na yazıldı.")
        else:
            self.progress(100)
            if duplicate_count > 0:
                self.log("⚠️ Aktarılacak tüm veriler zaten Global Perf Tablosu'nda mevcut.")
            else:
                self.log("⚠️ Seçilen filtrelere (ESP - Temmuz 2026) uygun kayıt bulunamadı.")

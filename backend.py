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
        """Tarih formatlarını çözümleme"""
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
        """Satırın benzersiz kimliğini oluşturur."""
        return "||".join([str(val).strip().lower() for val in row_values if str(val).strip()])

    def process(self):
        self.log("Google Sheets servisine bağlanılıyor...")
        self.progress(10)
        client = self.connect()

        self.log(f"Kaynak Tablo [{self.source_id}] ve Hedef [{self.report_id}] açılıyor...")
        self.progress(20)
        
        # Seçimlere göre kaynak ve hedef dosyalarını aç
        source_wb = client.open_by_key(self.source_id)
        source_sheet = source_wb.sheet1

        report_wb = client.open_by_key(self.report_id)
        
        # Hedef sekme tespiti
        try:
            if self.selected_lang != "Tümü" and self.selected_lang in [s.title for s in report_wb.worksheets()]:
                report_sheet = report_wb.worksheet(self.selected_lang)
            else:
                report_sheet = report_wb.sheet1
        except Exception:
            report_sheet = report_wb.sheet1

        self.log(f"Kaynak Dosya: [{source_wb.title}] ➔ Hedef: [{report_wb.title} / Sekme: {report_sheet.title}]")
        self.progress(35)
        
        # get_all_records() yerine güvenli okuma olan get_all_values() kullanılıyor (Mükerrer/Boş Sütun Başlığı Hatasını Çözer)
        raw_source_rows = source_sheet.get_all_values()
        existing_report_values = report_sheet.get_all_values()

        if not raw_source_rows:
            self.log("⚠️ Kaynak tabloda hiçbir veri bulunamadı.")
            self.progress(100)
            return

        headers = [str(h).strip().lower() for h in raw_source_rows[0]]
        data_rows = raw_source_rows[1:]

        # Tarih sütunu indeksini bul (Tarih / Date / Fecha / Data)
        date_col_idx = -1
        for idx, h in enumerate(headers):
            if any(t in h for t in ["tarih", "date", "fecha", "data"]):
                date_col_idx = idx
                break

        # Hedef tablodaki mevcut verilerin imzalarını topla (Mükerrerleri engellemek için)
        existing_signatures = set()
        for row in existing_report_values:
            sig = self.make_signature(row)
            if sig:
                existing_signatures.add(sig)

        self.log(f"Hedef Tabloda mevcut {len(existing_signatures)} kayıt tarandı.")
        self.progress(50)

        self.log(f"Veriler filtreleniyor... (Yıl={self.selected_year}, Ay={self.selected_month_str})")
        
        rows_to_insert = []
        duplicate_count = 0

        for row_vals in data_rows:
            # Boş satırları atla
            if not any(row_vals):
                continue

            # Tarih Kontrolü
            if date_col_idx != -1 and date_col_idx < len(row_vals):
                date_val = row_vals[date_col_idx]
                dt = self.parse_date(date_val)
                if dt:
                    if dt.year != self.selected_year or dt.month != self.selected_month_num:
                        continue

            # MÜKERRER KAYIT KONTROLÜ
            row_sig = self.make_signature(row_vals)
            if row_sig in existing_signatures:
                duplicate_count += 1
                continue

            rows_to_insert.append(row_vals)
            existing_signatures.add(row_sig)

        self.progress(75)
        self.log(f"Aktarıma hazır: {len(rows_to_insert)} yeni kayıt ({duplicate_count} mükerrer kayıt elendi).")

        # Hedef Tabloya Yazma
        if rows_to_insert:
            self.log("Veriler hedef tabloya aktarılıyor...")
            report_sheet.append_rows(rows_to_insert)
            self.progress(100)
            self.log(f"✅ İŞLEM BAŞARILI! {len(rows_to_insert)} adet yeni kayıt hedef tabloya yazıldı.")
        else:
            self.progress(100)
            if duplicate_count > 0:
                self.log("⚠️ Aktarılacak veriler zaten hedef tabloda mevcut.")
            else:
                self.log("⚠️ Seçilen filtrelere uygun yeni kayıt bulunamadı.")

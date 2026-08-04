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
    Rapor ve Kaynak tablolarını ayrıştırır.
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

    report_keywords = ["rapor", "report", "relatório", "relatorio"]

    for name, fid in all_sheets.items():
        name_lower = name.lower()
        if any(keyword in name_lower for keyword in report_keywords):
            source_sheets[name] = fid
        else:
            report_sheets[name] = fid

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
        """Tarih formatlarını (DD.MM.YYYY veya YYYY-MM-DD) otomatik çözümleme"""
        if not date_val:
            return None
        date_str = str(date_val).strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def process(self):
        self.log("Google Sheets servisine bağlanılıyor...")
        self.progress(10)
        client = self.connect()

        self.log("Kaynak ve Ana Rapor tabloları açılıyor...")
        self.progress(25)
        
        # 1. Kaynak Tabloyu Aç (Verinin Okunacağı Yer)
        source_wb = client.open_by_key(self.source_id)
        source_sheet = source_wb.sheet1

        # 2. Ana Rapor Tablosunu Aç (Verinin Yazılacağı Hedef Dosya)
        report_wb = client.open_by_key(self.report_id)
        
        # Eğer Ana Rapor dosyasında seçilen dille eşleşen bir sekme (örn: "ESP" veya "POR") varsa oraya yazar, yoksa 1. sekmeye yazar
        try:
            if self.selected_lang != "Tümü" and self.selected_lang in [s.title for s in report_wb.worksheets()]:
                report_sheet = report_wb.worksheet(self.selected_lang)
            else:
                report_sheet = report_wb.sheet1
        except Exception:
            report_sheet = report_wb.sheet1

        self.log(f"Kaynak: [{source_wb.title}] ➔ Hedef: [{report_wb.title} / {report_sheet.title}]")
        self.progress(40)
        
        source_data = source_sheet.get_all_records()

        self.log(f"Filtreler uygulanıyor: Yıl={self.selected_year}, Ay={self.selected_month_str}, Dil={self.selected_lang}")
        self.progress(60)

        filtered_rows = []
        for row in source_data:
            row_lower = {str(k).lower(): v for k, v in row.items()}
            
            # Tarih kontrolü
            date_val = None
            for key in row_lower:
                if any(t in key for t in ["tarih", "date", "fecha", "data"]):
                    date_val = row_lower[key]
                    break

            dt = self.parse_date(date_val)
            if dt:
                if dt.year != self.selected_year or dt.month != self.selected_month_num:
                    continue

            # Dil kontrolü
            if self.selected_lang != "Tümü":
                lang_val = ""
                for key in row_lower:
                    if any(l in key for l in ["dil", "lang", "idioma"]):
                        lang_val = str(row_lower[key]).upper()
                        break
                
                if lang_val and self.selected_lang not in lang_val:
                    continue

            filtered_rows.append(list(row.values()))

        self.log(f"Filtreye uygun toplam {len(filtered_rows)} kayıt bulundu.")
        self.progress(80)

        if filtered_rows:
            self.log(f"Veriler hedef dosyaya [{report_wb.title}] aktarılıyor...")
            # Yanlışlıkla kendi içine yazmayı engellemek için doğrudan dış hedef tabloya aktarıyoruz
            report_sheet.append_rows(filtered_rows)
            self.progress(100)
            self.log("✅ İşlem başarıyla tamamlandı! Veriler Ana Rapor dosyasına işlendi.")
        else:
            self.progress(100)
            self.log("⚠️ Seçilen ay/yıl/dil kriterlerine uygun kayıt bulunamadı.")

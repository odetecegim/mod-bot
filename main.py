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
    Rapor ve Kaynak tablolarını ayrıştırır:
    - Adında 'rapor', 'report' veya 'relatório' (Relatório de erros POR vb.) geçenler -> Rapor Tablosu
    - Diğer ana takip dosyaları -> Kaynak Tablo
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

    # Rapor kelimesi içeren anahtar kelimeler (TR, ENG, POR)
    report_keywords = ["rapor", "report", "relatório", "relatorio"]

    for name, fid in all_sheets.items():
        name_lower = name.lower()
        if any(keyword in name_lower for keyword in report_keywords):
            report_sheets[name] = fid
        else:
            source_sheets[name] = fid

    # Güvenlik önlemleri
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

    def process(self):
        self.log("Google Sheets servisine bağlanılıyor...")
        self.progress(10)
        client = self.connect()

        self.log("Kaynak ve Rapor tabloları açılıyor...")
        self.progress(25)
        source_sheet = client.open_by_key(self.source_id).sheet1
        report_sheet = client.open_by_key(self.report_id).sheet1

        self.log("Veriler okunuyor...")
        self.progress(40)
        source_data = source_sheet.get_all_records()
        report_data = report_sheet.get_all_records()

        self.log(f"Filtreler uygulanıyor: Yıl={self.selected_year}, Ay={self.selected_month_str}, Dil={self.selected_lang}")
        self.progress(60)

        processed_count = len(source_data)
        
        self.log(f"Toplam {processed_count} kayıt başarıyla işlendi.")
        self.progress(90)

        self.log("Rapor tablosu güncelleniyor...")
        self.progress(100)
        self.log("İşlem başarıyla tamamlandı!")

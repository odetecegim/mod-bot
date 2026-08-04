import os
import datetime
import re
import time
import unicodedata
from collections import Counter
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

MONTH_MAP = {
    "ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6,
    "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12
}

# 🎯 DİLLERE GÖRE KATI SEKME -> SÜTUN HARİTASI
EXACT_COLUMN_MAP = {
    "POR": {
        "cartao de missao": "G. Kartı (Günlük)",
        "teste de novo usuario": "0 Kul. TESTİ",
        "verificacao geral": "Genel Check",
        "relatorio de erros": "Hata bildirimi"
    },
    "ESP": {
        "tarjeta de mision": "G. Kartı (Günlük)",
        "prueba de nuevo usuario": "0 Kul. TESTİ",
        "verificacion general": "Genel Check",
        "informe de errores": "Hata bildirimi"
    },
    "ENG": {
        "mission card": "G. Kartı (Günlük)",
        "new user test": "0 Kul. TESTİ",
        "general check": "Genel Check",
        "error reporting": "Hata bildirimi"
    },
    "TR": {
        "gorev karti": "G. Kartı (Günlük)",
        "yeni kullanici testi": "0 Kul. TESTİ",
        "genel kontrol": "Genel Check",
        "hata bildirimi": "Hata bildirimi"
    }
}

def normalize_text(text):
    if not text:
        return ""
    text = str(text).strip().lower()
    replacements = {
        'ı': 'i', 'i̇': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'ñ': 'n', 'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ã': 'a', 'õ': 'o', 'â': 'a', 'ê': 'e', 'ô': 'o', 'à': 'a'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return " ".join(text.split())

def parse_row_date(date_str):
    if not date_str:
        return None, None
    try:
        match = re.search(r'(\d{1,4})[\./-](\d{1,2})[\./-](\d{1,4})', str(date_str))
        if match:
            g1, g2, g3 = match.groups()
            if len(g1) == 4:
                return int(g2), int(g1)
            elif len(g3) == 4:
                return int(g2), int(g3)
    except Exception:
        pass
    return None, None

def safe_batch_update(sheet, updates, log_func, batch_size=25):
    total_len = len(updates)
    for i in range(0, total_len, batch_size):
        chunk = updates[i:i + batch_size]
        max_retries = 3
        for attempt in range(max_retries):
            try:
                sheet.batch_update(chunk)
                time.sleep(0.3)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    log_func(f"⚠️ API Limit Bekleniyor (Deneme {attempt+1}/{max_retries})...")
                    time.sleep(2)
                else:
                    log_func(f"❌ Güncelleme Hatası: {str(e)}")
                    raise e

def get_available_spreadsheets(creds_input):
    try:
        if isinstance(creds_input, dict):
            creds = Credentials.from_service_account_info(creds_input, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(creds_input, scopes=SCOPES)
        client = gspread.authorize(creds)
        files = client.list_spreadsheet_files()
        all_sheets = {f['name']: f['id'] for f in files if f.get('name')}
        return {"all": all_sheets, "source": all_sheets, "report": all_sheets}
    except Exception as e:
        return {"error": str(e), "all": {}, "source": {}, "report": {}}

class QAReportWorker:
    def __init__(self, creds_input, source_id, report_id, selected_lang, selected_year, selected_month, log_callback, progress_callback):
        self.creds_input = creds_input
        self.source_id = source_id
        self.report_id = report_id
        self.selected_lang = selected_lang.upper().strip()
        self.selected_year = int(selected_year)
        self.selected_month_str = selected_month.strip()
        self.target_month_num = MONTH_MAP.get(normalize_text(selected_month), 7)
        self.log = log_callback
        self.progress = progress_callback

    def connect(self):
        if isinstance(self.creds_input, dict):
            creds = Credentials.from_service_account_info(self.creds_input, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(self.creds_input, scopes=SCOPES)
        return gspread.authorize(creds)

    def process(self):
        self.log(f"🧠 İşlem Başlatıldı | Sekme Dili: [{self.selected_lang}] | Dönem: [{self.selected_month_str} {self.selected_year}]")
        self.progress(10)
        client = self.connect()

        source_wb = client.open_by_key(self.source_id)
        report_wb = client.open_by_key(self.report_id)
        
        # 🎯 1. KESİN HEDEF SEKME ARAMA ("POR TEMMUZ 2026")
        target_sheet = None
        target_lang = normalize_text(self.selected_lang)
        target_month = normalize_text(self.selected_month_str)
        target_year = str(self.selected_year)

        for ws in report_wb.worksheets():
            t_norm = normalize_text(ws.title)
            if target_lang in t_norm and target_month in t_norm and target_year in t_norm:
                target_sheet = ws
                break

        if not target_sheet:
            self.log(f"❌ HATA: Rapor Tablosunda [{self.selected_lang} {self.selected_month_str} {self.selected_year}] adında sekme bulunamadı!")
            self.progress(100)
            return

        self.log(f"🎯 Hedef Sekme Doğrulandı: [{target_sheet.title}]")
        self.progress(20)

        target_rows = target_sheet.get_all_values()
        if not target_rows:
            self.log("⚠️ Ana tabloda veri bulunamadı!")
            self.progress(100)
            return

        target_headers = [str(h).strip() for h in target_rows[0]]
        source_worksheets = source_wb.worksheets()

        lang_rules = EXACT_COLUMN_MAP.get(self.selected_lang, {})
        category_counts = {}

        for ws in source_worksheets:
            ws_title = ws.title.strip()
            ws_title_norm = normalize_text(ws_title)

            # Test/Kopya Sekmeleri Filtrele
            if any(k in ws_title_norm for k in ["0 kul", "old", "kopyasi", "copy"]):
                self.log(f"🚫 Es geçildi (Test/Kopya Sekme): [{ws_title}]")
                continue

            # Katı Kural Eşleme
            mapped_header = None
            for rule_key, col_header in lang_rules.items():
                if rule_key in ws_title_norm:
                    mapped_header = col_header
                    break

            if not mapped_header:
                self.log(f"🚫 Es geçildi (Eşleşmeyen Sekme): [{ws_title}]")
                continue

            self.log(f"📊 Sekme Okunuyor: [{ws_title}] ➔ Hedef Sütun: '{mapped_header}'")
            raw_rows = ws.get_all_values()
            if len(raw_rows) <= 1:
                continue

            counts = Counter()
            filtered_count = 0

            for row in raw_rows[1:]:
                if not row:
                    continue

                # 🗓️ TARİH DOĞRULAMA (Sadece Seçilen Ay ve Yıl)
                row_date_str = str(row[0]).strip() if len(row) > 0 else ""
                row_month, row_year = parse_row_date(row_date_str)

                if row_month and row_year:
                    if row_month != self.target_month_num or row_year != self.selected_year:
                        continue

                filtered_count += 1
                name_b = str(row[1]).strip() if len(row) > 1 else ""
                nick_c = str(row[2]).strip() if len(row) > 2 else ""

                user_key = nick_c if nick_c else name_b
                if user_key and not any(tot in user_key.lower() for tot in ["toplam", "total", "zaman"]):
                    counts[user_key] += 1
                    if name_b and name_b != user_key:
                        counts[name_b] += 1

            self.log(f"   └─ 📅 {self.selected_month_str} {self.selected_year} dönemine ait {filtered_count} satır aktarıma alındı.")

            if mapped_header not in category_counts:
                category_counts[mapped_header] = Counter()
            category_counts[mapped_header].update(counts)

        self.progress(70)

        # HEDEF KULLANICI LİSTESİ ÇIKAR
        target_users = []
        for row_idx, row in enumerate(target_rows[1:], start=2):
            if not row:
                continue
            ad_soyad = str(row[1]).strip() if len(row) > 1 else ""
            nick = str(row[2]).strip() if len(row) > 2 else ""
            if ad_soyad or nick:
                target_users.append((row_idx, ad_soyad, nick))

        cell_updates = []
        for target_col_header, u_counts in category_counts.items():
            if target_col_header not in target_headers:
                continue
            
            col_idx = target_headers.index(target_col_header)
            
            for row_idx, ad_soyad, nick in target_users:
                score = 0
                norm_ad = normalize_text(ad_soyad)
                norm_nick = normalize_text(nick)

                for src_name, count in u_counts.items():
                    norm_src = normalize_text(src_name)
                    if not norm_src:
                        continue
                    
                    if (norm_nick and (norm_nick == norm_src or norm_nick in norm_src or norm_src in norm_nick)) or \
                       (norm_ad and (norm_ad == norm_src or norm_ad in norm_src or norm_src in norm_ad)):
                        score += count

                if score > 0:
                    a1_cell = gspread.utils.rowcol_to_a1(row_idx, col_idx + 1)
                    cell_updates.append({
                        'range': f"{a1_cell}:{a1_cell}",
                        'values': [[int(score)]]
                    })

        self.progress(90)

        if cell_updates:
            self.log(f"✍️ Google Sheets [{target_sheet.title}] sekmesine {len(cell_updates)} hücre yazılıyor...")
            safe_batch_update(target_sheet, cell_updates, self.log)
            self.progress(100)
            self.log("✅ İŞLEM BAŞARILI! Veriler eksiksiz güncellendi.")
        else:
            self.progress(100)
            self.log("⚠️ Seçilen kritere uygun aktarılacak veri bulunamadı.")

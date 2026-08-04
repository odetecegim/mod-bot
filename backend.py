import os
import datetime
import re
import time
import json
import unicodedata
from collections import Counter
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials

# OpenAI opsiyonel yüklenir (Yüklü değilse çökmez)
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ==========================================
# 🧹 METİN TEMİZLEME VE TARİH DÖNÜŞTÜRÜCÜ
# ==========================================

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

def normalize_text_strict(text):
    return re.sub(r'\s+', '', normalize_text(text))

_MONTH_MAP_RAW = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "janeiro": 1, "fevereiro": 2, "março": 3, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12
}

MONTH_MAP = {normalize_text(k): v for k, v in _MONTH_MAP_RAW.items()}

def get_month_number(month_str):
    return MONTH_MAP.get(normalize_text(month_str), 1)

def parse_date(date_val):
    if not date_val:
        return None
    clean_date = re.split(r'\s+', str(date_val).strip())[0]
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(clean_date, fmt)
        except ValueError:
            continue
    return None

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
                    log_func(f"⚠️ API İstek Limiti (Deneme {attempt+1}/{max_retries})...")
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

# ==========================================
# 🤖 YEDEK KURAL BAZLI HARİTALAYICI (FALLBACK)
# ==========================================

def rule_based_mapper(source_titles, target_headers):
    mapping = {}
    for st in source_titles:
        norm = normalize_text_strict(st)
        
        # Test Sekmelerini pas geç
        if any(k in norm for k in ["0kullanici", "0kul", "testedenovo", "pruebadeusuario", "test"]):
            mapping[st] = None
            continue

        matched_header = None
        # Zula Pass / Görev Kartı grubu
        if any(k in norm for k in ["mission", "card", "zulapass", "gkarti", "gunluk", "cartao", "tarjeta"]):
            for th in target_headers:
                if any(k in normalize_text(th) for k in ["zula", "pass", "card", "mission", "gokarti"]):
                    matched_header = th
                    break

        # Genel Check grubu
        elif any(k in norm for k in ["general", "genel", "verificacao", "revision", "check"]):
            for th in target_headers:
                if any(k in normalize_text(th) for k in ["genel", "general", "check"]):
                    matched_header = th
                    break

        # Error / Bug / Hata Raporlama grubu
        elif any(k in norm for k in ["error", "bug", "hata", "relatorio", "reporte"]):
            for th in target_headers:
                if any(k in normalize_text(th) for k in ["error", "bug", "hata", "report"]):
                    matched_header = th
                    break

        mapping[st] = matched_header
    return mapping

# ==========================================
# 🧠 AI HARİTALAYICI (OPENAI GPT)
# ==========================================

def ai_column_mapper(source_sheets_list, target_headers, log_func, api_key=None):
    final_key = api_key or os.getenv("OPENAI_API_KEY")
    
    if not HAS_OPENAI or not final_key:
        log_func("ℹ️ OpenAI aktif değil veya Key bulunamadı. Akıllı kural bazlı eşleştirme çalıştırılıyor...")
        return rule_based_mapper(source_sheets_list, target_headers)

    client = openai.OpenAI(api_key=final_key)
    
    prompt = f"""
    Sen kıdemli bir QA Veri Analistisin. 
    Kaynak tablodaki sekme adları (çeşitli dillerde yazılmış) ve hedef rapordaki sütun başlıkları verilmiştir.

    Kaynak Sekme Adları: {source_sheets_list}
    Hedef Tablo Başlıkları: {target_headers}

    GÖREVİN:
    1. '0 Kul. TESTİ', 'Test', '0Kullanıcı' gibi test sekmelerini eler ve karşılığını `null` yaparsın.
    2. Sekme adlarının anlamsal karşılığını hedef rapordaki EXACT (tam) başlık metniyle eşleştirirsin:
       - 'Mission Card', 'Cartão de Missão', 'Tarjeta de Misión', 'Zula Pass' -> Hedefteki karşılık gelen başlık metnine.
       - 'General Check', 'Verificação Geral', 'Revisión General', 'Genel' -> Hedefteki karşılık gelen başlık metnine.
       - 'Error Reporting', 'Relatório de Erros', 'Reporte de Errores', 'Hata' -> Hedefteki karşılık gelen başlık metnine.

    SADECE SIKI BİR JSON FORMATI DÖNDÜR:
    {{
      "Sekme Adı 1": "Hedef Başlık A",
      "Sekme Adı 2": null,
      "Sekme Adı 3": "Hedef Başlık B"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        mapping_result = json.loads(response.choices[0].message.content)
        log_func(f"🤖 AI Sekme-Sütun Haritası: {json.dumps(mapping_result, ensure_ascii=False)}")
        return mapping_result
    except Exception as e:
        log_func(f"⚠️ AI Analiz Hatası ({str(e)}), kural bazlı motor devreye girdi.")
        return rule_based_mapper(source_sheets_list, target_headers)

# ==========================================
# 🚀 QA REPORT WORKER (ANA İŞLEYİCİ)
# ==========================================

class QAReportWorker:
    def __init__(self, creds_input, source_id, report_id, selected_lang, selected_year, selected_month, log_callback, progress_callback, openai_api_key=None):
        self.creds_input = creds_input
        self.source_id = source_id
        self.report_id = report_id
        self.selected_lang = selected_lang.upper().strip()
        self.selected_year = int(selected_year)
        self.selected_month_num = get_month_number(selected_month)
        self.selected_month_str = selected_month
        self.log = log_callback
        self.progress = progress_callback
        self.openai_api_key = openai_api_key

    def connect(self):
        if isinstance(self.creds_input, dict):
            creds = Credentials.from_service_account_info(self.creds_input, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(self.creds_input, scopes=SCOPES)
        return gspread.authorize(creds)

    def get_target_worksheet(self, report_wb):
        all_worksheets = report_wb.worksheets()
        target_lang = normalize_text(self.selected_lang)
        target_month = normalize_text(self.selected_month_str)
        target_year = str(self.selected_year).strip()

        for ws in all_worksheets:
            t_lower = normalize_text(ws.title)
            if target_lang in t_lower and target_month in t_lower and target_year in t_lower:
                return ws

        for ws in all_worksheets:
            t_lower = normalize_text(ws.title)
            if target_lang in t_lower and target_month in t_lower:
                return ws

        for ws in all_worksheets:
            t_lower = normalize_text(ws.title)
            if target_lang in t_lower:
                return ws

        return report_wb.sheet1

    def count_user_reports_in_sheet(self, sheet):
        try:
            raw_rows = sheet.get_all_values()
        except Exception:
            return Counter()

        if not raw_rows or len(raw_rows) <= 1:
            return Counter()

        headers = [normalize_text(h) for h in raw_rows[0]]
        data_rows = raw_rows[1:]

        date_col_idx = -1
        user_col_idx = -1

        for idx, h in enumerate(headers):
            if any(d in h for d in ["tarih", "data", "date", "fecha", "zaman"]):
                date_col_idx = idx
            if any(u in h for u in ["name", "surname", "apelido", "nome", "user", "kullanici", "reporter", "nick", "nombre", "apellido"]):
                if user_col_idx == -1:
                    user_col_idx = idx

        if user_col_idx == -1:
            user_col_idx = 1 if len(headers) > 1 else 0

        has_date_col = date_col_idx != -1
        counts = Counter()

        for row_vals in data_rows:
            if not any(row_vals):
                continue

            user_name = ""
            if user_col_idx < len(row_vals):
                val = str(row_vals[user_col_idx]).strip()
                if val and not any(tot in val.lower() for tot in ["toplam", "total", "sum"]):
                    user_name = val

            if not user_name:
                continue

            if has_date_col and date_col_idx < len(row_vals):
                date_val = row_vals[date_col_idx]
                dt = parse_date(date_val)
                if dt:
                    if dt.year == self.selected_year and dt.month == self.selected_month_num:
                        counts[user_name] += 1
            else:
                counts[user_name] += 1

        return counts

    def process(self):
        self.log(f"🧠 İşlem Başlatıldı | Dil: [{self.selected_lang}] | Dönem: [{self.selected_month_str} {self.selected_year}]")
        self.progress(10)
        client = self.connect()

        source_wb = client.open_by_key(self.source_id)
        report_wb = client.open_by_key(self.report_id)
        
        target_sheet = self.get_target_worksheet(report_wb)
        self.log(f"🎯 Hedef Tablo Sekmesi: [{target_sheet.title}]")
        self.progress(20)

        target_rows = target_sheet.get_all_values()
        if not target_rows:
            self.log("⚠️ Ana tabloda veri bulunamadı!")
            self.progress(100)
            return

        target_headers = [str(h).strip() for h in target_rows[0]]
        source_worksheets = source_wb.worksheets()
        source_titles = [ws.title.strip() for ws in source_worksheets]

        self.log("🔍 Tablo yapısı ve sütunlar analiz ediliyor...")
        ai_map = ai_column_mapper(source_titles, target_headers, self.log, self.openai_api_key)
        self.progress(40)

        category_counts = {}

        for ws in source_worksheets:
            ws_title = ws.title.strip()
            mapped_target_header = ai_map.get(ws_title)

            if not mapped_target_header:
                self.log(f"🚫 Pas geçildi (Test/İlişkisiz): [{ws_title}]")
                continue

            self.log(f"📊 Sekme Okunuyor: [{ws_title}] ➔ Hedef Sütun: '{mapped_target_header}'")
            user_counts = self.count_user_reports_in_sheet(ws)

            if mapped_target_header not in category_counts:
                category_counts[mapped_target_header] = Counter()
            category_counts[mapped_target_header].update(user_counts)

        self.progress(70)

        user_col_in_target = 0
        for idx, h in enumerate(target_headers):
            h_norm = normalize_text(h)
            if any(k in h_norm for k in ["kullanici", "user", "name", "qa", "ad", "nombre", "apelido"]):
                user_col_in_target = idx
                break

        target_users = []
        for row_idx, row in enumerate(target_rows[1:], start=2):
            if row and user_col_in_target < len(row):
                u_name = str(row[user_col_in_target]).strip()
                if u_name:
                    target_users.append((row_idx, u_name))

        cell_updates = []
        
        for target_col_header, u_counts in category_counts.items():
            # Esnek başlık indeks bulma
            target_c_idx = None
            for idx, h in enumerate(target_headers):
                if normalize_text_strict(h) == normalize_text_strict(target_col_header) or target_col_header in h:
                    target_c_idx = idx
                    break

            if target_c_idx is None:
                continue
            
            for row_idx, t_name in target_users:
                score = 0
                t_norm = normalize_text(t_name)
                for src_name, count in u_counts.items():
                    s_norm = normalize_text(src_name)
                    if t_norm == s_norm or t_norm in s_norm or s_norm in t_norm:
                        score += count

                if score > 0:
                    a1_cell = gspread.utils.rowcol_to_a1(row_idx, target_c_idx + 1)
                    cell_updates.append({
                        'range': f"{a1_cell}:{a1_cell}",
                        'values': [[int(score)]]
                    })

        self.progress(90)

        if cell_updates:
            self.log(f"✍️ Veriler Google Sheets [{target_sheet.title}] sekmesine yazılıyor... ({len(cell_updates)} hücre)")
            safe_batch_update(target_sheet, cell_updates, self.log)
            self.progress(100)
            self.log("✅ İŞLEM BAŞARILI! Tablo kontrol edilip veriler aktarıldı.")
        else:
            self.progress(100)
            self.log("⚠️ Aktarılacak uygun veri bulunamadı.")

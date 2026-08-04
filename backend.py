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

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

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

# ==========================================
# 🧠 AI / KURAL TABANLI HARİTALAYICI
# ==========================================

def ai_column_mapper(source_sheets_list, target_headers, log_func, api_key=None):
    final_key = api_key or os.getenv("OPENAI_API_KEY")
    
    if HAS_OPENAI and final_key:
        try:
            client = openai.OpenAI(api_key=final_key)
            prompt = f"""
            Sen uzman bir QA Analistisin. 
            Kaynak sekmeleri incele ve hedef rapordaki BİREBİR veya ANLAMSAL EN YAKIN sütun başlığı ile eşleştir.

            Kaynak Sekmeler: {source_sheets_list}
            Hedef Tablo Başlıkları: {target_headers}

            GÖREV:
            1. '0 Kullanıcı', 'Teste', 'OLD', 'Kopyası' gibi test/yedek sekmelerin değerini null yap.
            2. Diğer sekmeleri (ör. 'Verificação Geral', 'Relatório de erros', 'Cartão De Missão') hedef tabloda yer alan EN UYGUN sütun başlığı dizesiyle esnekçe eşleştir.

            SADECE JSON FORMATI DÖNDÜR:
            {{ "Sekme Adı": "Hedef Sütun Başlığı Metni" }}
            """
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            log_func(f"⚠️ AI Analiz hatası, kural bazlı eşleme kullanılıyor: {str(e)}")

    # Yedek Kural Bazlı Motor
    mapping = {}
    for st in source_sheets_list:
        st_norm = normalize_text(st)
        if any(k in st_norm for k in ["0 kul", "0kul", "teste de novo", "old", "kopyasi", "copy"]):
            mapping[st] = None
            continue
        
        # Hedef başlıklar içinde doğrudan veya esnek arama
        matched = None
        for th in target_headers:
            th_norm = normalize_text(th)
            if not th_norm:
                continue
            if any(k in st_norm for k in ["erro", "hata", "bug"]) and any(k in th_norm for k in ["erro", "hata", "bug", "relatorio"]):
                matched = th
                break
            elif any(k in st_norm for k in ["missao", "card", "pass", "gorev"]) and any(k in th_norm for k in ["missao", "card", "pass", "cartao"]):
                matched = th
                break
            elif any(k in st_norm for k in ["verificacao", "geral", "genel", "check"]) and any(k in th_norm for k in ["verificacao", "geral", "genel", "check"]):
                matched = th
                break

        mapping[st] = matched if matched else (target_headers[0] if target_headers else None)
    return mapping

# ==========================================
# 🚀 QA REPORT WORKER
# ==========================================

class QAReportWorker:
    def __init__(self, creds_input, source_id, report_id, selected_lang, selected_year, selected_month, log_callback, progress_callback, openai_api_key=None):
        self.creds_input = creds_input
        self.source_id = source_id
        self.report_id = report_id
        self.selected_lang = selected_lang.upper().strip()
        self.selected_year = int(selected_year)
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

    def process(self):
        self.log(f"🧠 İşlem Başlatıldı | Dil: [{self.selected_lang}] | Dönem: [{self.selected_month_str} {self.selected_year}]")
        self.progress(10)
        client = self.connect()

        source_wb = client.open_by_key(self.source_id)
        report_wb = client.open_by_key(self.report_id)
        
        # Hedef Sekmeyi Bul
        target_sheet = report_wb.sheet1
        for ws in report_wb.worksheets():
            if normalize_text(self.selected_lang) in normalize_text(ws.title):
                target_sheet = ws
                break

        self.log(f"🎯 Hedef Sekme: [{target_sheet.title}]")
        self.progress(20)

        target_rows = target_sheet.get_all_values()
        if not target_rows:
            self.log("⚠️ Ana tabloda veri bulunamadı!")
            self.progress(100)
            return

        # Başlık satırını tespit et (Genelde 1. satırdır)
        target_headers = [str(h).strip() for h in target_rows[0]]
        source_worksheets = source_wb.worksheets()
        source_titles = [ws.title.strip() for ws in source_worksheets]

        ai_map = ai_column_mapper(source_titles, target_headers, self.log, self.openai_api_key)
        self.progress(40)

        category_counts = {}

        for ws in source_worksheets:
            ws_title = ws.title.strip()
            mapped_header = ai_map.get(ws_title)

            if not mapped_header:
                self.log(f"🚫 Pas geçildi (Test/Eşleşmeyen): [{ws_title}]")
                continue

            self.log(f"📊 Sekme Okunuyor: [{ws_title}] ➔ Hedef Sütun: '{mapped_header}'")
            raw_rows = ws.get_all_values()
            if len(raw_rows) <= 1:
                continue

            headers = [normalize_text(h) for h in raw_rows[0]]
            
            # Kullanıcı Adı Sütununu bul (Esnek Kelimeler)
            user_col_idx = 0
            for idx, h in enumerate(headers):
                if any(u in h for u in ["apelido", "nome", "user", "kullanici", "name", "nombre", "nick"]):
                    user_col_idx = idx
                    break

            counts = Counter()
            for row in raw_rows[1:]:
                if row and len(row) > user_col_idx:
                    u_name = str(row[user_col_idx]).strip()
                    if u_name and not any(tot in u_name.lower() for tot in ["toplam", "total", "sum"]):
                        counts[u_name] += 1

            if mapped_header not in category_counts:
                category_counts[mapped_header] = Counter()
            category_counts[mapped_header].update(counts)

        self.progress(70)

        # Hedef Tabloda Kullanıcı İsimlerinin Olduğu Sütunu Bul
        target_user_col = 0
        for idx, h in enumerate(target_headers):
            h_norm = normalize_text(h)
            if any(k in h_norm for k in ["apelido", "nome", "kullanici", "user", "name", "qa", "ad"]):
                target_user_col = idx
                break

        target_users = []
        for row_idx, row in enumerate(target_rows[1:], start=2):
            if row and target_user_col < len(row):
                u_name = str(row[target_user_col]).strip()
                if u_name:
                    target_users.append((row_idx, u_name))

        cell_updates = []
        for target_col_header, u_counts in category_counts.items():
            if target_col_header not in target_headers:
                continue
            
            col_idx = target_headers.index(target_col_header)
            
            for row_idx, t_name in target_users:
                t_norm = normalize_text(t_name)
                score = 0
                for src_name, count in u_counts.items():
                    s_norm = normalize_text(src_name)
                    if t_norm in s_norm or s_norm in t_norm:
                        score += count

                if score > 0:
                    a1_cell = gspread.utils.rowcol_to_a1(row_idx, col_idx + 1)
                    cell_updates.append({
                        'range': f"{a1_cell}:{a1_cell}",
                        'values': [[int(score)]]
                    })

        self.progress(90)

        if cell_updates:
            self.log(f"✍️ Veriler Google Sheets tablosuna yazılıyor... ({len(cell_updates)} hücre)")
            safe_batch_update(target_sheet, cell_updates, self.log)
            self.progress(100)
            self.log("✅ İŞLEM BAŞARILI! Veriler eksiksiz olarak işlendi.")
        else:
            self.progress(100)
            self.log("⚠️ Eşleşen kullanıcı/sütun verisi bulunamadığından aktarım yapılamadı.")

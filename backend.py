import datetime
import re
import time
import json
import unicodedata
from collections import Counter
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials
import openai

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# API Key'ini buraya koyabilir veya arayüzden aktarabilirsin
OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"

# ==========================================
# 🧹 METİN NORMALLERİ VE TARİH
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

def safe_batch_update(sheet, updates, log_func, batch_size=20):
    total_len = len(updates)
    for i in range(0, total_len, batch_size):
        chunk = updates[i:i + batch_size]
        max_retries = 3
        for attempt in range(max_retries):
            try:
                sheet.batch_update(chunk)
                time.sleep(0.4)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    log_func(f"⚠️ API bekleniyor (Deneme {attempt+1}/{max_retries})...")
                    time.sleep(2)
                else:
                    log_func(f"❌ Güncelleme Hatası: {str(e)}")
                    raise e

# ==========================================
# 🧠 AI (ARTIFICIAL INTELLIGENCE) MAPPING
# ==========================================

def ai_column_mapper(source_sheets_list, target_headers, log_func, api_key=OPENAI_API_KEY):
    """
    Yapay zeka (GPT-4o) kaynak sekme isimlerini ve ana tablonun başlıklarını okur,
    bir insan QA Yöneticisi gibi hangi sekmenin hangi ana sütuna yazılacağını eşler.
    """
    client = openai.OpenAI(api_key=api_key)
    
    prompt = f"""
    Sen uzman bir QA Veri Analistisin. 
    Aşağıda kaynak tablodaki sekme adları (çeşitli dillerde olabilir) ve hedef rapordaki sütun başlıkları verilmiştir.

    Kaynak Sekme İsimleri: {source_sheets_list}
    Hedef Tablo Sütun Başlıkları: {target_headers}

    GÖREVİN:
    1. Kaynak sekmeleri incele. Eğer sekme adı bir TEST sekmesi ise (örnek: '0 Kul. TESTİ', 'Test', '0 Kullanıcı' vb.) bunu pas geç (null yap).
    2. Geri kalan sekmeleri mantıksal olarak hedef sütun başlıklarıyla eşleştir:
       - 'Mission Card', 'Zula Pass', 'Cartão de Missão', 'Tarjeta de Misión' vb. -> Zula Pass/Görev Kartı ile ilgili sütuna.
       - 'General Check', 'Genel', 'Verificação Geral', 'Revisión General' vb. -> Genel ile ilgili sütuna.
       - 'Error Reporting', 'Hata', 'Relatório de Erros' vb. -> Hata Raporlama ile ilgili sütuna.
    
    SADECE SIKI BIR JSON FORMATI DÖNDÜR.
    Format Örneği:
    {{
      "Mission Card": "Zula Pass",
      "0 Kul. TESTİ": null,
      "General Check": "Genel"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        mapping_result = json.loads(response.choices[0].message.content)
        log_func(f"🤖 AI Analiz Sonucu Eşleşmeleri: {mapping_result}")
        return mapping_result
    except Exception as e:
        log_func(f"⚠️ AI Analizinde hata oluştu, standart mantık kullanılacak: {str(e)}")
        return {}

# ==========================================
# 🚀 QA REPORT WORKER (AI DESTEKLİ)
# ==========================================

class QAReportWorker:
    def __init__(self, creds_input, source_id, report_id, selected_lang, selected_year, selected_month, log_callback, progress_callback, api_key=OPENAI_API_KEY):
        self.creds_input = creds_input
        self.source_id = source_id
        self.report_id = report_id
        self.selected_lang = selected_lang.upper().strip()
        self.selected_year = int(selected_year)
        self.selected_month_str = selected_month
        self.log = log_callback
        self.progress = progress_callback
        self.api_key = api_key

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

    def process(self):
        self.log(f"🧠 AI Destekli Kontrol Başlatıldı | Dil: [{self.selected_lang}] | Dönem: [{self.selected_month_str} {self.selected_year}]")
        self.progress(10)
        client = self.connect()

        source_wb = client.open_by_key(self.source_id)
        report_wb = client.open_by_key(self.report_id)
        
        target_sheet = self.get_target_worksheet(report_wb)
        self.log(f"Hedef Tablo Sekmesi: [{target_sheet.title}]")
        self.progress(20)

        target_rows = target_sheet.get_all_values()
        if not target_rows:
            self.log("⚠️ Ana tabloda veri bulunamadı!")
            self.progress(100)
            return

        target_headers = [str(h).strip() for h in target_rows[0]]
        source_worksheets = source_wb.worksheets()
        source_titles = [ws.title.strip() for ws in source_worksheets]

        # 🤖 AI İNSAN GİBİ TABLOLARI VE SÜTUNLARI İNCELEYİP EŞLEŞTİRİYOR
        self.log("🔍 Yapay Zeka sekmeleri ve hedef sütunları analiz ediyor...")
        ai_map = ai_column_mapper(source_titles, target_headers, self.log, self.api_key)
        self.progress(40)

        category_counts = {}

        for ws in source_worksheets:
            ws_title = ws.title.strip()
            mapped_target_header = ai_map.get(ws_title)

            if not mapped_target_header:
                self.log(f"🚫 AI Tarafından Pas Geçildi (Test/İlişkisiz): [{ws_title}]")
                continue

            self.log(f"📊 AI Okuyor: Sekme [{ws_title}] ➔ Hedef Sütun: '{mapped_target_header}'")
            
            # Sekmedeki verileri topla
            raw_rows = ws.get_all_values()
            if len(raw_rows) <= 1:
                continue

            headers = [normalize_text(h) for h in raw_rows[0]]
            user_col_idx = 0
            for idx, h in enumerate(headers):
                if any(u in h for u in ["user", "kullanici", "name", "nome", "nombre", "ad"]):
                    user_col_idx = idx
                    break

            counts = Counter()
            for row in raw_rows[1:]:
                if row and len(row) > user_col_idx:
                    u_name = str(row[user_col_idx]).strip()
                    if u_name and not any(tot in u_name.lower() for tot in ["toplam", "total"]):
                        counts[u_name] += 1

            if mapped_target_header not in category_counts:
                category_counts[mapped_target_header] = Counter()
            category_counts[mapped_target_header].update(counts)

        self.progress(70)

        # Hedef tablodaki kullanıcı sütununu bul
        user_col_in_target = 0
        for idx, h in enumerate(target_headers):
            h_norm = normalize_text(h)
            if any(k in h_norm for k in ["kullanici", "user", "name", "qa", "ad", "nombre"]):
                user_col_in_target = idx
                break

        target_users = []
        for row_idx, row in enumerate(target_rows[1:], start=2):
            if row and user_col_in_target < len(row):
                u_name = str(row[user_col_in_target]).strip()
                if u_name:
                    target_users.append((row_idx, u_name))

        # Hücre güncellemelerini hazırla
        cell_updates = []
        
        for target_col_header, u_counts in category_counts.items():
            if target_col_header not in target_headers:
                continue
            
            target_c_idx = target_headers.index(target_col_header)
            
            for row_idx, t_name in target_users:
                # Kullanıcı eşleştirme
                score = 0
                for src_name, count in u_counts.items():
                    if normalize_text(t_name) in normalize_text(src_name) or normalize_text(src_name) in normalize_text(t_name):
                        score += count

                if score > 0:
                    a1_cell = gspread.utils.rowcol_to_a1(row_idx, target_c_idx + 1)
                    cell_updates.append({
                        'range': f"{a1_cell}:{a1_cell}",
                        'values': [[int(score)]]
                    })

        self.progress(90)

        if cell_updates:
            self.log(f"✍️ AI Verileri [{target_sheet.title}] sekmesine işliyor... ({len(cell_updates)} hücre)")
            safe_batch_update(target_sheet, cell_updates, self.log)
            self.progress(100)
            self.log("✅ İŞLEM BAŞARILI! AI tabloyu insan gibi kontrol edip verileri eksiksiz işledi.")
        else:
            self.progress(100)
            self.log("⚠️ Aktarılacak uygun veri bulunamadı.")

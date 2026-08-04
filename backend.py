import os
import datetime
import re
import time
import json
import unicodedata
from collections import Counter
import gspread
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

# Türkçe Ay İsimleri Haritası
MONTH_MAP = {
    "ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6,
    "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12
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
    """Satırdaki Zaman Damgasından Ay ve Yıl Çıkarır"""
    if not date_str:
        return None, None
    try:
        # DD.MM.YYYY HH:MM:SS veya YYYY-MM-DD vb. kalıpları eşleştir
        match = re.search(r'(\d{1,4})[\./-](\d{1,2})[\./-](\d{1,4})', str(date_str))
        if match:
            g1, g2, g3 = match.groups()
            if len(g1) == 4: # YYYY-MM-DD
                return int(g2), int(g1)
            elif len(g3) == 4: # DD.MM.YYYY
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

# ==========================================
# 🧠 HARİTALAMA MOTORU
# ==========================================

def get_sheet_column_mapping(source_titles, target_headers, log_func, api_key=None):
    final_key = api_key or os.getenv("OPENAI_API_KEY")
    
    if HAS_OPENAI and final_key:
        try:
            client = openai.OpenAI(api_key=final_key)
            prompt = f"""
            Kaynak Sekme Adları: {source_titles}
            Hedef Tablo Başlıkları: {target_headers}

            GÖREV:
            - '0 Kullanıcı', 'Teste', 'OLD', 'Kopyası' geçen test sekmelerini eler (null yap).
            - Sekme isimlerini hedef tablodaki BİREBİR sütun metniyle eşleştir:
               'Cartão De Missão (günlük)' -> 'G. Kartı (Günlük)'
               'Verificação Geral (genel)' -> 'Genel Check'
               'Relatório de erros' -> 'Hata bildirimi'

            SADECE JSON DÖNDÜR: {{ "Sekme Adı": "Hedef Sütun Başlığı Metni" }}
            """
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            log_func(f"⚠️ AI Analiz Hatası ({str(e)}), kural bazlı haritalama çalıştırılıyor.")

    mapping = {}
    for st in source_titles:
        st_norm = normalize_text(st)
        
        if any(k in st_norm for k in ["0 kul", "teste de novo", "old", "kopyasi", "copy"]):
            mapping[st] = None
            continue
        
        matched_header = None
        for th in target_headers:
            th_norm = normalize_text(th)
            
            if any(k in st_norm for k in ["cartao", "missao", "card", "gunluk"]) and any(k in th_norm for k in ["g karti", "karti", "gunluk"]):
                matched_header = th
                break
            elif any(k in st_norm for k in ["verificacao", "geral", "genel", "check"]) and any(k in th_norm for k in ["genel", "check", "geral"]):
                matched_header = th
                break
            elif any(k in st_norm for k in ["relatorio", "erro", "hata", "bug"]) and any(k in th_norm for k in ["hata", "bildirimi"]):
                matched_header = th
                break

        mapping[st] = matched_header

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
        self.selected_month_str = selected_month.strip()
        self.target_month_num = MONTH_MAP.get(normalize_text(selected_month), 7)
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
        
        # 🎯 1. KESİN YIL VE AY MATCH (Örn: "POR TEMMUZ 2026")
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
            self.log(f"❌ HATA: [{self.selected_lang} {self.selected_month_str} {self.selected_year}] adında hedef sekme bulunamadı!")
            self.progress(100)
            return

        self.log(f"🎯 Hedef Sekme Bulundu: [{target_sheet.title}]")
        self.progress(20)

        target_rows = target_sheet.get_all_values()
        if not target_rows:
            self.log("⚠️ Ana tabloda veri bulunamadı!")
            self.progress(100)
            return

        target_headers = [str(h).strip() for h in target_rows[0]]
        source_worksheets = source_wb.worksheets()
        source_titles = [ws.title.strip() for ws in source_worksheets]

        ai_map = get_sheet_column_mapping(source_titles, target_headers, self.log, self.openai_api_key)
        self.progress(40)

        category_counts = {}

        for ws in source_worksheets:
            ws_title = ws.title.strip()
            mapped_header = ai_map.get(ws_title)

            if not mapped_header:
                self.log(f"🚫 Es geçildi (Test/Eşleşmeyen): [{ws_title}]")
                continue

            self.log(f"📊 Sekme Okunuyor: [{ws_title}] ➔ Hedef Sütun: '{mapped_header}'")
            raw_rows = ws.get_all_values()
            if len(raw_rows) <= 1:
                continue

            counts = Counter()
            filtered_rows_count = 0

            for row in raw_rows[1:]:
                if not row:
                    continue

                # 🗓️ TARİH FİLTRESİ CHECK (Zaman damgası 0. Sütundadır)
                row_date_str = str(row[0]).strip() if len(row) > 0 else ""
                row_month, row_year = parse_row_date(row_date_str)

                # Yalnızca seçilen ay ve yıl verisi işlenir
                if row_month and row_year:
                    if row_month != self.target_month_num or row_year != self.selected_year:
                        continue # Seçilen döneme uymayan veriyi atla
                
                filtered_rows_count += 1
                name_b = str(row[1]).strip() if len(row) > 1 else ""
                nick_c = str(row[2]).strip() if len(row) > 2 else ""

                user_key = nick_c if nick_c else name_b
                if user_key and not any(tot in user_key.lower() for tot in ["toplam", "total", "zaman"]):
                    counts[user_key] += 1
                    if name_b and name_b != user_key:
                        counts[name_b] += 1

            self.log(f"   └─ 📅 {self.selected_month_str} {self.selected_year} tarihli işlenebilir satır sayısı: {filtered_rows_count}")

            if mapped_header not in category_counts:
                category_counts[mapped_header] = Counter()
            category_counts[mapped_header].update(counts)

        self.progress(70)

        # HEDEF KULLANICI LİSTESİ VE HÜCRE GÜNCELLEMELERİ
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
            self.log(f"✍️ Veriler Google Sheets [{target_sheet.title}] sekmesine yazılıyor... ({len(cell_updates)} hücre)")
            safe_batch_update(target_sheet, cell_updates, self.log)
            self.progress(100)
            self.log("✅ İŞLEM BAŞARILI! Yalnızca Temmuz 2026 verileri tabloya aktarıldı.")
        else:
            self.progress(100)
            self.log("⚠️ Seçilen döneme (Temmuz 2026) uygun eşleşen veri bulunamadı.")

import datetime
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Ay isimlerinin sayısal karşılıkları
MONTH_MAP = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12
}

def get_available_spreadsheets(json_path):
    creds = Credentials.from_service_account_file(json_path, scopes=SCOPES)
    client = gspread.authorize(creds)
    files = client.list_spreadsheet_files()
    return {f['name']: f['id'] for f in files}

class QAReportWorker:
    def __init__(self, json_path, source_id, report_id, selected_lang, selected_year, selected_month, log_callback, progress_callback):
        self.json_path = json_path
        self.source_id = source_id
        self.report_id = report_id
        self.selected_lang = selected_lang
        self.selected_year = int(selected_year)
        self.selected_month_num = MONTH_MAP.get(selected_month.lower(), 1)
        self.selected_month_str = selected_month
        self.log = log_callback
        self.progress = progress_callback

    def connect(self):
        creds = Credentials.from_service_account_file(self.json_path, scopes=SCOPES)
        return gspread.authorize(creds)

    def get_target_sheet_name(self, lang, spreadsheet):
        expected_title = f"{lang} {self.selected_month_str} {self.selected_year}"
        worksheets = [ws.title for ws in spreadsheet.worksheets()]
        
        if expected_title in worksheets:
            return expected_title

        for ws_title in worksheets:
            if lang in ws_title and self.selected_month_str in ws_title and str(self.selected_year) in ws_title:
                return ws_title
            
        for ws_title in worksheets:
            if "error reporting" in ws_title.lower() and lang.lower() in ws_title.lower():
                return ws_title
            
        raise ValueError(f"'{lang}' için belirtilen döneme ait rapor sayfası bulunamadı! Aranan: '{expected_title}'")

    def is_in_selected_period(self, timestamp_val):
        """Zaman damgasının seçilen Ay ve Yıl içerisinde olup olmadığını kontrol eder."""
        if not timestamp_val:
            return True

        ts_str = str(timestamp_val).strip()

        for fmt in [
            "%d.%m.%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
            "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"
        ]:
            try:
                dt = datetime.datetime.strptime(ts_str.split('.')[0] if '.' in ts_str and len(ts_str.split('.')[-1]) > 4 else ts_str, fmt)
                return dt.year == self.selected_year and dt.month == self.selected_month_num
            except ValueError:
                continue

        if str(self.selected_year) in ts_str:
            month_zero_padded = f"{self.selected_month_num:02d}"
            if f"/{month_zero_padded}/" in ts_str or f".{month_zero_padded}." in ts_str or f"-{month_zero_padded}-" in ts_str:
                return True

        return False

    def count_tasks_by_user(self, worksheet):
        """Kaynak sayfadan SADECE SEÇİLEN AY VE YILDAKİ görev sayılarını toplar."""
        records = worksheet.get_all_records()
        user_counts = {}

        for row in records:
            timestamp = None
            for key, val in row.items():
                if "zaman" in str(key).lower() or "timestamp" in str(key).lower() or "tarih" in str(key).lower():
                    timestamp = val
                    break

            if timestamp and not self.is_in_selected_period(timestamp):
                continue

            user = None
            for key, val in row.items():
                clean_key = str(key).strip().lower()
                if any(attr in clean_key for attr in ["in-game character name", "nick", "name-surname", "ad soyad", "oyuncu", "player", "qa"]):
                    user = val
                    if user:
                        break

            if user:
                user_str = str(user).strip().lower()
                if user_str:
                    user_counts[user_str] = user_counts.get(user_str, 0) + 1

        return user_counts

    def process(self):
        self.log("Google Sheets API'ye bağlanılıyor...")
        client = self.connect()
        self.progress(10)

        self.log("Spreadsheet'ler açılıyor...")
        src_spreadsheet = client.open_by_key(self.source_id)
        rep_spreadsheet = client.open_by_key(self.report_id)
        self.progress(20)

        self.log(f"Kaynak veriler filtrelenerek okunuyor ({self.selected_month_str} {self.selected_year})...")
        
        mission_counts = {}
        general_counts = {}

        for ws in src_spreadsheet.worksheets():
            title = ws.title.strip().lower()
            
            # Mission Card (Pass) tablosu tespiti
            if "mission card" in title or "pass" in title:
                mission_counts = self.count_tasks_by_user(ws)
                self.log(f"-> Mission Card(Pass): {self.selected_month_str} {self.selected_year} dönemi {len(mission_counts)} aktif oyuncu okundu.")
            
            # General Check (Genel) tablosu tespiti
            elif "general check" in title or "genel" in title:
                general_counts = self.count_tasks_by_user(ws)
                self.log(f"-> General Check (Genel): {self.selected_month_str} {self.selected_year} dönemi {len(general_counts)} aktif oyuncu okundu.")

        # Note: New User Test pas geçilmiştir (Manuel kontrol edilmektedir).
        self.log("ℹ️ New User Test kategorisi atlandı (Manuel kontrol edilecek).")

        self.progress(40)

        languages = ["ENG", "ESP", "POR", "TR"] if self.selected_lang == "Tümü" else [self.selected_lang]
        total_langs = len(languages)

        for idx, lang in enumerate(languages):
            self.log(f"[{lang}] Rapor sayfası aranıyor ({self.selected_month_str} {self.selected_year})...")
            
            try:
                target_sheet_name = self.get_target_sheet_name(lang, rep_spreadsheet)
            except ValueError as e:
                self.log(f"⚠️ [{lang}] Sayfa bulunamadı: {e}")
                continue

            target_ws = rep_spreadsheet.worksheet(target_sheet_name)
            self.log(f"[{lang}] Bulunan sayfa: '{target_sheet_name}'")

            all_rows = target_ws.get_all_values()
            updates = []
            matched_players = 0
            
            for row_idx, row in enumerate(all_rows, start=1):
                if not row:
                    continue
                
                col_a = row[0].strip().lower() if len(row) > 0 else ""
                col_b = row[1].strip().lower() if len(row) > 1 else ""
                
                player_name = None
                if col_a in mission_counts or col_a in general_counts:
                    player_name = col_a
                elif col_b in mission_counts or col_b in general_counts:
                    player_name = col_b

                if not player_name:
                    continue

                matched = False

                # D Sütunu: Mission Card(Pass) - Sadece sayısı > 0 ise güncelle
                if player_name in mission_counts and mission_counts[player_name] > 0:
                    updates.append({'range': f'D{row_idx}', 'values': [[mission_counts[player_name]]]})
                    matched = True

                # E Sütunu (New User Test): Manuel kontrol edildiği için pas geçildi.

                # F Sütunu: General Check (Genel) - Sadece sayısı > 0 ise güncelle
                if player_name in general_counts and general_counts[player_name] > 0:
                    updates.append({'range': f'F{row_idx}', 'values': [[general_counts[player_name]]]})
                    matched = True

                if matched:
                    matched_players += 1

            if updates:
                self.log(f"[{lang}] {matched_players} aktif oyuncu doğrulandı, {len(updates)} hücre güncelleniyor...")
                target_ws.batch_update(updates)
                self.log(f"[{lang}] Başarıyla güncellendi!")
            else:
                self.log(f"ℹ️ [{lang}] Güncellenecek yeni veri bulunamadı.")

            current_progress = 40 + int(((idx + 1) / total_langs) * 55)
            self.progress(current_progress)

        self.progress(100)
        self.log("İşlem tamamlandı.")
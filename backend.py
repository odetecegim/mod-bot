import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 🔍 GOOGLE DRIVE / SHEETS LISTELEME
# ==========================================
def get_available_spreadsheets(creds_input):
    """
    Google Drive üzerindeki erişilebilir tüm Google Sheets dosyalarını listeler.
    """
    spreadsheets = {"all": {}}
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        if isinstance(creds_input, dict):
            creds = Credentials.from_service_account_info(creds_input, scopes=scopes)
        else:
            creds = Credentials.from_service_account_file(creds_input, scopes=scopes)

        client = gspread.authorize(creds)
        files = client.openall()

        for f in files:
            spreadsheets["all"][f.title] = f.id

    except Exception as e:
        print(f"Spreadsheet listeleme hatası: {e}")

    return spreadsheets

# ==========================================
# 📊 QA REPORT WORKER (RAPOR İŞLEME MOTORU)
# ==========================================
class QAReportWorker:
    def __init__(self, creds_input, source_id, report_id, selected_year, selected_month, log_callback=print, progress_callback=None):
        self.creds_input = creds_input
        self.source_id = source_id
        self.report_id = report_id
        self.selected_year = selected_year
        self.selected_month = selected_month
        self.log_callback = log_callback
        self.progress_callback = progress_callback or (lambda v: None)

    def _get_client(self):
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        if isinstance(self.creds_input, dict):
            creds = Credentials.from_service_account_info(self.creds_input, scopes=scopes)
        else:
            creds = Credentials.from_service_account_file(self.creds_input, scopes=scopes)
        return gspread.authorize(creds)

    def process(self):
        try:
            self.log_callback("⚙️ Google Sheets bağlantısı kuruluyor...")
            self.progress_callback(10)
            client = self._get_client()

            # Kaynak dosyayı aç
            self.log_callback("📂 Kaynak dosya açılıyor...")
            src_wb = client.open_by_key(self.source_id)
            src_ws = src_wb.sheet1
            self.progress_callback(30)

            # Veriyi oku
            data = src_ws.get_all_records()
            if not data:
                self.log_callback("⚠️ Kaynak dosyada veri bulunamadı!")
                return None

            df = pd.DataFrame(data)
            df.columns = [str(c).strip() for c in df.columns]
            self.log_callback(f"📊 Toplam {len(df)} satır veri okundu.")
            self.progress_callback(50)

            # Sayısal sütunları düzelt ve temizle
            score_cols = [
                "Zula Pass", "0 Kul. TESTİ", "Genel Check", "Hata bildirimi", 
                "Öneri Bildirimi", "Discord PC", "Hakemlik", "Diğer/Kanaat"
            ]

            valid_score_cols = [c for c in df.columns if any(sc.lower() in str(c).lower() for sc in score_cols)]

            for col in valid_score_cols:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(',', '.').str.strip(), 
                    errors='coerce'
                ).fillna(0)

            if valid_score_cols:
                df["Toplam"] = df[valid_score_cols].sum(axis=1).astype(int)
                df["ZA"] = df["Toplam"] * 500

            self.progress_callback(75)

            # Hedef rapora kaydet
            self.log_callback("💾 Hedef rapora veriler yazılıyor...")
            rep_wb = client.open_by_key(self.report_id)
            rep_ws = rep_wb.sheet1

            df_to_write = df.fillna("")
            data_to_write = [df_to_write.columns.tolist()] + df_to_write.astype(str).values.tolist()

            rep_ws.clear()
            rep_ws.update('A1', data_to_write)

            self.progress_callback(100)
            self.log_callback("✅ Rapor işleme ve aktarım başarıyla tamamlandı!")
            return df

        except Exception as e:
            self.log_callback(f"❌ Rapor işleme hatası: {e}")
            return None

# ==========================================
# ⚡ AY TABLOSUNA VERİ İŞLEME & DİNAMİK SEKME BULUCU
# ==========================================
def process_za_and_insert_month(main_ws, target_month_name, selected_year=2026, log_func=print):
    """
    Hedef Google Sheets belgesinde 'ENG Temmuz 2026', 'POR TEMMUZ 2026' gibi dinamik isimli sekmeleri bulur 
    ve ZA verilerini tam olarak o sekmedeki ilgili ay/personel sütunlarına işler.
    """
    try:
        wb = main_ws.spreadsheet
        all_worksheets = wb.worksheets()
        sheet_titles = [ws.title for ws in all_worksheets]
        
        target_ws = None
        
        # 1. Sekme adını dinamik ara (Örn: "Temmuz" ve "2026" kelimelerini içeren sekme)
        target_month_clean = str(target_month_name).strip().lower()
        target_year_clean = str(selected_year).strip()

        for ws in all_worksheets:
            title_clean = ws.title.lower()
            if target_month_clean in title_clean and target_year_clean in title_clean:
                target_ws = ws
                break

        # Tam yıl içeren bulunamazsa sadece Ay ismine göre ara (örn: "ENG TEMMUZ")
        if not target_ws:
            for ws in all_worksheets:
                if target_month_clean in ws.title.lower():
                    target_ws = ws
                    break

        if not target_ws:
            log_func(f"❌ '{target_month_name} {selected_year}' içeren uygun sekme bulunamadı! Mevcut sekmeler: {', '.join(sheet_titles[:5])}...")
            return False

        log_func(f"🎯 Hedef sekme tespit edildi: [{target_ws.title}]")

        # 2. Ana tablodaki verileri al
        data = main_ws.get_all_records()
        if not data:
            log_func("⚠️ Ana çalışma sayfasında işlenecek veri bulunamadı!")
            return False

        df_main = pd.DataFrame(data)
        df_main.columns = [str(c).strip() for c in df_main.columns]

        user_col = None
        for col in ["Nick", "Personel", "Kullanıcı", "Ad Soyad"]:
            if col in df_main.columns:
                user_col = col
                break
                
        if not user_col:
            log_func("❌ Ana tabloda 'Nick' veya 'Personel' sütunu bulunamadı!")
            return False

        za_col = "ZA" if "ZA" in df_main.columns else df_main.columns[-1]

        # 3. Bulunan Hedef Sekmeye (örn: ENG Temmuz 2026) veriyi işle
        target_rows = target_ws.get_all_values()
        
        if not target_rows:
            headers = [user_col, f"{target_month_name} ZA"]
            rows_to_write = [headers]
            for _, row in df_main.iterrows():
                rows_to_write.append([str(row[user_col]), str(row[za_col])])
            
            target_ws.clear()
            target_ws.update('A1', rows_to_write)
        else:
            headers = [str(h).strip() for h in target_rows[0]]
            
            col_idx = -1
            for i, h in enumerate(headers):
                if target_month_clean in h.lower() or "za" in h.lower() or "toplam" in h.lower():
                    col_idx = i + 1
                    break
            
            if col_idx == -1:
                headers.append(f"{target_month_name} ZA")
                col_idx = len(headers)
                target_ws.update_cell(1, col_idx, f"{target_month_name} ZA")

            main_dict = dict(zip(df_main[user_col].astype(str).str.strip(), df_main[za_col].astype(str).str.strip()))
            
            updated_rows = [headers]
            for row in target_rows[1:]:
                if not row: continue
                u_name = str(row[0]).strip()
                
                while len(row) < len(headers):
                    row.append("")
                    
                if u_name in main_dict:
                    row[col_idx - 1] = main_dict[u_name]
                
                updated_rows.append(row)

            target_ws.clear()
            target_ws.update('A1', updated_rows)

        log_func(f"✅ Veriler başarıyla [{target_ws.title}] sekmesine aktarıldı!")
        return True

    except Exception as e:
        log_func(f"❌ Akış Hatası: {e}")
        return False

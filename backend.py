import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

def get_available_spreadsheets(creds_input):
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

            self.log_callback("📂 Kaynak dosya açılıyor...")
            src_wb = client.open_by_key(self.source_id)
            
            # İlk dolu sekmeyi bul
            src_ws = None
            for ws in src_wb.worksheets():
                vals = ws.get_all_values()
                if vals and len(vals) > 1:
                    src_ws = ws
                    break
            
            if not src_ws:
                src_ws = src_wb.sheet1

            self.progress_callback(30)

            # Esnek Veri Okuma
            raw_data = src_ws.get_all_values()
            if not raw_data or len(raw_data) < 2:
                self.log_callback("⚠️ Kaynak dosyada yeterli veri bulunamadı!")
                return None

            headers = [str(h).strip() for h in raw_data[0]]
            df = pd.DataFrame(raw_data[1:], columns=headers)
            
            self.log_callback(f"📊 Toplam {len(df)} satır veri okundu.")
            self.progress_callback(50)

            # Formül hesaplamaları
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

            # Hedef dosyaya yaz
            self.log_callback("💾 Hedef rapora veriler yazılıyor...")
            rep_wb = client.open_by_key(self.report_id)
            rep_ws = rep_wb.sheet1

            df_to_write = df.fillna("")
            data_to_write = [df_to_write.columns.tolist()] + df_to_write.astype(str).values.tolist()

            rep_ws.clear()
            rep_ws.update(data_to_write, 'A1')

            self.progress_callback(100)
            self.log_callback("✅ Rapor işleme ve aktarım başarıyla tamamlandı!")
            return df

        except Exception as e:
            self.log_callback(f"❌ Rapor işleme hatası: {e}")
            return None


def process_za_and_insert_month(main_ws, target_month_name, selected_year=2026, log_func=print):
    try:
        wb = main_ws.spreadsheet
        all_worksheets = wb.worksheets()
        sheet_titles = [ws.title for ws in all_worksheets]
        
        target_ws = None
        target_month_clean = str(target_month_name).strip().lower()
        target_year_clean = str(selected_year).strip()

        # 1. Sekmeyi bul (Örn: "ENG Temmuz 2026")
        for ws in all_worksheets:
            title_clean = ws.title.lower()
            if target_month_clean in title_clean and target_year_clean in title_clean:
                target_ws = ws
                break

        if not target_ws:
            for ws in all_worksheets:
                if target_month_clean in ws.title.lower():
                    target_ws = ws
                    break

        if not target_ws:
            log_func(f"❌ '{target_month_name} {selected_year}' sekmesi bulunamadı! Mevcut sekmeler: {', '.join(sheet_titles[:4])}...")
            return False

        log_func(f"🎯 Hedef sekme bulundu: [{target_ws.title}]")

        # 2. Ana tablodan veri al
        raw_main = main_ws.get_all_values()
        if not raw_main or len(raw_main) < 2:
            log_func("⚠️ Ana çalışma sayfasında işlenecek veri bulunamadı!")
            return False

        df_main = pd.DataFrame(raw_main[1:], columns=[str(h).strip() for h in raw_main[0]])

        user_col = None
        for col in ["Nick", "Personel", "Kullanıcı", "Ad Soyad"]:
            if col in df_main.columns:
                user_col = col
                break
                
        if not user_col:
            user_col = df_main.columns[0]

        za_col = "ZA" if "ZA" in df_main.columns else df_main.columns[-1]

        # 3. Sekmeye Veri Yaz
        target_rows = target_ws.get_all_values()
        
        if not target_rows:
            headers = [user_col, f"{target_month_name} ZA"]
            rows_to_write = [headers]
            for _, row in df_main.iterrows():
                rows_to_write.append([str(row[user_col]), str(row[za_col])])
            
            target_ws.clear()
            target_ws.update(rows_to_write, 'A1')
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
            target_ws.update(updated_rows, 'A1')

        log_func(f"✅ Veriler başarıyla [{target_ws.title}] sekmesine yazıldı!")
        return True

    except Exception as e:
        log_func(f"❌ İşlem Hatası: {e}")
        return False

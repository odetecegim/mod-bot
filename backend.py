import time
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


def _find_target_worksheet(wb, language, month_name, year, log_callback=print, create_if_missing=True, source_columns=None):
    """
    '<DİL> <Ay> <Yıl>' deseniyle eşleşen sekmeyi bulur.
    'Rapor' geçen sekmelere KESİNLİKLE dokunulmaz.
    """
    language_clean = str(language or "").strip().lower()
    month_clean = str(month_name or "").strip().lower()
    year_clean = str(year or "").strip()

    candidates = [
        ws for ws in wb.worksheets()
        if "rapor" not in ws.title.strip().lower()
    ]

    # 1. Tam eşleşme
    for ws in candidates:
        title_clean = ws.title.strip().lower()
        if language_clean in title_clean and month_clean in title_clean and year_clean in title_clean:
            return ws

    # 2. Gevşetilmiş eşleşme (Sadece Ay + Yıl)
    for ws in candidates:
        title_clean = ws.title.strip().lower()
        if month_clean in title_clean and year_clean in title_clean:
            log_callback(f"⚠️ '{language} {month_name} {year}' tam eşleşmedi, '[{ws.title}]' sekmesi kullanılıyor.")
            return ws

    if not create_if_missing:
        return None

    # 3. Yeni sekme oluştur
    new_title = f"{language} {month_name} {year}"
    log_callback(f"🆕 '{new_title}' sekmesi bulunamadı, yeni oluşturuluyor...")
    new_ws = wb.add_worksheet(title=new_title, rows="1000", cols=str(max(len(source_columns or []), 10)))
    if source_columns:
        new_ws.update(range_name='A1', values=[list(source_columns)])
    return new_ws


class QAReportWorker:
    def __init__(self, creds_input, source_id, report_id, selected_year, selected_month, selected_language="ENG", log_callback=print, progress_callback=None):
        self.creds_input = creds_input
        self.source_id = source_id
        self.report_id = report_id
        self.selected_year = selected_year
        self.selected_month = selected_month
        self.selected_language = selected_language
        self.log_callback = log_callback
        self.progress_callback = progress_callback or (lambda v: None)
        self.used_worksheet_title = None

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
            
            user_report_counts = {}
            visible_sheet_count = 0

            for ws in src_wb.worksheets():
                # gspread uyumluluğu (is_hidden / _properties kontrolü)
                is_hidden = getattr(ws, 'is_hidden', ws._properties.get('hidden', False))
                if is_hidden:
                    self.log_callback(f"🙈 Gizli sekme atlandı: [{ws.title}]")
                    continue
                
                visible_sheet_count += 1
                self.log_callback(f"✅ Açık sekme taranıyor: [{ws.title}]")
                
                try:
                    vals = ws.get_all_values()
                    if not vals or len(vals) < 2:
                        continue
                    
                    headers = [str(h).strip() for h in vals[0]]
                    df_sheet = pd.DataFrame(vals[1:], columns=headers)
                    
                    nick_col = None
                    for c in df_sheet.columns:
                        if str(c).lower() in ["nick", "personel", "kullanıcı", "ad soyad", "qa_member"]:
                            nick_col = c
                            break
                    if not nick_col and len(df_sheet.columns) > 0:
                        nick_col = df_sheet.columns[0]
                        
                    if nick_col:
                        counts = df_sheet[nick_col].astype(str).str.strip().value_counts()
                        for user_name, count in counts.items():
                            if user_name and user_name.lower() not in ['nan', '', 'none', 'nick']:
                                user_report_counts[user_name] = user_report_counts.get(user_name, 0) + count
                except Exception as ex_ws:
                    self.log_callback(f"⚠️ Sekme okunurken hata ({ws.title}): {ex_ws}")

            self.log_callback(f"📊 Toplam {visible_sheet_count} açık sekmeden {len(user_report_counts)} personelin rapor sayıları toplandı.")
            self.progress_callback(40)

            self.log_callback("💾 Hedef (Global Perf) dosyası açılıyor...")
            rep_wb = client.open_by_key(self.report_id)

            rep_ws = _find_target_worksheet(
                rep_wb,
                language=self.selected_language,
                month_name=self.selected_month,
                year=self.selected_year,
                log_callback=self.log_callback,
                create_if_missing=True
            )

            self.used_worksheet_title = rep_ws.title
            self.log_callback(f"📄 Hedef sekme: [{rep_ws.title}]")
            self.progress_callback(60)

            target_vals = rep_ws.get_all_values()
            
            if target_vals and len(target_vals) >= 1:
                headers = [str(h).strip() for h in target_vals[0]]
                df = pd.DataFrame(target_vals[1:], columns=headers)
            else:
                headers = ["Nick", "Zula Pass", "0 Kul. TESTİ", "Genel Check", "Hata bildirimi", "Öneri Bildirimi", "Discord PC", "Hakemlik", "Diğer/Kanaat", "Toplam", "ZA"]
                df = pd.DataFrame(columns=headers)

            user_col = None
            for c in df.columns:
                if str(c).lower() in ["nick", "personel", "kullanıcı", "ad soyad"]:
                    user_col = c
                    break
            if not user_col:
                user_col = df.columns[0] if len(df.columns) > 0 else "Nick"

            existing_users = set(df[user_col].astype(str).str.strip().tolist()) if not df.empty else set()
            for u_name in user_report_counts.keys():
                if u_name not in existing_users:
                    new_row = {col: "" for col in df.columns}
                    new_row[user_col] = u_name
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

            report_col = None
            for col in df.columns:
                if any(k in str(col).lower() for k in ["hata", "rapor", "check"]):
                    report_col = col
                    break
            if not report_col:
                report_col = "Hata bildirimi"
                if report_col not in df.columns:
                    df[report_col] = 0

            for idx, row in df.iterrows():
                u_name = str(row[user_col]).strip()
                if u_name in user_report_counts:
                    df.at[idx, report_col] = user_report_counts[u_name]

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

            self.progress_callback(85)

            df_to_write = df.fillna("")
            data_to_write = [df_to_write.columns.tolist()] + df_to_write.astype(str).values.tolist()

            rep_ws.clear()
            rep_ws.update(range_name='A1', values=data_to_write)

            self.progress_callback(100)
            self.log_callback(f"✅ [{rep_ws.title}] sekmesine açık sekmelerin rapor sayıları başarıyla işlendi!")
            return df

        except Exception as e:
            self.log_callback(f"❌ Rapor işleme hatası: {e}")
            return None


def process_za_and_insert_month(main_ws, target_month_name, selected_year=2026, selected_language="ENG", log_func=print):
    try:
        wb = main_ws.spreadsheet

        target_ws = _find_target_worksheet(
            wb,
            language=selected_language,
            month_name=target_month_name,
            year=selected_year,
            log_callback=log_func,
            create_if_missing=False
        )

        if not target_ws:
            other_titles = [ws.title for ws in wb.worksheets() if "rapor" not in ws.title.strip().lower()]
            log_func(f"❌ '{selected_language} {target_month_name} {selected_year}' sekmesi bulunamadı! Mevcut sekmeler: {', '.join(other_titles[:6])}...")
            return False

        log_func(f"🎯 Hedef sekme bulundu: [{target_ws.title}]")

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

        target_rows = target_ws.get_all_values()
        
        if not target_rows:
            headers = [user_col, f"{target_month_name} ZA"]
            rows_to_write = [headers]
            for _, row in df_main.iterrows():
                rows_to_write.append([str(row[user_col]), str(row[za_col])])
            
            target_ws.clear()
            target_ws.update(range_name='A1', values=rows_to_write)
        else:
            headers = [str(h).strip() for h in target_rows[0]]
            target_month_clean = str(target_month_name).strip().lower()

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
                if not row: 
                    continue
                u_name = str(row[0]).strip()
                
                while len(row) < len(headers):
                    row.append("")
                    
                if u_name in main_dict:
                    row[col_idx - 1] = main_dict[u_name]
                
                updated_rows.append(row)

            target_ws.clear()
            target_ws.update(range_name='A1', values=updated_rows)

        log_func(f"✅ Veriler başarıyla [{target_ws.title}] sekmesine yazıldı!")
        return True

    except Exception as e:
        log_func(f"❌ İşlem Hatası: {e}")
        return False

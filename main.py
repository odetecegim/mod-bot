import gspread
import pandas as pd

def process_qa_reports_from_visible_sheets(creds_input, source_id, report_id, selected_language, selected_month, selected_year, log_callback=print):
    """
    Kaynak belgedeki GİZLİ OLMAYAN (AÇIK) sekmelerden verileri toplar, 
    her kullanıcının yaptığı rapor/işlem sayısını hesaplar ve hedef ana sheet'e işler.
    """
    # 1. Google Sheets Bağlantısı
    if isinstance(creds_input, dict):
        client = gspread.service_account_from_dict(creds_input)
    else:
        client = gspread.service_account(filename=creds_input)

    source_wb = client.open_by_key(source_id)
    target_wb = client.open_by_key(report_id)

    log_callback(f"📂 Kaynak Belge Açıldı: {source_wb.title}")

    # 2. Kaynak Belgedeki SADECE AÇIK (GİZLİ OLMAYAN) Sekmeleri Filtreleme
    visible_worksheets = []
    for ws in source_wb.worksheets():
        # gspread metadata üzerinden gizli sekme kontrolü
        sheet_properties = ws._properties
        is_hidden = sheet_properties.get('hidden', False)
        
        if not is_hidden:
            visible_worksheets.append(ws)
            log_callback(f"✅ Açık Sekme Bulundu: {ws.title}")
        else:
            log_callback(f"🙈 Gizli Sekme Atlantı: {ws.title}")

    # 3. Açık Sekmelerden Kullanıcı Rapor Sayılarını Toplama
    user_report_counts = {}

    for ws in visible_worksheets:
        try:
            records = ws.get_all_records()
            if not records:
                continue
            
            df_ws = pd.DataFrame(records)
            
            # Kullanıcı adı/Nick kolonunu dinamik tespit etme
            user_col = None
            for col in df_ws.columns:
                if str(col).strip().lower() in ['nick', 'kullanıcı', 'personel', 'isim', 'qa_member']:
                    user_col = col
                    break
            
            if user_col:
                # Kullanıcı bazlı rapor sayılarını hesaplama (Frekans)
                counts = df_ws[user_col].astype(str).str.strip().value_counts()
                for user_name, count in counts.items():
                    if user_name and user_name.lower() != 'nan':
                        user_report_counts[user_name] = user_report_counts.get(user_name, 0) + count
        except Exception as e:
            log_callback(f"⚠️ Sekme okunurken hata ({ws.title}): {e}")

    log_callback(f"📊 Toplam {len(user_report_counts)} farklı personelin açık sekmelerdeki rapor sayıları hesaplandı.")

    # 4. Hedef Sekmeyi Belirleme (Örn: "ENG Temmuz 2026")
    target_ws_title = f"{selected_language} {selected_month} {selected_year}"
    target_ws = None
    
    for ws in target_wb.worksheets():
        if ws.title.strip().lower() == target_ws_title.lower():
            target_ws = ws
            break
            
    if not target_ws:
        log_callback(f"⚠️ Hedef sekme ({target_ws_title}) bulunamadı, varsayılan ilk sekme seçiliyor.")
        target_ws = target_wb.sheet1

    # 5. Ana Sheet Verilerini Okuma ve Rapor Sayılarını Karşılık Gelen Satırlara Yazma
    target_data = target_ws.get_all_values()
    if not target_data:
        log_callback("❌ Hedef sekme boş!")
        return None

    df_target = pd.DataFrame(target_data[1:], columns=target_data[0])
    
    # Nick sütununu tespit et
    target_nick_col = next((c for c in df_target.columns if 'nick' in c.lower() or 'isim' in c.lower() or 'personel' in c.lower()), df_target.columns[0])
    
    # Sayım verisini yerleştireceğimiz sütun (örneğin 'Hata bildirimi' veya 'Genel Check' / 'Rapor Sayısı')
    report_count_col = next((c for c in df_target.columns if 'rapor' in c.lower() or 'hata' in c.lower() or 'check' in c.lower()), 'Hata bildirimi')

    if report_count_col not in df_target.columns:
        df_target[report_count_col] = 0

    # Sayıları Ana Sheet'e Eşleştirme
    for idx, row in df_target.iterrows():
        nick = str(row[target_nick_col]).strip()
        if nick in user_report_counts:
            df_target.at[idx, report_count_col] = user_report_counts[nick]

    log_callback("🚀 Veriler başarıyla eşleştirildi ve hedef sekmeye aktarılmaya hazır.")
    return df_target

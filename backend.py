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
            # Sekme boşsa başlık ve verileri sıfırdan bas
            headers = [user_col, f"{target_month_name} ZA"]
            rows_to_write = [headers]
            for _, row in df_main.iterrows():
                rows_to_write.append([str(row[user_col]), str(row[za_col])])
            
            target_ws.clear()
            target_ws.update('A1', rows_to_write)
        else:
            headers = [str(h).strip() for h in target_rows[0]]
            
            # Ay veya ZA sütun indeksini bul / yoksa ekle
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
                
                # Sütun hizalamasını koru
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

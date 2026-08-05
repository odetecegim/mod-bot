import datetime
import re
import time
import unicodedata
from collections import Counter
import pandas as pd
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials

# ==========================================
# 🧹 METİN TEMİZLEME VE NORMALİZASYON
# ==========================================

def normalize_text(text):
    """Metinlerdeki Türkçe/yabancı karakterleri ve büyük-küçük harf farklarını temizler."""
    if not text:
        return ""
    text = str(text).strip().lower()
    text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
    return text

def clean_name_string(name):
    """İsim stringini sadece harf ve rakamlardan oluşacak şekilde temizler."""
    normalized = normalize_text(name)
    return re.sub(r'[^a-z0-9]', '', normalized)

# ==========================================
# 🎯 HASSAS İSİM EŞLEŞTİRME MANTIĞI
# ==========================================

def match_names(target_name, src_name):
    """
    Kullanıcı isimlerini ve Nick'lerini hassas şekilde eşleştirir.
    Soyad benzerliklerinden kaynaklı (örn: Dejan Rajic vs Stefan Rajic) 
    yanlış eşleşmeleri engeller.
    """
    t_clean = clean_name_string(target_name)
    s_clean = clean_name_string(src_name)

    if not t_clean or not s_clean:
        return False

    # 1. Birebir Tam Eşleşme (Örn: stefanrajic == stefanrajic)
    if t_clean == s_clean:
        return True

    # 2. Ad + Soyad Kelime Kontrolü (Her iki kelime de birebir aynı olmalı)
    t_words = set(normalize_text(target_name).split())
    s_words = set(normalize_text(src_name).split())

    if len(t_words) >= 2 and len(s_words) >= 2:
        return t_words == s_words

    # 3. Nick / Tek İsim Kontrolü (En az 4 karakter tam eşitlik)
    if len(t_clean) >= 4 and len(s_clean) >= 4:
        return t_clean == s_clean

    return False

# ==========================================
# 📊 RAPOR VE TABLO GÜNCELLEME İŞLEMİ
# ==========================================

def process_and_update_scores(target_sheet, source_data, column_name):
    """
    Kaynak verileri işler ve SADECE raporlama/işlem yapmış kullanıcıların
    puanlarını hedef tabloya aktarır. İşlem yapmayanları pas geçer.
    """
    # Kaynak verideki kullanıcıların işlem sayılarını hesapla
    user_counts = Counter()
    for row in source_data:
        if not row:
            continue
        
        # Kaynak tablodaki kullanıcı adını al
        raw_user = str(row[0]).strip() if len(row) > 0 else ""
        
        # Boş ve #REF! / #VALUE! gibi hatalı hücreleri atla
        if not raw_user or raw_user.startswith("#"):
            continue
        
        user_counts[raw_user] += 1

    # Hedef tablodaki kullanıcıları okuyalım
    try:
        target_rows = target_sheet.get_all_values()
    except APIError as e:
        print(f"GSpread API Hatası: {e}")
        return

    if not target_rows:
        return

    # Target sütun başlığını bul (Örn: Zula Pass, Genel Check vb.)
    header_row = target_rows[0]
    col_index = None
    for idx, col_name in enumerate(header_row):
        if column_name.lower() in str(col_name).lower():
            col_index = idx + 1  # GSpread 1-based index kullanır
            break

    if not col_index:
        print(f"Hata: '{column_name}' sütunu hedef tabloda bulunamadı.")
        return

    # Güncellenecek hücreler listesi (Batch Update)
    updates = []

    for row_idx, row in enumerate(target_rows[1:], start=2):  # Başlık 1 olduğu için 2'den başla
        if not row:
            continue
            
        # Hedef tablodaki Ad Soyad (1. sütun / B) ve Nick (2. sütun / C)
        target_name = str(row[1]).strip() if len(row) > 1 else ""
        target_nick = str(row[2]).strip() if len(row) > 2 else ""

        # #REF! hatası olan veya boş hücreleri es geç
        if target_name.startswith("#") or target_nick.startswith("#"):
            continue

        matched_count = 0
        has_matched = False

        # Kaynak verideki her kullanıcı ile hedefteki kişiyi karşılaştır
        for src_user, count in user_counts.items():
            if match_names(target_name, src_user) or match_names(target_nick, src_user):
                matched_count += count
                has_matched = True

        # KURAL: SADECE işlem yapmış (puanı > 0 olan) kullanıcıları ana tabloya işle!
        if has_matched and matched_count > 0:
            updates.append({
                'range': f"{gspread.utils.rowcol_to_a1(row_idx, col_index)}",
                'values': [[matched_count]]
            })

    # Toplu güncelleme ile Google Sheets'e gönder
    if updates:
        target_sheet.batch_update(updates)
        print(f"✅ Başarıyla {len(updates)} kullanıcının puanı güncellendi.")
    else:
        print("⚠️ İşlem yapmış kullanıcı bulunamadı, tablo güncellenmedi.")

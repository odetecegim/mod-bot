import os
import json
import streamlit as st

def setup_credentials():
    # 1. Yerel dizinde 'credentials.json' var mı kontrol et
    if os.path.exists("credentials.json"):
        return "credentials.json"
    
    # 2. Streamlit Secrets içindeki [gcp_service_account] alanını kontrol et
    try:
        if "gcp_service_account" in st.secrets:
            # TOML yapısını sözlüğe çevir
            creds_dict = dict(st.secrets["gcp_service_account"])
            
            # Temp dosyası oluşturup Google kütüphanelerinin okuyacağı formata getir
            with open("temp_credentials.json", "w", encoding="utf-8") as f:
                json.dump(creds_dict, f, ensure_ascii=False, indent=2)
                
            return "temp_credentials.json"
    except Exception as e:
        st.error(f"Secrets okuma hatası: {e}")
        
    return None

# Çağırırken üzerinde @st.cache_resource OLMAMASINA dikkat edin!
active_json_path = setup_credentials()

if not active_json_path:
    st.error("❌ Kimlik doğrulama verisi bulunamadı! Lütfen 'credentials.json' dosyasını ekleyin veya Secrets alanını kontrol edin.")
    st.stop()

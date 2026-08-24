import os
import json
import streamlit as st

def setup_credentials():
    # 1. Öncelik: Yerel credentials.json dosyası
    if os.path.exists("credentials.json"):
        return "credentials.json"
    
    # 2. Öncelik: Streamlit Secrets kontrolü
    target_key = None
    for key in ["GOOGLE_CREDENTIALS", "gcp_service_account"]:
        try:
            if key in st.secrets:
                target_key = key
                break
        except Exception:
            pass

    if target_key:
        try:
            creds_dict = dict(st.secrets[target_key])
            # private_key içerisindeki kaçış karakterlerini düzelt
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                
            with open("temp_credentials.json", "w", encoding="utf-8") as f:
                json.dump(creds_dict, f, ensure_ascii=False, indent=2)
            return "temp_credentials.json"
        except Exception as e:
            st.error(f"Secrets okuma hatası: {e}")
            return None

    return None

# Çağrılırken üstünde dekoratör (@st.cache_resource) olmadığına emin olun
active_json_path = setup_credentials()

if not active_json_path:
    st.error("❌ 'credentials.json' dosyası veya Streamlit Secrets doğrulama bilgisi bulunamadı!")
    st.stop()

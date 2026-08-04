# --- GOOGLE CREDENTIALS YÖNETİMİ ---
@st.cache_resource
def get_credentials():
    # 1. GCP_SERVICE_ACCOUNT Secrets Kontrolü (TOML Objesi veya String)
    if "GCP_SERVICE_ACCOUNT" in st.secrets:
        try:
            sec = st.secrets["GCP_SERVICE_ACCOUNT"]
            
            # Eğer Streamlit bunu zaten bir dictionary/AttrDict olarak okuduysa:
            if isinstance(sec, (dict, st.runtime.secrets.AttrDict)):
                creds = dict(sec)
            # Eğer düz string olarak okuduysa:
            elif isinstance(sec, str):
                try:
                    decoded = base64.b64decode(sec).decode('utf-8')
                    creds = json.loads(decoded)
                except Exception:
                    creds = json.loads(sec)
            else:
                creds = dict(sec)

            # Private Key format düzeltmesi (Ters slashları alt satıra çevir)
            if "private_key" in creds:
                creds["private_key"] = creds["private_key"].replace("\\n", "\n")
                
            return creds
        except Exception as e:
            st.error(f"Secrets okuma hatası: {e}")
            return None

    # 2. GOOGLE_CREDENTIALS Secrets Kontrolü (Eski format)
    elif "GOOGLE_CREDENTIALS" in st.secrets:
        creds = dict(st.secrets["GOOGLE_CREDENTIALS"])
        if "private_key" in creds:
            creds["private_key"] = creds["private_key"].replace("\\n", "\n")
        return creds

    # 3. Yerel Dosya Kontrolü
    elif os.path.exists("credentials.json"):
        return "credentials.json"
    else:
        return None

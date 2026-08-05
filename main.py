# --- SADECE ŞİFRE İLE GİRİŞ EKRANI ---
def login_screen():
    zula_logo_url = "https://upload.wikimedia.org/wikipedia/commons/9/91/Zula_New_LOGO_VECTOR.png"

    st.markdown(f"""
        <style>
            .stApp {{
                background: radial-gradient(circle at center, #2a2d34 0%, #121316 60%, #08080a 100%) !important;
            }}
            html, body, [data-testid="stAppViewContainer"] {{
                height: 100vh;
                margin: 0;
                padding: 0;
            }}
            /* Dış Kapsayıcıyı Daraltma ve Ortalamak */
            .main .block-container {{
                padding-top: 5rem !important;
                padding-bottom: 2rem !important;
                max-width: 380px !important;
                margin: 0 auto !important;
                display: flex;
                flex-direction: column;
                justify-content: center;
                position: relative;
            }}
            /* Logo Görseli */
            .main .block-container::before {{
                content: "";
                position: absolute;
                top: 8%;
                left: 50%;
                transform: translateX(-50%);
                width: 260px;
                height: 120px;
                background-image: url('{zula_logo_url}');
                background-size: contain;
                background-repeat: no-repeat;
                background-position: center;
                opacity: 0.9;
                filter: drop-shadow(0 0 20px rgba(245, 158, 11, 0.4));
                pointer-events: none;
                z-index: 0;
            }}
            /* Form / Kart Tasarımı */
            div[data-testid="stForm"] {{
                position: relative;
                z-index: 1;
                background: rgba(18, 20, 26, 0.85) !important;
                border: 1px solid rgba(255, 255, 255, 0.12) !important;
                border-radius: 20px !important;
                padding: 2rem 1.8rem !important;
                box-shadow: 0 25px 50px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
                backdrop-filter: blur(12px);
                margin-top: 10vh !important;
            }}
            label {{
                color: #f1f5f9 !important;
                font-size: 12px !important;
                font-weight: 600 !important;
                margin-bottom: 6px !important;
            }}
            div[data-baseweb="input"] {{
                background-color: rgba(10, 11, 15, 0.85) !important;
                border: 1px solid rgba(255, 255, 255, 0.15) !important;
                border-radius: 12px !important;
                color: #ffffff !important;
            }}
            div[data-testid="stFormSubmitButton"] > button {{
                background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%) !important;
                color: #ffffff !important;
                border: none !important;
                border-radius: 12px !important;
                height: 46px !important;
                font-weight: 700 !important;
                font-size: 14px !important;
                box-shadow: 0 8px 20px rgba(245, 158, 11, 0.35) !important;
                margin-top: 10px !important;
            }}
            .footer-text {{
                position: relative;
                z-index: 1;
                text-align: center;
                font-size: 12px;
                color: #94a3b8;
                margin-top: 1.2rem;
            }}
        </style>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        password_input = st.text_input("GİRİŞ ŞİFRESİ", type="password", placeholder="••••••••••••")
        submit = st.form_submit_button("Sisteme Giriş Yap →", use_container_width=True)

        if submit:
            raw_users = st.secrets.get("USERS", {})
            typed_pass = password_input.strip()

            found_user = None
            for user_name, user_pass in raw_users.items():
                if str(user_pass).strip() == typed_pass:
                    found_user = str(user_name).strip()
                    break

            if found_user:
                st.session_state["authenticated"] = True
                st.session_state["current_user"] = found_user
                st.session_state["login_time"] = time.time()
                st.session_state["login_date"] = datetime.now().date()
                st.rerun()
            else:
                st.error("❌ Hatalı veya Geçersiz Şifre!")

    st.markdown('<div class="footer-text">🔒 Oturum süresi: <strong>1 Saat / Gece 00:00 Çıkışlı</strong></div>', unsafe_allow_html=True)

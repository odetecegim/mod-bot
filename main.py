if process_btn:
            append_log_to_modbot_sheet("ZA MİKTARLARI İŞLENDİ", f"Hedef Ay: {target_month_to_process}")
            with st.spinner(f"ZA verileri Global Perf Tablosundaki ilgili sekmeye işleniyor..."):
                try:
                    sheets_data = get_available_spreadsheets(creds_input)
                    all_sheets = sheets_data.get("all", {})
                    
                    rep_id = st.session_state.get("active_report_id")
                    if not rep_id or rep_id not in all_sheets.values():
                        for name, sid in all_sheets.items():
                            if "global perf" in name.lower():
                                rep_id = sid
                                break
                    if not rep_id:
                        rep_id = TARGET_LOG_SHEET_ID

                    if isinstance(creds_input, dict):
                        client = gspread.service_account_from_dict(creds_input)
                    else:
                        client = gspread.service_account(filename=creds_input)

                    wb = client.open_by_key(rep_id)
                    ws_main = wb.sheet1  # Kaynak/Ana veri sekmesi

                    selected_year_val = st.session_state.get("selected_year", 2026)

                    log_msgs = []
                    success = process_za_and_insert_month(
                        main_ws=ws_main, 
                        target_month_name=target_month_to_process, 
                        selected_year=selected_year_val,
                        log_func=lambda m: log_msgs.append(m)
                    )
                    
                    for m in log_msgs:
                        st.write(m)
                        
                    if success:
                        st.balloons()
                        st.success(f"🎉 Veriler ilgili sekmeye tam olarak işlendi!")
                        time.sleep(1.5)
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ İşlem sırasında bir hata oluştu: {e}")

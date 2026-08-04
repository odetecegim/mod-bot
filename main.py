from flask import Flask, jsonify, request
from backend import get_available_spreadsheets, QAReportWorker

app = Flask(__name__)

# Service account JSON dosyanızın yolu veya dict verisi
CREDS_PATH = "service_account.json"

@app.route("/api/spreadsheets", methods=["GET"])
def fetch_spreadsheets():
    """
    Google Drive'da bağlı olan tüm Google Sheets dosyalarını çekip
    Frontend'deki Kaynak ve Rapor dropdown'larına gönderir.
    """
    try_sheets = get_available_spreadsheets(CREDS_PATH)
    # try_sheets = {"all": {"Tablo Adı 1": "ID_1", "Tablo Adı 2": "ID_2"}}
    
    # Frontend'in rahat okuyabilmesi için liste formatına çeviriyoruz:
    sheets_list = [
        {"name": name, "id": sheet_id} 
        for name, sheet_id in try_sheets["all"].items()
    ]
    
    return jsonify({"success": True, "spreadsheets": sheets_list})

@app.route("/api/run-report", methods=["POST"])
def run_report():
    """
    Paneldan seçilen Kaynak Tablo ID, Rapor Tablosu ID, Dil, Ay ve Yıl
    bilgilerini alıp rapor güncelleme işlemini başlatır.
    """
    data = request.json
    
    source_id = data.get("source_id")   # Seçilen Kaynak Tablo ID'si
    report_id = data.get("report_id")   # Seçilen Rapor Tablosu ID'si
    lang = data.get("lang")             # Seçilen Dil (örn: TR, EN, Tümü)
    month = data.get("month")           # Seçilen Ay (örn: Temmuz)
    year = data.get("year")             # Seçilen Yıl (örn: 2026)

    logs = []
    
    def log_callback(msg):
        logs.append(msg)
        print(f"[LOG]: {msg}")

    def progress_callback(percentage):
        print(f"[PROGRESS]: %{percentage}")

    # Rapor işleyiciyi çalıştır
    worker = QAReportWorker(
        creds_input=CREDS_PATH,
        source_id=source_id,
        report_id=report_id,
        selected_lang=lang,
        selected_year=year,
        selected_month=month,
        log_callback=log_callback,
        progress_callback=progress_callback
    )
    
    try:
        worker.process()
        return jsonify({"success": True, "logs": logs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "logs": logs}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)

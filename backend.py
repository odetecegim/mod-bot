class PORLanguageHandler(BaseLanguageHandler):
    def map_category(self, ws_title):
        norm = normalize_text_strict(ws_title)
        if self.is_test_sheet(norm):
            return None
        
        # 'Cartão de Missão' vb. sekmeleri ana tablodaki "G. Kartı (Günlük)" veya "Zula Pass" sütununa eşle
        if any(k in norm for k in ["cartaodemissao", "missao", "diaria", "pass", "gkarti", "kart"]):
            return "G. Kartı (Günlük)"
            
        # 'Verificação Geral' vb. sekmeleri "Genel Check" sütununa eşle
        elif any(k in norm for k in ["verificacaogeral", "geral", "check"]):
            return "Genel Check"
            
        # 'Relatório de Erros' vb. sekmeleri "Hata bildirimi" sütununa eşle
        elif any(k in norm for k in ["relatoriodeerros", "erros", "error", "hata", "bug"]):
            return "Hata bildirimi"
            
        return re.sub(r'\(.*?\)', '', ws_title).strip()

class ESPLanguageHandler(BaseLanguageHandler):
    def map_category(self, ws_title):
        norm = normalize_text_strict(ws_title)
        if self.is_test_sheet(norm):
            return None
        if any(k in norm for k in ["tarjetademision", "mision", "diaria", "pass", "gkarti", "kart"]):
            return "G. Kartı (Günlük)"
        elif any(k in norm for k in ["revisiongeneral", "general", "check"]):
            return "Genel Check"
        elif any(k in norm for k in ["reportedeerrores", "errores", "error", "hata", "bug"]):
            return "Hata bildirimi"
        return re.sub(r'\(.*?\)', '', ws_title).strip()

class TRLanguageHandler(BaseLanguageHandler):
    def map_category(self, ws_title):
        norm = normalize_text_strict(ws_title)
        if self.is_test_sheet(norm):
            return None
        if any(k in norm for k in ["zulapass", "gunluk", "gkarti", "mission", "pass", "kart"]):
            return "G. Kartı (Günlük)"
        elif any(k in norm for k in ["genelcheck", "genel"]):
            return "Genel Check"
        elif any(k in norm for k in ["errorreporting", "hata", "error", "bug"]):
            return "Hata bildirimi"
        return re.sub(r'\(.*?\)', '', ws_title).strip()

class ENGLanguageHandler(BaseLanguageHandler):
    def map_category(self, ws_title):
        norm = normalize_text_strict(ws_title)
        if self.is_test_sheet(norm):
            return None
        if any(k in norm for k in ["missioncard", "mission", "card", "pass", "gkarti", "kart"]):
            return "G. Kartı (Günlük)"
        elif any(k in norm for k in ["generalcheck", "general", "check"]):
            return "Genel Check"
        elif any(k in norm for k in ["errorreporting", "error", "bug", "hata"]):
            return "Hata bildirimi"
        return re.sub(r'\(.*?\)', '', ws_title).strip()

import os
import json
from typing import Dict, List, Any
from app.utils.logging import logger

class DictionaryManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DictionaryManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, dictionary_dir: str = None):
        if self._initialized:
            return
        
        if not dictionary_dir:
            # Default to the directory of this file
            dictionary_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.dictionary_dir = dictionary_dir
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.load_all()
        self._initialized = True

    def load_all(self):
        dict_files = {
            "symptoms": "symptoms.json",
            "diseases": "diseases.json",
            "drugs": "drug_dictionary.json",
            "anatomy": "anatomy.json",
            "procedures": "procedures.json",
            "negations": "negations.json",
            "family": "family.json"
        }
        
        for name, filename in dict_files.items():
            path = os.path.join(self.dictionary_dir, filename)
            if not os.path.exists(path):
                logger.error(f"Dictionary file not found: {path}")
                self.cache[name] = {"version": "0.0", "updated": "unknown", "entries": {}}
                continue
            
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Simple validation
                if "version" not in data or "entries" not in data:
                    raise ValueError("Missing 'version' or 'entries' key")
                
                self.cache[name] = data
                logger.info(f"Loaded dictionary '{name}' version {data.get('version')} from {filename}")
            except Exception as e:
                logger.error(f"Error loading dictionary {filename}: {e}", exc_info=True)
                self.cache[name] = {"version": "0.0", "updated": "unknown", "entries": {}}

    def get_symptoms(self) -> Dict[str, List[str]]:
        return self.cache.get("symptoms", {}).get("entries", {})

    def get_diseases(self) -> Dict[str, List[str]]:
        return self.cache.get("diseases", {}).get("entries", {})

    def get_drugs(self) -> Dict[str, List[str]]:
        return self.cache.get("drugs", {}).get("entries", {})

    def get_anatomy(self) -> Dict[str, List[str]]:
        return self.cache.get("anatomy", {}).get("entries", {})

    def get_procedures(self) -> Dict[str, List[str]]:
        return self.cache.get("procedures", {}).get("entries", {})

    def get_negations(self) -> Dict[str, List[str]]:
        return self.cache.get("negations", {}).get("entries", {})

    def get_family(self) -> Dict[str, List[str]]:
        return self.cache.get("family", {}).get("entries", {})

# Singleton instance for application usage
dictionary_manager = DictionaryManager()

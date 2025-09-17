# /src/utils/config/settings.py

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

class SettingsManager:
    _instance: Optional['SettingsManager'] = None
    _config: Optional[Dict[str, Any]] = None

    def __new__(cls) -> 'SettingsManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self) -> None:
        """Loads the YAML configuration file."""
        config_path = Path(__file__).parent / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found at {config_path}")
        
        with open(config_path, 'r') as f:
            self._config = yaml.safe_load(f)

    def _substitute_env_vars(self, value: Any) -> Any:
        """
        Recursively substitutes environment variables in the format ${VAR_NAME}.
        """
        if isinstance(value, dict):
            return {k: self._substitute_env_vars(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._substitute_env_vars(i) for i in value]
        elif isinstance(value, str):
            # Regex to find all occurrences of ${VAR_NAME}
            matches = re.findall(r"\$\{([A-Z0-9_]+)\}", value)
            for var_name in matches:
                env_value = os.getenv(var_name)
                if env_value is None:
                    
                    env_value = "" 
                value = value.replace(f"${{{var_name}}}", env_value)
            return value
        return value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a configuration value by a dot-separated key and
        substitutes any environment variables found in the value.
        """
        if self._config is None:
            return default
        
        keys = key.split('.')
        value = self._config
        try:
            for k in keys:
                value = value[k]
        except (KeyError, TypeError):
            return default
            
        return self._substitute_env_vars(value)

    def get_server_config(self) -> Dict[str, Any]:
        return self.get("server", {})

    def get_app_config(self) -> Dict[str, Any]:
        return self.get("app", {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        return self.get("logging", {})

# Global instance
settings = SettingsManager()
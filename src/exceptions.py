"""
自訂異常類別

提供專案特定的異常，用於錯誤處理和重試邏輯。
"""


class TranslationError(Exception):
    """基礎異常類別"""
    pass


class ConfigError(TranslationError):
    """配置錯誤

    當配置檔案缺失、格式錯誤或欄位缺失時拋出。
    """
    def __init__(self, message: str, config_path: str = None):
        self.config_path = config_path
        super().__init__(message)


class APIError(TranslationError):
    """API 調用錯誤

    當 LLM API 調用失敗時拋出。

    Attributes:
        provider: API 提供者名稱 (gemini/openai/anthropic)
        retryable: 是否可重試（True 表示暫時性錯誤，可以重試）
    """
    def __init__(self, provider: str, message: str, retryable: bool = True):
        self.provider = provider
        self.retryable = retryable
        super().__init__(f"[{provider}] {message}")


class ValidationError(TranslationError):
    """資料驗證錯誤

    當資料格式不符合預期時拋出（如 YAML 結構錯誤、segment_id 不連續等）。
    """
    pass


class ParseError(TranslationError):
    """解析錯誤

    當解析 SRT、YAML 或 JSON 失敗時拋出。
    """
    def __init__(self, message: str, file_path: str = None, line_number: int = None):
        self.file_path = file_path
        self.line_number = line_number
        super().__init__(message)

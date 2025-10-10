"""
Gemini API 客戶端

使用最新的 google-genai SDK (2024+) 提供 Gemini API 調用。

主要功能：
- 新版 SDK 支援 (google.genai)
- 智能重試機制（指數退避）
- Token 使用統計
- 環境變數 API key 管理
"""

import os
import time
import logging
from typing import Dict, Any

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from .base_client import BaseLLMClient
from ..models import APIResponse, TokenUsage
from ..exceptions import APIError, ConfigError


logger = logging.getLogger(__name__)


class GeminiClient(BaseLLMClient):
    """Gemini API 客戶端"""

    def __init__(self, config: Dict[str, Any]):
        """初始化 Gemini 客戶端

        Args:
            config: 包含以下鍵值的字典：
                - model: 模型名稱（如 "gemini-2.0-flash-exp"）
                - timeout: 超時時間（秒），預設 120
                - max_retries: 最大重試次數，預設 3
                - temperature: 溫度參數（0.0-1.0），預設 0.2
                - max_output_tokens: 最大輸出 tokens，預設 8192

        Raises:
            ConfigError: SDK 未安裝或 API key 未設定
        """
        self.model_name = config['model']  # 直接從扁平結構讀取
        self.timeout = config.get('timeout', 120)
        self.max_retries = config.get('max_retries', 3)
        self.temperature = config.get('temperature', 0.2)
        self.max_output_tokens = config.get('max_output_tokens', 8192)
        self.api_key = self._get_api_key_from_env("GEMINI_API_KEY")
        self._init_client()

    def _init_client(self) -> None:
        """初始化 Gemini 客戶端"""
        if genai is None or types is None:
            raise ConfigError(
                "google-genai library not installed. Run: pip install google-genai>=0.1.0"
            )

        try:
            self.client = genai.Client(api_key=self.api_key)
            logger.info(f"Gemini client initialized: model={self.model_name}, "
                       f"temperature={self.temperature}, max_tokens={self.max_output_tokens}")
        except Exception as e:
            raise ConfigError(f"Failed to initialize Gemini client: {e}")

    def _get_api_key_from_env(self, env_name: str) -> str:
        """從環境變數獲取 API Key

        Args:
            env_name: 環境變數名稱

        Returns:
            str: API Key

        Raises:
            ConfigError: 環境變數未設定
        """
        api_key = os.getenv(env_name)
        if not api_key:
            raise ConfigError(
                f"Environment variable {env_name} not set. "
                f"Please create .env file with {env_name}=your_api_key"
            )
        return api_key

    def generate_content(self, system_prompt: str, user_message: str) -> APIResponse:
        """生成內容並返回統一格式

        實作重試邏輯：
        - 可重試錯誤：timeout, rate limit, server error
        - 不可重試錯誤：invalid API key, bad request
        - 使用指數退避（exponential backoff）

        Args:
            system_prompt: 系統提示詞
            user_message: 用戶訊息

        Returns:
            APIResponse: 統一格式的 API 回應
        """
        start_time = time.time()

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"Gemini API call attempt {attempt + 1}/{self.max_retries + 1}")

                # 調用 Gemini API
                response = self._call_api(system_prompt, user_message)

                # 提取 token 使用統計
                token_usage = self._extract_token_usage(response)

                # 提取生成的內容
                content = self._extract_content(response)

                processing_time = time.time() - start_time

                logger.info(f"Gemini API success - Input: {token_usage.input_tokens}, "
                          f"Output: {token_usage.output_tokens}, Time: {processing_time:.2f}s")

                return APIResponse.success_response(
                    provider="gemini",
                    content=content,
                    token_usage=token_usage,
                    processing_time=processing_time
                )

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Gemini API failed (attempt {attempt + 1}): {error_msg}")

                # 判斷是否可重試
                retryable = self._is_retryable_error(e)

                if attempt == self.max_retries or not retryable:
                    processing_time = time.time() - start_time
                    logger.error(f"Gemini API failed after {attempt + 1} attempts: {error_msg}")

                    return APIResponse.error_response(
                        provider="gemini",
                        error_message=error_msg,
                        processing_time=processing_time
                    )

                # 指數退避延遲
                if attempt < self.max_retries:
                    delay = min(2 ** attempt, 60)  # 最大延遲 60 秒
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)

        # 理論上不會到達這裡
        return APIResponse.error_response(
            provider="gemini",
            error_message="Max retries exceeded",
            processing_time=time.time() - start_time
        )

    def _call_api(self, system_prompt: str, user_message: str):
        """調用 Gemini API（新版 SDK）

        Args:
            system_prompt: 系統指令
            user_message: 用戶內容

        Returns:
            Gemini API 回應物件

        Raises:
            APIError: API 調用失敗
        """
        try:
            # 構建生成配置
            # 使用 response_mime_type 強制 JSON 輸出，避免 markdown 包裝
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                response_mime_type="application/json"  # 官方推薦：防止 markdown 包裝
            )

            # 使用新版 SDK 調用
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=user_message,
                config=config
            )

            return response

        except Exception as e:
            # 包裝原始異常
            raise APIError("gemini", str(e), retryable=self._is_retryable_error(e))

    def _extract_content(self, response) -> str:
        """從 Gemini response 提取生成的內容

        Gemini 經常會用 markdown 代碼塊包裝 JSON 回應（即使 prompt 禁止）。
        此方法會自動清理這些包裝。

        Args:
            response: Gemini API 回應物件

        Returns:
            str: 生成的文字內容（已清理 markdown 包裝）
        """
        try:
            content = ""

            # 新版 SDK 的回應格式
            if hasattr(response, 'text') and response.text:
                content = response.text
            elif hasattr(response, 'candidates') and response.candidates:
                # 嘗試從 candidates 中提取
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts') and candidate.content.parts:
                            for part in candidate.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    content = part.text
                                    break

            if not content:
                logger.warning("No text content found in Gemini response")
                return ""

            # 清理 Gemini 常見的 markdown 代碼塊包裝
            content = content.strip()

            # 處理 ```json ... ``` 包裝
            if content.startswith("```json"):
                logger.debug("Removing ```json markdown wrapper from Gemini response")
                content = content[7:]  # 移除 "```json" 和可能的換行
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            # 處理通用 ``` ... ``` 包裝
            elif content.startswith("```"):
                logger.debug("Removing generic ``` markdown wrapper from Gemini response")
                content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            return content

        except Exception as e:
            logger.error(f"Failed to extract content from Gemini response: {e}")
            return ""

    def _extract_token_usage(self, response) -> TokenUsage:
        """從 Gemini response 提取 token 統計

        Args:
            response: Gemini API 回應物件

        Returns:
            TokenUsage: Token 使用統計
        """
        try:
            # 新版 SDK 的 usage metadata
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                return TokenUsage(
                    input_tokens=getattr(usage, 'prompt_token_count', 0),
                    output_tokens=getattr(usage, 'candidates_token_count', 0),
                    total_tokens=getattr(usage, 'total_token_count', 0)
                )
            elif hasattr(response, 'usage') and response.usage:
                # 備用屬性名稱
                usage = response.usage
                return TokenUsage(
                    input_tokens=getattr(usage, 'input_tokens', 0),
                    output_tokens=getattr(usage, 'output_tokens', 0),
                    total_tokens=getattr(usage, 'total_tokens', 0)
                )
            else:
                logger.warning("No usage metadata found in Gemini response")
                return TokenUsage.zero()

        except Exception as e:
            logger.error(f"Failed to extract token usage: {e}")
            return TokenUsage.zero()

    def _is_retryable_error(self, error: Exception) -> bool:
        """判斷錯誤是否可重試

        Args:
            error: 異常物件

        Returns:
            bool: True 表示可重試，False 表示不可重試
        """
        error_str = str(error).lower()

        # 可重試的錯誤類型
        retryable_keywords = [
            'timeout', 'connection', 'network', 'temporary',
            'rate limit', 'quota', 'server error',
            '429',  # Too Many Requests
            '500',  # Internal Server Error
            '502',  # Bad Gateway
            '503',  # Service Unavailable
            '504'   # Gateway Timeout
        ]

        for keyword in retryable_keywords:
            if keyword in error_str:
                return True

        # 不可重試的錯誤
        non_retryable_keywords = [
            'invalid api key', 'authentication',
            '401',  # Unauthorized
            '403',  # Forbidden
            'invalid request', 'bad request',
            '400',  # Bad Request
            'not found',
            '404'   # Not Found
        ]

        for keyword in non_retryable_keywords:
            if keyword in error_str:
                return False

        # 預設為可重試（保守策略）
        return True

    def get_client_info(self) -> Dict[str, Any]:
        """取得客戶端資訊

        Returns:
            Dict: 客戶端配置資訊
        """
        return {
            "provider": "gemini",
            "model": self.model_name,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "api_key_set": bool(self.api_key)
        }

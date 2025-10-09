"""
OpenAI API 客戶端

使用 OpenAI Responses API 提供 GPT-5 等模型調用。

主要功能：
- 支援 GPT-5 系列模型（gpt-5-mini, gpt-5）
- Responses API（非傳統 Chat Completions API）
- 智能重試機制（指數退避）
- Token 使用統計
- 環境變數 API key 管理

參考：Phase18 social-automation 專案
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from .base_client import BaseLLMClient
from ..models import APIResponse, TokenUsage
from ..exceptions import APIError, ConfigError


logger = logging.getLogger(__name__)


class OpenAIClient(BaseLLMClient):
    """OpenAI API 客戶端（同步版本）"""

    def __init__(self, config: Dict[str, Any]):
        """初始化 OpenAI 客戶端

        Args:
            config: 包含以下鍵值的字典：
                - model: 模型名稱（如 "gpt-5-mini", "gpt-5"）
                - timeout: 超時時間（秒），預設 120
                - max_retries: 最大重試次數，預設 3
                - temperature: 溫度參數（0.0-2.0），預設 1.0
                - max_output_tokens: 最大輸出 tokens，預設 8192

        Raises:
            ConfigError: SDK 未安裝或 API key 未設定
        """
        self.model_name = config['model']  # 直接從扁平結構讀取
        self.timeout = config.get('timeout', 120)
        self.max_retries = config.get('max_retries', 3)
        self.temperature = config.get('temperature', 1.0)
        self.max_output_tokens = config.get('max_output_tokens', 8192)
        self.api_key = self._get_api_key_from_env("OPENAI_API_KEY")
        self._init_client()

    def _init_client(self) -> None:
        """初始化 OpenAI 客戶端"""
        if OpenAI is None:
            raise ConfigError(
                "openai library not installed. Run: pip install openai>=1.0.0"
            )

        try:
            self.client = OpenAI(
                api_key=self.api_key,
                timeout=self.timeout
            )
            logger.info(f"OpenAI client initialized: model={self.model_name}, "
                       f"temperature={self.temperature}, max_tokens={self.max_output_tokens}")
        except Exception as e:
            raise ConfigError(f"Failed to initialize OpenAI client: {e}")

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
        """生成內容並返回統一格式（同步版本）

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
                logger.debug(f"OpenAI API call attempt {attempt + 1}/{self.max_retries + 1}")

                # 調用 OpenAI API
                response = self._call_api(system_prompt, user_message)

                # 提取 token 使用統計
                token_usage = self._extract_token_usage(response)

                # 提取生成的內容
                content = self._extract_content(response)

                processing_time = time.time() - start_time

                logger.info(f"OpenAI API success - Input: {token_usage.input_tokens}, "
                          f"Output: {token_usage.output_tokens}, Time: {processing_time:.2f}s")

                return APIResponse.success_response(
                    provider="openai",
                    content=content,
                    token_usage=token_usage,
                    processing_time=processing_time
                )

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"OpenAI API failed (attempt {attempt + 1}): {error_msg}")

                # 判斷是否可重試
                retryable = self._is_retryable_error(e)

                if attempt == self.max_retries or not retryable:
                    processing_time = time.time() - start_time
                    logger.error(f"OpenAI API failed after {attempt + 1} attempts: {error_msg}")

                    return APIResponse.error_response(
                        provider="openai",
                        error_message=error_msg,
                        processing_time=processing_time
                    )

                # 指數退避延遲（同步版本）
                if attempt < self.max_retries:
                    delay = min(2 ** attempt, 60)  # 最大延遲 60 秒
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)

        # 理論上不會到達這裡
        return APIResponse.error_response(
            provider="openai",
            error_message="Max retries exceeded",
            processing_time=time.time() - start_time
        )

    def _call_api(self, system_prompt: str, user_message: str):
        """調用 OpenAI Responses API

        使用新版 Responses API（非 Chat Completions API）
        參考：Phase18 驗證成功的方法

        Args:
            system_prompt: 系統指令
            user_message: 用戶內容

        Returns:
            OpenAI API 回應物件

        Raises:
            APIError: API 調用失敗
        """
        try:
            # 準備 messages（Responses API 格式）
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]

            # 構建 API 配置（參考 Phase18）
            api_config = {
                "model": self.model_name,
                "input": messages,
                "timeout": self.timeout,
                "reasoning": {"effort": "low"},  # 降低推理深度以減少 token 使用
            }

            # 使用 Responses API（同步調用）
            response = self.client.responses.create(**api_config)

            return response

        except Exception as e:
            # 包裝原始異常
            raise APIError("openai", str(e), retryable=self._is_retryable_error(e))

    def _extract_content(self, response) -> str:
        """從 OpenAI Responses API 回應提取內容

        參考 Phase15/Phase18 成功實作

        Args:
            response: OpenAI API 回應物件

        Returns:
            str: 生成的文字內容
        """
        try:
            # Responses API 回應結構（Phase18 驗證成功的方法）
            # response.output[] 包含多個項目，需要找到 message 類型
            if hasattr(response, 'output') and response.output:
                for output_item in response.output:
                    # 尋找 message 類型的輸出
                    if hasattr(output_item, 'type') and output_item.type == 'message':
                        if hasattr(output_item, 'content') and output_item.content:
                            # content 是列表，包含 text 項目
                            for content_item in output_item.content:
                                if hasattr(content_item, 'type') and content_item.type == 'output_text':
                                    if hasattr(content_item, 'text'):
                                        logger.debug("Successfully extracted content from response.output")
                                        return content_item.text

                # 記錄 output 類型用於 debug
                output_types = [getattr(item, 'type', 'unknown') for item in response.output]
                logger.debug(f"Output types found: {output_types}")

            # 備用：嘗試舊版 API 格式（Chat Completions API）
            if hasattr(response, 'choices') and response.choices:
                choice = response.choices[0]
                if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                    logger.debug("Extracted content from choices format (legacy)")
                    return choice.message.content

            logger.warning("No text content found in OpenAI response")
            return ""

        except Exception as e:
            logger.error(f"Failed to extract content from OpenAI response: {e}")
            return ""

    def _extract_token_usage(self, response) -> TokenUsage:
        """從 OpenAI response 提取 token 統計

        支援 Responses API 和 Chat Completions API

        Args:
            response: OpenAI API 回應物件

        Returns:
            TokenUsage: Token 使用統計
        """
        try:
            # Responses API 格式
            if hasattr(response, 'usage') and response.usage:
                usage = response.usage
                return TokenUsage(
                    input_tokens=getattr(usage, 'prompt_tokens', 0),
                    output_tokens=getattr(usage, 'completion_tokens', 0),
                    total_tokens=getattr(usage, 'total_tokens', 0)
                )

            # 備用：檢查其他可能的屬性
            elif hasattr(response, 'token_usage'):
                usage = response.token_usage
                return TokenUsage(
                    input_tokens=getattr(usage, 'input_tokens', 0),
                    output_tokens=getattr(usage, 'output_tokens', 0),
                    total_tokens=getattr(usage, 'total_tokens', 0)
                )

            else:
                logger.warning("No usage metadata found in OpenAI response")
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
            'rate limit', 'quota', 'server error', 'overloaded',
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
            '404',  # Not Found
            'model not found', 'invalid model'
        ]

        for keyword in non_retryable_keywords:
            if keyword in error_str:
                return False

        # 檢查 OpenAI 特定異常類型
        error_type = type(error).__name__.lower()
        if 'autherror' in error_type or 'permissionerror' in error_type:
            return False

        # 預設為可重試（保守策略）
        return True

    def get_client_info(self) -> Dict[str, Any]:
        """取得客戶端資訊

        Returns:
            Dict: 客戶端配置資訊
        """
        return {
            "provider": "openai",
            "model": self.model_name,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "api_key_set": bool(self.api_key)
        }

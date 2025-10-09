"""
LLM 客戶端抽象基類

定義所有 LLM 客戶端的統一介面。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from ..models import APIResponse


class BaseLLMClient(ABC):
    """LLM 客戶端抽象基類

    所有具體的 LLM 客戶端（Gemini、OpenAI、Anthropic）都應繼承此類。
    """

    @abstractmethod
    def generate_content(self, system_prompt: str, user_message: str) -> APIResponse:
        """生成內容

        Args:
            system_prompt: 系統提示詞（定義 AI 的角色和行為）
            user_message: 用戶訊息（實際要處理的內容）

        Returns:
            APIResponse: 統一格式的 API 回應

        Raises:
            APIError: API 調用失敗
            ConfigError: 配置錯誤
        """
        pass

    @abstractmethod
    def get_client_info(self) -> Dict[str, Any]:
        """取得客戶端資訊

        Returns:
            Dict: 包含 provider, model, timeout 等資訊
        """
        pass

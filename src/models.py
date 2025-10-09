"""
核心資料模型

使用 @dataclass 定義結構化資料，提供型別安全和自動序列化。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TokenUsage:
    """Token 使用統計"""
    input_tokens: int
    output_tokens: int
    total_tokens: int

    def __post_init__(self):
        """驗證 token 統計的一致性"""
        if self.total_tokens != self.input_tokens + self.output_tokens:
            # 自動修正 total_tokens
            self.total_tokens = self.input_tokens + self.output_tokens

    def format_display(self) -> str:
        """格式化顯示 token 使用量

        Returns:
            str: 格式化字串，如 "1,234 / 567"
        """
        return f"{self.input_tokens:,} / {self.output_tokens:,}"

    @classmethod
    def zero(cls) -> 'TokenUsage':
        """創建零值 TokenUsage"""
        return cls(0, 0, 0)


@dataclass
class APIResponse:
    """API 回應統一格式

    所有 LLM 客戶端回傳此格式，確保介面一致。

    Attributes:
        provider: API 提供者名稱 ("gemini" / "openai" / "anthropic")
        success: 調用是否成功
        content: 生成的內容（成功時）
        token_usage: Token 使用統計
        error_message: 錯誤訊息（失敗時）
        processing_time: API 處理時間（秒）
    """
    provider: str
    success: bool
    content: str
    token_usage: TokenUsage
    error_message: Optional[str] = None
    processing_time: float = 0.0

    @classmethod
    def success_response(
        cls,
        provider: str,
        content: str,
        token_usage: TokenUsage,
        processing_time: float = 0.0
    ) -> 'APIResponse':
        """創建成功回應

        Args:
            provider: API 提供者名稱
            content: 生成的內容
            token_usage: Token 使用統計
            processing_time: 處理時間（秒）

        Returns:
            APIResponse: 成功的回應物件
        """
        return cls(
            provider=provider,
            success=True,
            content=content,
            token_usage=token_usage,
            processing_time=processing_time
        )

    @classmethod
    def error_response(
        cls,
        provider: str,
        error_message: str,
        processing_time: float = 0.0
    ) -> 'APIResponse':
        """創建錯誤回應

        Args:
            provider: API 提供者名稱
            error_message: 錯誤訊息
            processing_time: 處理時間（秒）

        Returns:
            APIResponse: 失敗的回應物件
        """
        return cls(
            provider=provider,
            success=False,
            content="",
            token_usage=TokenUsage.zero(),
            error_message=error_message,
            processing_time=processing_time
        )

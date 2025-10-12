#!/usr/bin/env python3
"""
Topics Analysis Driver

調用 LLM 分析 segments JSON 並生成 topics.json。

流程：
1. 載入 segments JSON（來自 main_yaml_to_json.py）
2. 載入 system prompt（prompts/topic_analysis_system.txt）
3. 調用 LLM 生成主題結構
4. 驗證並寫入 topics.json

依賴：
- src/clients/gemini_client.py（或其他 LLM 客戶端）
- src/models.py（APIResponse, TokenUsage）
- src/exceptions.py（ConfigError, APIError, ValidationError）
"""

import json
import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 導入共用模組
from src.clients.gemini_client import GeminiClient
from src.clients.openai_client import OpenAIClient
from src.config_loader import load_config as load_project_config
from src.exceptions import ConfigError, APIError, ValidationError


def setup_logging(level: str = "INFO"):
    """設置日誌配置

    Args:
        level: 日誌級別（DEBUG/INFO/WARNING/ERROR）
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def load_config(config_path: Path) -> Dict[str, Any]:
    """載入並驗證配置檔"""
    config = load_project_config(config_path)

    required = ['episode_id', 'output', 'prompts', 'topic_analysis']
    for field in required:
        if field not in config:
            raise ConfigError(f"Missing required field: {field}", str(config_path))

    return config


def load_segments_json(json_path: Path) -> List[Dict[str, Any]]:
    """載入 segments JSON

    Args:
        json_path: JSON 檔案路徑

    Returns:
        List[Dict]: Segments 陣列

    Raises:
        ConfigError: 檔案不存在或格式錯誤
    """
    if not json_path.exists():
        raise ConfigError(f"Segments JSON not found: {json_path}")

    try:
        with json_path.open('r', encoding='utf-8') as f:
            segments = json.load(f)

        if not isinstance(segments, list):
            raise ConfigError("Segments JSON must be an array")

        if len(segments) == 0:
            raise ConfigError("Segments JSON is empty")

        logging.info(f"Loaded {len(segments)} segments from {json_path}")
        return segments

    except json.JSONDecodeError as e:
        raise ConfigError(f"Failed to parse segments JSON: {e}")


def load_system_prompt(prompt_path: Path) -> str:
    """載入 system prompt

    Args:
        prompt_path: Prompt 檔案路徑

    Returns:
        str: System prompt 內容

    Raises:
        ConfigError: 檔案不存在
    """
    if not prompt_path.exists():
        raise ConfigError(f"System prompt not found: {prompt_path}")

    with prompt_path.open('r', encoding='utf-8') as f:
        prompt = f.read().strip()

    logging.info(f"Loaded system prompt from {prompt_path} ({len(prompt)} chars)")
    return prompt


def init_client(config: Dict[str, Any]):
    """初始化 LLM 客戶端

    Args:
        config: 配置資料

    Returns:
        BaseLLMClient: 初始化的客戶端（GeminiClient 或 OpenAIClient）

    Raises:
        ConfigError: 不支援的 provider 或初始化失敗
    """
    # 扁平結構：直接從 topic_analysis 讀取所有配置
    model_config = config['topic_analysis']
    provider = model_config['provider']

    if provider == 'gemini':
        client = GeminiClient(model_config)
        logging.info(f"Initialized Gemini client: {client.get_client_info()}")
        return client
    elif provider == 'openai':
        client = OpenAIClient(model_config)
        logging.info(f"Initialized OpenAI client: {client.get_client_info()}")
        return client
    else:
        raise ConfigError(f"Unsupported provider: {provider}. Supported: gemini, openai")


def validate_topics_json(data: Dict[str, Any], total_segments: int) -> List[str]:
    """驗證 topics.json 結構

    Args:
        data: 解析後的 JSON 資料
        total_segments: 總段落數（用於檢查覆蓋度）

    Returns:
        List[str]: 警告訊息列表

    Raises:
        ValidationError: 嚴重的驗證錯誤
    """
    warnings = []

    # 檢查必要欄位
    if 'global_summary' not in data or not data['global_summary']:
        raise ValidationError("Missing or empty 'global_summary'")

    if 'topics' not in data or not isinstance(data['topics'], list):
        raise ValidationError("Missing or invalid 'topics' field")

    if len(data['topics']) == 0:
        raise ValidationError("No topics found in response")

    # 驗證每個 topic
    topics = data['topics']

    for idx, topic in enumerate(topics):
        # 檢查必要欄位
        required_fields = ['topic_id', 'segment_start', 'segment_end', 'title', 'summary']
        for field in required_fields:
            if field not in topic or not topic[field]:
                raise ValidationError(f"Topic {idx + 1} missing required field: {field}")

        # 取得 topic_id（允許語意化 ID，不強制序號格式）
        topic_id = topic['topic_id']

        # 檢查範圍有效性
        start = topic['segment_start']
        end = topic['segment_end']

        if not isinstance(start, int) or not isinstance(end, int):
            raise ValidationError(f"Topic {topic_id}: segment_start/end must be integers")

        if start > end:
            raise ValidationError(f"Topic {topic_id}: segment_start ({start}) > segment_end ({end})")

        if start < 1:
            raise ValidationError(f"Topic {topic_id}: segment_start must be >= 1")

    # 檢查範圍覆蓋度和連續性
    topics_sorted = sorted(topics, key=lambda t: t['segment_start'])
    covered_segments = set()

    for i, topic in enumerate(topics_sorted):
        start = topic['segment_start']
        end = topic['segment_end']

        # 檢查是否與前一個 topic 有空隙或重疊
        if i > 0:
            prev_end = topics_sorted[i - 1]['segment_end']
            if start != prev_end + 1:
                if start > prev_end + 1:
                    warnings.append(f"Gap between topics: {prev_end + 1} to {start - 1}")
                else:
                    raise ValidationError(f"Topics overlap: {topic['topic_id']} starts at {start}, "
                                         f"but previous ends at {prev_end}")

        # 記錄覆蓋的段落
        covered_segments.update(range(start, end + 1))

    # 檢查是否覆蓋所有段落
    expected_coverage = set(range(1, total_segments + 1))
    missing = expected_coverage - covered_segments
    extra = covered_segments - expected_coverage

    if missing:
        warnings.append(f"Missing segments: {sorted(missing)}")

    if extra:
        warnings.append(f"Extra segments (beyond total): {sorted(extra)}")

    logging.info(f"Validation passed with {len(warnings)} warnings")
    return warnings


def write_topics_json(data: Dict[str, Any], output_path: Path):
    """寫入 topics.json

    Args:
        data: Topics 資料
        output_path: 輸出檔案路徑
    """
    # 創建輸出目錄
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open('w', encoding='utf-8') as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )

    logging.info(f"Wrote topics JSON to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate topics.yaml using LLM analysis of segments'
    )
    parser.add_argument(
        '--config',
        type=Path,
        required=True,
        help='Path to YAML configuration file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate inputs without calling API'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging (DEBUG level)'
    )

    args = parser.parse_args()

    # 設置日誌
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level)

    try:
        # 載入配置
        logging.info(f"Loading config from {args.config}")
        config = load_config(args.config)
        episode_id = config['episode_id']
        logging.info(f"Processing episode: {episode_id}")

        # 取得檔案路徑
        segments_json_path = Path(config['output']['json'])
        topics_json_path = Path(config['output']['topics_json'])
        system_prompt_path = Path(config['prompts']['topic_analysis_system'])

        # 載入輸入檔案
        segments = load_segments_json(segments_json_path)
        system_prompt = load_system_prompt(system_prompt_path)

        # 準備 user message（JSON 序列化）
        user_message = json.dumps(segments, ensure_ascii=False, indent=None)
        logging.info(f"Prepared user message: {len(user_message)} chars, {len(segments)} segments")

        # Dry run 模式（扁平結構，直接從 topic_analysis 讀取）
        dry_run = args.dry_run or config['topic_analysis'].get('dry_run', False)
        if dry_run:
            logging.info("DRY RUN mode - skipping API call")
            logging.info(f"Would call API with:")
            logging.info(f"  System prompt: {len(system_prompt)} chars")
            logging.info(f"  User message: {len(user_message)} chars")
            logging.info("Validation passed, exiting without API call")
            sys.exit(0)

        # 初始化 LLM 客戶端
        client = init_client(config)

        # 調用 API
        logging.info("Calling LLM API for topic analysis...")
        response = client.generate_content(system_prompt, user_message)

        if not response.success:
            logging.error(f"API call failed: {response.error_message}")
            sys.exit(1)

        logging.info(f"API call successful - Tokens: {response.token_usage.format_display()}, "
                    f"Time: {response.processing_time:.2f}s")

        # 解析回應 JSON
        logging.info("Parsing LLM response as JSON...")
        try:
            topics_data = json.loads(response.content)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse LLM response as JSON: {e}")
            logging.error("Response content (first 500 chars):")
            logging.error(response.content[:500])
            sys.exit(1)

        # 驗證結構（扁平結構，直接從 topic_analysis 讀取）
        logging.info("Validating topics structure...")
        strict_validation = config['topic_analysis'].get('strict_validation', True)

        try:
            warnings = validate_topics_json(topics_data, len(segments))

            if warnings:
                logging.warning(f"Validation warnings ({len(warnings)}):")
                for warning in warnings:
                    logging.warning(f"  - {warning}")

                if strict_validation:
                    logging.error("Strict validation enabled - treating warnings as errors")
                    sys.exit(1)

        except ValidationError as e:
            logging.error(f"Validation failed: {e}")
            sys.exit(1)

        # 添加 episode_id
        topics_data['episode_id'] = episode_id

        # 寫入輸出檔案
        write_topics_json(topics_data, topics_json_path)

        logging.info("✓ Topics analysis completed successfully!")
        logging.info(f"  Generated {len(topics_data['topics'])} topics")
        logging.info(f"  Output: {topics_json_path}")

    except ConfigError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)
    except APIError as e:
        logging.error(f"API error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

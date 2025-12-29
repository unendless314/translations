#!/usr/bin/env python3
"""
簡化繁體字幕：批次將 hw zh-TW SRT 內容用 OpenCC 轉為 zh-CN。
- 支援從 config 自動找出 episode，或傳入自訂檔案/目錄。
- 預設會保留原本的文件結構並以 `zh-TW` → `zh-CN` 命名，必要時可指定 output root。
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

try:
    from opencc import OpenCC
except ImportError as exc:  # pragma: no cover - install-time dependency
    raise SystemExit(
        "缺少 OpenCC 套件，請先安裝 opencc-python-reimplemented (pip install opencc-python-reimplemented)"
    ) from exc


SUPPORTED_OPENCC_MODES = {"t2s", "s2t", "t2sp", "s2sp", "tw2s", "s2tw", "tw2sp"}


@dataclass
class BatchSummary:
    processed: int = 0
    converted: int = 0
    unchanged: int = 0
    skipped_existing: int = 0


def load_episode_id_from_config(config_path: Path) -> str:
    """
    從 configs 檔案抓 episode_id。
    """
    if not config_path.exists():
        raise FileNotFoundError(f"找不到配置檔案 {config_path}")

    with config_path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)

    episode_id = config.get("episode_id")
    if not episode_id:
        raise ValueError(f"{config_path} 未指定 episode_id")
    return episode_id


def gather_episode_files(
    episode_id: str,
    input_root: Path,
    pattern: str,
) -> list[Path]:
    """
    找出指定 episode 底下符合 glob pattern 的 SRT。
    """
    target_dir = input_root / episode_id
    if not target_dir.exists():
        raise FileNotFoundError(f"{target_dir} 不存在")

    files = sorted(target_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"{target_dir} 中找不到符合 {pattern} 的檔案")
    return files


def gather_manual_files(patterns: list[str]) -> list[Path]:
    """
    解析用戶輸入的路徑或 glob pattern。
    """
    collected: list[Path] = []
    for raw in patterns:
        path = Path(raw)
        if path.is_file():
            collected.append(path)
            continue

        parent = path.parent if path.parent.exists() else Path(".")
        collected.extend(sorted(parent.glob(path.name)))

    return collected


def build_output_path(
    source: Path, target_tag: str, input_root: Path | None, output_root: Path | None
) -> Path:
    """
    使用 target_tag 對檔名做標記，並決定輸出路徑。
    """
    target_name = source.name.replace("zh-TW", target_tag, 1)
    if target_name == source.name:
        target_name = f"{source.stem}.{target_tag}{source.suffix}"

    parent_dir = source.parent
    if output_root:
        try:
            relative = source.relative_to(input_root) if input_root else Path(source.name)
        except Exception:
            relative = Path(source.name)
        parent_dir = output_root / relative.parent

    return parent_dir / target_name


def convert_file(
    source: Path, destination: Path, converter: OpenCC, dry_run: bool
) -> bool:
    """
    轉換單一檔案並回傳是否有變動。
    """
    text = source.read_text(encoding="utf-8")
    converted = converter.convert(text)

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(converted, encoding="utf-8")

    return text != converted


def main():
    parser = argparse.ArgumentParser(
        description="將 zh-TW SRT 轉為 zh-CN，支援批次處理與 dry-run"
    )
    parser.add_argument(
        "--config",
        help="episode config（如 configs/S01-E01.yaml），會從裡面讀 episode_id 並掃 output/episode",
    )
    parser.add_argument(
        "--episode",
        "-e",
        action="append",
        dest="episodes",
        help="直接指定 episode id，可重複使用（等同於 --config 多個 episode）",
    )
    parser.add_argument(
        "--input-root",
        default="output",
        help="字幕來源根目錄（預設 output）",
    )
    parser.add_argument(
        "--output-root",
        help="指定輸出根目錄，會保留原始相對路徑，預設與原檔同目錄",
    )
    parser.add_argument(
        "--pattern",
        default="*.zh-TW*.srt",
        help="glob pattern，用於篩選需要轉換的檔案（預設 *.zh-TW*.srt）",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        help="直接提供要處理的檔案/pattern（可搭配 glob）",
    )
    parser.add_argument(
        "--mode",
        default="t2s",
        choices=sorted(SUPPORTED_OPENCC_MODES),
        help="OpenCC 模式",
    )
    parser.add_argument(
        "--target-tag",
        default="zh-CN",
        help="用來替換檔名中的 zh-TW 標記，或加在原始檔名後",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只檢查，不寫入檔案",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="若輸出檔已存在則覆寫（預設會跳過）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="輸出詳細訊息",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")

    input_root = Path(args.input_root)
    output_root = Path(args.output_root) if args.output_root else None

    if args.config and args.episodes:
        logging.warning("同時提供 --config 與 --episode，優先使用 config")

    candidates: list[Path] = []

    if args.config:
        config_path = Path(args.config)
        try:
            episode_id = load_episode_id_from_config(config_path)
        except Exception as exc:  # pragma: no cover - user error
            logging.error(exc)
            sys.exit(1)

        try:
            candidates.extend(gather_episode_files(episode_id, input_root, args.pattern))
        except Exception as exc:  # pragma: no cover - user error
            logging.error(exc)
            sys.exit(1)
    elif args.episodes:
        for episode_id in args.episodes:
            try:
                candidates.extend(gather_episode_files(episode_id, input_root, args.pattern))
            except Exception as exc:
                logging.error(exc)
                sys.exit(1)
    elif args.files:
        candidates.extend(gather_manual_files(args.files))
    else:
        parser.error("請提供 --config、--episode 或 --files 至少一項")

    if not candidates:
        logging.error("找不到任何待處理的檔案")
        sys.exit(1)

    converter = OpenCC(args.mode)
    summary = BatchSummary()

    for source in sorted(set(candidates)):
        summary.processed += 1
        destination = build_output_path(source, args.target_tag, input_root, output_root)

        if destination.exists() and not args.overwrite:
            logging.debug(f"跳過已有檔案：{destination}")
            summary.skipped_existing += 1
            continue

        changed = convert_file(source, destination, converter, args.dry_run)
        if changed:
            summary.converted += 1
            logging.info(f"轉換 {source} → {destination}")
        else:
            summary.unchanged += 1
            logging.debug(f"內容無變化：{source}")

    banner = "【dry run】" if args.dry_run else "【實際寫入】"
    logging.info(
        "\n".join(
            [
                "轉換完成",
                f"  模式: {args.mode}",
                f"  目標標記: {args.target_tag}",
                f"  處理檔案: {summary.processed}",
                f"  已轉換: {summary.converted}",
                f"  內容一致: {summary.unchanged}",
                f"  跳過 (已存在): {summary.skipped_existing}",
                f"  {banner}",
            ]
        )
    )


if __name__ == "__main__":
    main()

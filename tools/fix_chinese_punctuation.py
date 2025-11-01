#!/usr/bin/env python3
"""
修正翻譯檔案中 text 欄位內的英文標點為中文標點
- 英文逗號 , → 中文逗號 ，
- 保持 JSON 結構完整（不影響 JSON 語法中的逗號）
"""

import re
import sys
import yaml
from pathlib import Path


def fix_punctuation_in_text_field(line: str) -> str:
    """
    只修正 "text": "..." 欄位內的標點符號
    """
    # 匹配 "text": "內容" 的模式
    pattern = r'"text":\s*"([^"]*)"'

    def replace_comma(match):
        text_content = match.group(1)
        # 將英文逗號替換為中文逗號
        fixed_content = text_content.replace(',', '，')
        return f'"text": "{fixed_content}"'

    # 只替換 text 欄位內的內容
    result = re.sub(pattern, replace_comma, line)
    return result


def process_file(file_path: Path, dry_run: bool = False) -> dict:
    """
    處理單個檔案

    Args:
        file_path: 檔案路徑
        dry_run: 若為 True，只檢查不修改

    Returns:
        統計資訊 dict
    """
    stats = {
        'file': file_path.name,
        'lines_changed': 0,
        'commas_fixed': 0
    }

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        new_line = fix_punctuation_in_text_field(line)
        if new_line != line:
            stats['lines_changed'] += 1
            stats['commas_fixed'] += line.count(',') - new_line.count(',')
        new_lines.append(new_line)

    if not dry_run and stats['lines_changed'] > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='修正翻譯檔案中的中文標點符號'
    )
    parser.add_argument(
        '--config',
        help='Episode 配置檔案（如 configs/S01-E27.yaml），自動處理該 episode 的所有 drafts'
    )
    parser.add_argument(
        'files',
        nargs='*',
        help='要處理的檔案路徑（支援 glob pattern，如 topic_*.md）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只檢查不修改，顯示將會做的改變'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='顯示詳細資訊'
    )

    args = parser.parse_args()

    # 收集所有檔案
    files_to_process = []

    if args.config:
        # 從配置檔讀取 episode_id
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"錯誤：找不到配置檔案 {args.config}")
            sys.exit(1)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        episode_id = config.get('episode_id')
        if not episode_id:
            print(f"錯誤：配置檔案中未找到 episode_id")
            sys.exit(1)

        # 自動定位到 drafts 目錄
        drafts_dir = Path('data') / episode_id / 'drafts'
        if not drafts_dir.exists():
            print(f"錯誤：找不到目錄 {drafts_dir}")
            sys.exit(1)

        # 收集所有 topic_*.md 檔案
        files_to_process = sorted(drafts_dir.glob('topic_*.md'))

        if not files_to_process:
            print(f"錯誤：在 {drafts_dir} 中找不到 topic_*.md 檔案")
            sys.exit(1)

    elif args.files:
        # 手動指定檔案模式
        for pattern in args.files:
            path = Path(pattern)
            if path.is_file():
                files_to_process.append(path)
            else:
                # 支援 glob pattern
                parent = path.parent if path.parent.exists() else Path('.')
                files_to_process.extend(parent.glob(path.name))

    else:
        print("錯誤：請提供 --config 參數或指定要處理的檔案")
        parser.print_help()
        sys.exit(1)

    if not files_to_process:
        print("錯誤：找不到符合的檔案")
        sys.exit(1)

    # 處理檔案
    total_stats = {
        'files_processed': 0,
        'files_changed': 0,
        'total_lines_changed': 0,
        'total_commas_fixed': 0
    }

    print(f"{'[DRY RUN] ' if args.dry_run else ''}開始處理 {len(files_to_process)} 個檔案...\n")

    for file_path in sorted(files_to_process):
        stats = process_file(file_path, dry_run=args.dry_run)
        total_stats['files_processed'] += 1

        if stats['lines_changed'] > 0:
            total_stats['files_changed'] += 1
            total_stats['total_lines_changed'] += stats['lines_changed']
            total_stats['total_commas_fixed'] += stats['commas_fixed']

            status = '(將修改)' if args.dry_run else '(已修改)'
            print(f"✓ {stats['file']:<20} {status}")
            if args.verbose:
                print(f"  - 修改行數: {stats['lines_changed']}")
                print(f"  - 修正逗號: {stats['commas_fixed']}")
        elif args.verbose:
            print(f"○ {stats['file']:<20} (無需修改)")

    # 顯示總結
    print(f"\n{'=' * 50}")
    print(f"總結：")
    print(f"  處理檔案數: {total_stats['files_processed']}")
    print(f"  {'將修改' if args.dry_run else '已修改'}檔案數: {total_stats['files_changed']}")
    print(f"  {'將修改' if args.dry_run else '已修改'}行數: {total_stats['total_lines_changed']}")
    print(f"  {'將修正' if args.dry_run else '已修正'}逗號數: {total_stats['total_commas_fixed']}")

    if args.dry_run and total_stats['files_changed'] > 0:
        print(f"\n提示：使用不加 --dry-run 參數來實際執行修改")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
驗證 terminology.yaml 中的 segment 標記是否準確

驗證方式：
1. 與 terminology_candidates.yaml 比對（快速）
2. 直接檢查 main.yaml 中的 segment 內容（準確）
"""

import yaml
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict

def load_yaml(file_path: Path) -> dict:
    """載入 YAML 文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_terminology_segments(terminology_yaml: dict) -> Dict[str, Set[int]]:
    """從 terminology.yaml 提取術語及其 segments"""
    term_segments = {}

    for term_entry in terminology_yaml.get('terms', []):
        term = term_entry['term']
        segments = set()

        for sense in term_entry.get('senses', []):
            segments.update(sense.get('segments', []))

        term_segments[term] = segments

    return term_segments

def get_candidates_segments(candidates_yaml: dict) -> Dict[str, Set[int]]:
    """從 terminology_candidates.yaml 提取術語及其 segments"""
    term_segments = {}

    for term_entry in candidates_yaml.get('terms', []):
        term = term_entry['term']
        segments = set()

        for occurrence in term_entry.get('occurrences', []):
            segments.add(occurrence['segment_id'])

        term_segments[term] = segments

    return term_segments

def compare_with_candidates(
    terminology_segments: Dict[str, Set[int]],
    candidates_segments: Dict[str, Set[int]]
) -> Tuple[List[str], Dict[str, List[int]], Dict[str, List[int]]]:
    """
    比對 terminology.yaml 和 candidates.yaml

    Returns:
        missing_terms: 在 candidates 中有但 terminology 中缺失的術語
        invalid_segments: 在 terminology 中標記但 candidates 中不存在的 segments
        missing_segments: 在 candidates 中有但 terminology 中遺漏的 segments
    """
    missing_terms = []
    invalid_segments = defaultdict(list)
    missing_segments = defaultdict(list)

    # 檢查 terminology 中的術語
    for term, segments in terminology_segments.items():
        if term not in candidates_segments:
            # 術語在 candidates 中不存在（可能是手動添加的）
            continue

        candidate_segs = candidates_segments[term]

        # 檢查無效的 segments（terminology 有但 candidates 沒有）
        invalid = segments - candidate_segs
        if invalid:
            invalid_segments[term] = sorted(invalid)

        # 檢查遺漏的 segments（candidates 有但 terminology 沒有）
        missing = candidate_segs - segments
        if missing:
            missing_segments[term] = sorted(missing)

    # 檢查 candidates 中有但 terminology 中完全缺失的術語
    for term in candidates_segments:
        if term not in terminology_segments:
            missing_terms.append(term)

    return missing_terms, invalid_segments, missing_segments

def verify_against_main_yaml(
    terminology_segments: Dict[str, Set[int]],
    main_yaml_path: Path,
    case_sensitive: bool = False
) -> Dict[str, List[Tuple[int, bool]]]:
    """
    直接驗證 main.yaml 中的 segments 是否包含標記的術語

    Returns:
        verification_results: {term: [(segment_id, found), ...]}
    """
    main_data = load_yaml(main_yaml_path)
    segments_dict = {}

    # 建立 segment_id -> source_text 的映射
    for segment in main_data.get('segments', []):
        seg_id = segment.get('segment_id')
        source_text = segment.get('source_text', '')
        if seg_id:
            segments_dict[seg_id] = source_text

    verification_results = {}

    for term, segment_ids in terminology_segments.items():
        results = []

        for seg_id in sorted(segment_ids):
            if seg_id not in segments_dict:
                results.append((seg_id, False))  # segment 不存在
                continue

            source_text = segments_dict[seg_id]

            # 檢查術語是否在 source_text 中
            if case_sensitive:
                found = term in source_text
            else:
                found = term.lower() in source_text.lower()

            results.append((seg_id, found))

        verification_results[term] = results

    return verification_results

def print_report(
    missing_terms: List[str],
    invalid_segments: Dict[str, List[int]],
    missing_segments: Dict[str, List[int]],
    verification_results: Dict[str, List[Tuple[int, bool]]] = None
):
    """輸出驗證報告"""

    print("=" * 80)
    print("TERMINOLOGY.YAML 驗證報告")
    print("=" * 80)
    print()

    # 1. 與 candidates 比對結果
    print("【一】與 terminology_candidates.yaml 比對")
    print("-" * 80)

    if missing_terms:
        print(f"\n⚠️  在 candidates 中有但 terminology 中缺失的術語 ({len(missing_terms)} 個):")
        for term in sorted(missing_terms):
            print(f"  - {term}")
    else:
        print("\n✅ 無缺失術語")

    if invalid_segments:
        print(f"\n❌ 標記了不存在於 candidates 的 segments ({len(invalid_segments)} 個術語):")
        for term, segs in sorted(invalid_segments.items()):
            print(f"  - {term}: {segs}")
    else:
        print("\n✅ 無無效 segments")

    if missing_segments:
        print(f"\n⚠️  在 candidates 中有但未標記的 segments ({len(missing_segments)} 個術語):")
        for term, segs in sorted(missing_segments.items()):
            if len(segs) <= 5:
                print(f"  - {term}: {segs}")
            else:
                print(f"  - {term}: {segs[:5]} ... (共 {len(segs)} 個)")
    else:
        print("\n✅ 無遺漏 segments")

    # 2. 直接驗證 main.yaml
    if verification_results:
        print("\n【二】直接驗證 main.yaml")
        print("-" * 80)

        not_found_count = 0
        problematic_terms = []

        for term, results in sorted(verification_results.items()):
            not_found = [(seg_id, found) for seg_id, found in results if not found]

            if not_found:
                not_found_count += len(not_found)
                problematic_terms.append((term, not_found))

        if problematic_terms:
            print(f"\n❌ 發現 {not_found_count} 個標記錯誤（術語未在指定 segment 中出現）:")
            for term, not_found in problematic_terms[:10]:  # 只顯示前 10 個
                seg_ids = [seg_id for seg_id, _ in not_found]
                if len(seg_ids) <= 3:
                    print(f"  - {term}: segments {seg_ids}")
                else:
                    print(f"  - {term}: segments {seg_ids[:3]} ... (共 {len(seg_ids)} 個)")

            if len(problematic_terms) > 10:
                print(f"  ... (還有 {len(problematic_terms) - 10} 個術語有問題)")
        else:
            print("\n✅ 所有標記的 segments 都包含對應術語！")

    print("\n" + "=" * 80)
    print("驗證完成")
    print("=" * 80)

def main():
    parser = argparse.ArgumentParser(description='驗證 terminology.yaml 的正確性')
    parser.add_argument('--config', help='配置文件路徑 (configs/<episode>.yaml)')
    parser.add_argument('--episode', help='Episode ID (e.g., S01-E31)')
    parser.add_argument('--terminology', help='terminology.yaml 路徑')
    parser.add_argument('--candidates', help='terminology_candidates.yaml 路徑')
    parser.add_argument('--main-yaml', help='main.yaml 路徑')
    parser.add_argument('--skip-main-check', action='store_true',
                       help='跳過 main.yaml 的直接驗證（只與 candidates 比對）')
    parser.add_argument('--case-sensitive', action='store_true',
                       help='區分大小寫（默認不區分）')
    parser.add_argument('--verbose', action='store_true', help='顯示詳細信息')

    args = parser.parse_args()

    # 確定文件路徑
    if args.config:
        config = load_yaml(Path(args.config))
        episode_id = config.get('episode_id')
    elif args.episode:
        episode_id = args.episode
    else:
        print("錯誤：請提供 --config 或 --episode")
        sys.exit(1)

    terminology_path = Path(args.terminology) if args.terminology else Path(f"data/{episode_id}/terminology.yaml")
    candidates_path = Path(args.candidates) if args.candidates else Path(f"data/{episode_id}/terminology_candidates.yaml")
    main_yaml_path = Path(args.main_yaml) if args.main_yaml else Path(f"data/{episode_id}/main.yaml")

    # 檢查文件是否存在
    if not terminology_path.exists():
        print(f"錯誤：找不到 terminology.yaml: {terminology_path}")
        sys.exit(1)

    if not candidates_path.exists():
        print(f"錯誤：找不到 terminology_candidates.yaml: {candidates_path}")
        sys.exit(1)

    # 載入數據
    print(f"載入 {terminology_path} ...")
    terminology_data = load_yaml(terminology_path)
    terminology_segments = get_terminology_segments(terminology_data)

    print(f"載入 {candidates_path} ...")
    candidates_data = load_yaml(candidates_path)
    candidates_segments = get_candidates_segments(candidates_data)

    print(f"比對中...")
    missing_terms, invalid_segments, missing_segments = compare_with_candidates(
        terminology_segments, candidates_segments
    )

    # 直接驗證 main.yaml
    verification_results = None
    if not args.skip_main_check and main_yaml_path.exists():
        print(f"驗證 {main_yaml_path} ...")
        verification_results = verify_against_main_yaml(
            terminology_segments, main_yaml_path, args.case_sensitive
        )

    # 輸出報告
    print_report(missing_terms, invalid_segments, missing_segments, verification_results)

if __name__ == '__main__':
    main()

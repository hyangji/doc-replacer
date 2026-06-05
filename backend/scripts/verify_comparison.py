"""엑셀 대비표 파싱 + HWP 매칭 검증 스크립트.

실행: cd backend && python -X utf8 scripts/verify_comparison.py
"""

import sys
import os

# backend 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.excel_service import parse_comparison_table_excel
from app.services.hwp_service import HwpService

EXCEL_PATH = "C:/Users/rkdgi/OneDrive/바탕 화면/고시문 샘플.xlsx"
HWP_PATH = "C:/Users/rkdgi/OneDrive/바탕 화면/고시문 샘플.hwp"


def main():
    # 1. 엑셀 파싱
    print("=" * 70)
    print("1. 엑셀 대비표 파싱")
    print("=" * 70)
    with open(EXCEL_PATH, "rb") as f:
        excel_bytes = f.read()

    items = parse_comparison_table_excel(excel_bytes)
    print(f"총 추출된 교체쌍: {len(items)}건")

    # 시트별 출력
    sheets_seen: dict[str, list] = {}
    for it in items:
        sheets_seen.setdefault(it["sheet"], []).append(it)

    for sheet_name, sheet_items in sheets_seen.items():
        print(f"\n  [시트] {sheet_name!r} ({len(sheet_items)}건)")
        for it in sheet_items:
            print(f"    {it['field_name']!r}: {it['old_value']!r} -> {it['new_value']!r}")

    # 2. HWP 텍스트 로드
    print("\n" + "=" * 70)
    print("2. HWP 텍스트 로드 + 매칭 수 확인")
    print("=" * 70)
    with open(HWP_PATH, "rb") as f:
        hwp_bytes = f.read()

    hwp_svc = HwpService()
    import asyncio
    hwp_text = asyncio.run(hwp_svc.get_text_content(hwp_bytes, "hwp"))
    print(f"HWP 텍스트 길이: {len(hwp_text)}자")

    # 3. 매칭 수 계산
    print("\n" + "=" * 70)
    print("3. 항목별 old_value HWP 매칭 수 (오교체 위험 탐지)")
    print("=" * 70)

    risk_items = []
    zero_items = []
    ok_items = []

    for it in items:
        old_val = it["old_value"]
        count = hwp_text.count(old_val)
        it["match_count"] = count

        if count == 0:
            zero_items.append(it)
        elif count > 1:
            risk_items.append(it)
        else:
            ok_items.append(it)

    print(f"\n  [정상 (match=1)] {len(ok_items)}건")
    for it in ok_items:
        print(f"    {it['old_value']!r} -> {it['new_value']!r}  ({it['sheet']})")

    if risk_items:
        print(f"\n  [오교체 위험 (match>1)] {len(risk_items)}건 *** 주의 ***")
        for it in risk_items:
            print(f"    match={it['match_count']}  {it['old_value']!r} -> {it['new_value']!r}  ({it['sheet']})")

    if zero_items:
        print(f"\n  [미매칭 (match=0)] {len(zero_items)}건")
        for it in zero_items:
            print(f"    {it['old_value']!r} -> {it['new_value']!r}  ({it['sheet']})")

    # 4. 8.나 시트 특정 교체쌍 검증
    print("\n" + "=" * 70)
    print("4. 8.나 토지이용계획 시트 교체쌍 검증")
    print("=" * 70)
    expected_pairs = [
        ("267,309", "266,717"),
        ("184,636", "184,110"),
        ("77,335", "77,269"),
        ("24,151", "23,730"),
        ("40,173", "40,532"),
    ]
    sheet_8na = sheets_seen.get("8. 나. 토지이용계획 (변경)", [])
    extracted_pairs = {(it["old_value"], it["new_value"]) for it in sheet_8na}

    for old, new in expected_pairs:
        found = (old, new) in extracted_pairs
        match = hwp_text.count(old)
        status = "OK" if found else "MISS"
        print(f"  [{status}] {old!r} -> {new!r}  (HWP 매칭: {match}건)")

    # 5. 실제 교체 테스트 (안전하게 1건만, 원본 파일 건드리지 않음)
    print("\n" + "=" * 70)
    print("5. 실제 replace_text 테스트 (인메모리, 원본 불변)")
    print("=" * 70)
    # 8.나 시트에서 match_count==1인 첫 번째 항목
    safe_item = next(
        (it for it in sheet_8na if it.get("match_count") == 1),
        None
    )
    if safe_item:
        old_v = safe_item["old_value"]
        new_v = safe_item["new_value"]
        print(f"  테스트 항목: {old_v!r} -> {new_v!r}")
        new_data, cnt = hwp_svc.replace_text(hwp_bytes, old_v, new_v, file_type="hwp")
        print(f"  교체 결과: {cnt}건 교체됨")
        # 교체된 텍스트에서 확인
        new_text = asyncio.run(hwp_svc.get_text_content(new_data, "hwp"))
        in_old = old_v in new_text
        in_new = new_v in new_text
        print(f"  old_value 잔존: {in_old}  new_value 등장: {in_new}")
        if not in_old and in_new:
            print("  => 교체 성공!")
        else:
            print("  => 교체 이상 (확인 필요)")
    else:
        print("  안전한 테스트 항목 없음 (match_count==1인 항목 없음)")

    print("\n검증 완료.")


if __name__ == "__main__":
    main()

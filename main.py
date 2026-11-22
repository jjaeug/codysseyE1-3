"""Mini NPU Simulator - MAC 연산 기반 패턴 판별기 (표준 라이브러리만 사용)"""
import json
import os
import re
import time
import traceback

EPSILON = 1e-9
REPEAT = 10
DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")

# 라벨 정규화: 다양한 표기 -> 표준 라벨(Cross / X)
LABEL_MAP = {"+": "Cross", "cross": "Cross", "x": "X"}


def normalize_label(raw):
    return LABEL_MAP.get(str(raw).strip().lower())


# ---------------- 핵심 연산 ----------------
def mac(pattern, filt):
    """위치별 곱셈 후 누적 합 (반복문 직접 구현)"""
    total = 0.0
    n = len(pattern)
    for i in range(n):
        p_row, f_row = pattern[i], filt[i]
        for j in range(n):
            total += p_row[j] * f_row[j]
    return total


def judge(score_a, score_b, label_a, label_b):
    """epsilon 기반 비교: 차이가 EPSILON 미만이면 동점(UNDECIDED)"""
    if abs(score_a - score_b) < EPSILON:
        return "UNDECIDED"
    return label_a if score_a > score_b else label_b


def measure_ms(pattern, filt, repeat=REPEAT):
    """MAC 함수 호출 구간만 repeat회 측정한 평균(ms)"""
    start = time.perf_counter()
    for _ in range(repeat):
        mac(pattern, filt)
    return (time.perf_counter() - start) * 1000 / repeat


def is_square(m, n):
    return isinstance(m, list) and len(m) == n and all(
        isinstance(r, list) and len(r) == n for r in m)


# 모드 2 성능 분석의 3×3 측정용 기본 패턴 (미션 예시의 십자가 / X)
CROSS_3 = [[0.0, 1.0, 0.0], [1.0, 1.0, 1.0], [0.0, 1.0, 0.0]]
X_3 = [[1.0, 0.0, 1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 1.0]]


# ---------------- 출력 도우미 ----------------
def section(title):
    print("\n#" + "-" * 40)
    print("# " + title)
    print("#" + "-" * 40)


def print_perf_table(samples):
    """samples: {N: (패턴, 필터)}"""
    print(f"{'크기':<10}{'평균 시간(ms)':>14}{'연산 횟수(N²)':>16}")
    print("-" * 42)
    for n in sorted(samples):
        ms = measure_ms(*samples[n])
        print(f"{f'{n}×{n}':<10}{ms:>14.4f}{n * n:>16}")


# ---------------- 모드 1: 사용자 입력 ----------------
def read_matrix(name, n=3):
    while True:
        print(f"{name} ({n}줄 입력, 공백 구분)")
        rows = []
        try:
            for _ in range(n):
                row = [float(v) for v in input().split()]
                if len(row) != n:
                    raise ValueError
                rows.append(row)
            return rows
        except ValueError:
            print(f"입력 형식 오류: 각 줄에 {n}개의 숫자를 공백으로 구분해 입력하세요.\n")


def mode_user():
    section("[1] 필터 입력")
    fa = read_matrix("필터 A")
    fb = read_matrix("필터 B")
    print("[OK] 필터 A, B 저장 완료")

    section("[2] 패턴 입력")
    pat = read_matrix("패턴")

    section("[3] MAC 결과")
    sa, sb = mac(pat, fa), mac(pat, fb)
    ms = (measure_ms(pat, fa) + measure_ms(pat, fb)) / 2
    result = judge(sa, sb, "A", "B")
    print(f"A 점수: {sa}")
    print(f"B 점수: {sb}")
    print(f"연산 시간(평균/{REPEAT}회): {ms:.4f} ms")
    print("판정: " + ("판정 불가 (|A-B| < 1e-9)" if result == "UNDECIDED" else result))

    section(f"[4] 성능 분석 (평균/{REPEAT}회)")
    print_perf_table({3: (pat, fa)})


# ---------------- 모드 2: data.json 분석 ----------------
def load_filters(raw):
    """{'size_5': {'Cross': [...], 'X': [...]}, ...} 형태로 정규화"""
    filters = {}
    for key, pair in raw.items():
        try:
            n = int(key.split("_")[1])
            norm = {normalize_label(k): v for k, v in pair.items()}
            if not all(is_square(norm.get(lb), n) for lb in ("Cross", "X")):
                raise ValueError("Cross/X 필터 누락 또는 크기 불일치")
            filters[n] = norm
            print(f"[OK] {key:<8} 필터 로드 완료 (Cross, X)")
        except (IndexError, ValueError, AttributeError) as e:
            print(f"[FAIL] {key} 필터 로드 실패: {e}")
    return filters


def analyze_case(key, case, filters):
    """(판정, expected, 실패사유 or None) 반환. 어떤 오류도 예외로 터지지 않음."""
    m = re.fullmatch(r"size_(\d+)_\d+", key)
    if not m:
        return None, None, "키 형식 오류(size_N_idx 아님)"
    n = int(m.group(1))
    if n not in filters:
        return None, None, f"size_{n} 필터 없음"
    expected = normalize_label(case.get("expected"))
    if expected is None:
        return None, None, f"알 수 없는 expected 라벨: {case.get('expected')!r}"
    pat = case.get("input")
    if not is_square(pat, n):
        return None, expected, f"패턴 크기 불일치(필터 {n}×{n})"

    sc, sx = mac(pat, filters[n]["Cross"]), mac(pat, filters[n]["X"])
    result = judge(sc, sx, "Cross", "X")
    print(f"Cross 점수: {sc}")
    print(f"X 점수: {sx}")
    if result == "UNDECIDED":
        reason = f"동점(UNDECIDED) 처리 규칙에 따라 FAIL (|차이|={abs(sc - sx):.2e})"
    elif result != expected:
        reason = f"판정 {result} ≠ expected {expected}"
    else:
        reason = None
    return result, expected, reason


def mode_json():
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"data.json 로드 실패: {e}")
        return

    section("[1] 필터 로드")
    filters = load_filters(data.get("filters", {}))

    section("[2] 패턴 분석 (라벨 정규화 적용)")
    failures, total = [], 0
    for key, case in data.get("patterns", {}).items():
        total += 1
        print(f"--- {key} ---")
        try:
            result, expected, reason = analyze_case(key, case, filters)
        except (TypeError, AttributeError) as e:  # 숫자 아닌 값, 잘못된 구조 등
            result, expected, reason = None, None, f"데이터 형식 오류: {e}"
        status = "PASS" if reason is None else "FAIL"
        print(f"판정: {result or '-'} | expected: {expected or '-'} | {status}")
        if reason:
            failures.append((key, reason))

    section(f"[3] 성능 분석 (평균/{REPEAT}회)")
    samples = {n: (f["Cross"], f["X"]) for n, f in filters.items()}
    samples[3] = (CROSS_3, X_3)
    print_perf_table(samples)

    section("[4] 결과 요약")
    print(f"총 테스트: {total}개")
    print(f"통과: {total - len(failures)}개")
    print(f"실패: {len(failures)}개")
    if failures:
        print("\n실패 케이스:")
        for key, reason in failures:
            print(f"- {key}: {reason}")
    print('\n(상세 원인 분석 및 복잡도 설명은 README.md의 "결과 리포트" 섹션 참고)')


def main():
    print("=== Mini NPU Simulator ===\n")
    print("[모드 선택]")
    print("1. 사용자 입력 (3x3)")
    print("2. data.json 분석")
    while True:
        choice = input("선택: ").strip()
        if choice in ("1", "2"):
            break
        print("1 또는 2를 입력하세요.")
    mode_user() if choice == "1" else mode_json()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n종료합니다.")
    except Exception:
        traceback.print_exc()
    # 더블클릭 실행 시 창이 바로 닫히지 않도록 대기
    try:
        input("\n엔터를 누르면 종료합니다...")
    except EOFError:
        pass

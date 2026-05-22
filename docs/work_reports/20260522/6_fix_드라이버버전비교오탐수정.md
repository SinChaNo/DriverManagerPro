# 드라이버 버전 비교 오탐 수정

- 날짜: 2026-05-22
- 작업 유형: fix
- 작업자: Claude

## 문제

최신 드라이버임에도 UI에 "업데이트 필요"가 표시되는 오탐 2건 발생:

- NVIDIA GeForce: `32.0.15.7283 → 572.83` (실제로는 동일 버전)
- Intel 기기 다수: `10.0.26100.7705 → 31.0.101.5592`, `10.1.46.5 → 31.0.101.5592` (Intel 칩셋/ME 등이 Intel Graphics에 오매칭)

## 원인 분석

### 버그 1: NVIDIA 버전 형식 불일치

WMI는 NVIDIA 드라이버 버전을 Windows 4-part 형식으로 반환하고,
manifest는 NVIDIA 고유 2-part 형식으로 저장한다.

| 형식 | 예시 |
|---|---|
| WMI (Windows 4-part) | `32.0.15.7283` |
| Manifest (NVIDIA 2-part) | `572.83` |

`_parse_version` 튜플 비교 시 `(572, 83, 0, 0) > (32, 0, 15, 7283)` → 572 > 32 → True로 판정되어 오탐 발생.

실제 변환 공식:
```
parts = "32.0.15.7283".split(".")  # [32, 0, 15, 7283]
major = (parts[2] % 10) * 100 + parts[3] // 100  # 5*100 + 72 = 572
minor = parts[3] % 100                             # 83
→ "572.83"
```

### 버그 2: Intel 기기 과다 매칭

퍼지 매칭 키워드 목록에 `"intel"` 포함:

```python
for kw in ["geforce", "radeon", "intel", "realtek", ...]:
```

- 드라이버명 "Intel Graphics Driver" → `"intel"` 포함 ✓
- 기기명 "Intel Management Engine" → `"intel"` 포함 ✓
- → Intel 칩셋, ME, WiFi 등 모든 Intel 기기가 Intel Graphics 드라이버에 매칭됨

## 수정 내용

**파일:** `core/driver_compare.py`

### 1. NVIDIA 버전 변환 함수 추가

```python
def _nvidia_win_to_nvidia_ver(win_ver: str) -> Optional[str]:
    parts = win_ver.split(".")
    if len(parts) != 4:
        return None
    p2, p3 = int(parts[2]), int(parts[3])
    major = (p2 % 10) * 100 + p3 // 100
    minor = p3 % 100
    return f"{major}.{minor:02d}"
```

### 2. 버전 정규화 함수 추가

```python
def _normalize_installed_version(installed_ver, latest_ver, vendor) -> str:
    # NVIDIA만 적용: manifest 2-part, installed 4-part인 경우 변환
    if vendor.lower() == "nvidia":
        if len(latest_ver.split(".")) == 2 and len(installed_ver.split(".")) == 4:
            converted = _nvidia_win_to_nvidia_ver(installed_ver)
            if converted:
                return converted
    return installed_ver
```

`compare_device_to_manifest()`에서 비교 전 정규화 적용 및 UI 표시 버전도 정규화된 값 사용.

### 3. VEN-only HWID 매칭 추가

NVIDIA manifest의 `"PCI\\VEN_10DE"` (DEV 없음) 형식 지원:

```python
# DEV 없는 VEN-only HWID인 경우 벤더 전체 매칭
ven_only = re.search(r"VEN_([0-9A-Fa-f]{4})", hwid)
if ven_only and "&" not in hwid:
    ven = ven_only.group(1).upper()
    for d_hwid in device_upper:
        if f"VEN_{ven}" in d_hwid:
            return True
```

### 4. 퍼지 매칭 키워드에서 `"intel"` 제거

```python
# 수정 전
for kw in ["geforce", "radeon", "intel", "realtek", "bluetooth", ...]:

# 수정 후 ("intel" 제거)
for kw in ["geforce", "radeon", "realtek", "bluetooth", ...]:
```

Intel 기기는 DEV-specific 하드웨어 ID 매칭으로 처리한다.

## 검증

단위 테스트 결과:

| 테스트 | 결과 |
|---|---|
| `32.0.15.7283` → `572.83` 변환 | 통과 |
| `32.0.15.6636` → `566.36` 변환 | 통과 |
| `572.83` vs `572.83` 비교 → 업데이트 불필요 | 통과 |
| VEN-only HWID 매칭 (`PCI\VEN_10DE`) | 통과 |
| 다른 벤더 격리 (오매칭 방지) | 통과 |

## 결과

- NVIDIA 최신 드라이버 오탐 수정
- Intel 기기 과다 매칭 수정
- 포터블 EXE 재빌드 완료

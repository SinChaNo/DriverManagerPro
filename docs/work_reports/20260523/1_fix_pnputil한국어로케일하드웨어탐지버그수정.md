# 작업 보고서: pnputil 한국어 로케일 하드웨어 탐지 버그 수정

- 날짜: 2026-05-23
- 유형: fix
- 영향 파일: `core/hardware_detect.py`

## 문제 상황

앱 실행 시 하드웨어가 탐지되지 않는 버그 발생.

```
Hardware scan complete - 0 devices found
```

## 원인 분석

### 원인 1: wmi Python 모듈 미설치

`wmi` 모듈이 설치되어 있지 않아 pnputil fallback 경로로 진입.

### 원인 2: pnputil 한국어 로케일 필드명 불일치

`subprocess.run`에 `CREATE_NO_WINDOW` 플래그 사용 시 pnputil이 시스템 OEM 코드페이지(CP949)를 사용하여 **한국어 필드명**으로 출력.

| 예상 키 (영어) | 실제 출력 키 (한국어) |
|---|---|
| `Published Name` | `게시된 이름` |
| `Original Name` | `원래 이름` |
| `Class Name` | `클래스 이름` |
| `Driver Version` | `드라이버 버전` |
| `Provider Name` | `공급자 이름` |

키 매핑 실패로 모든 장치가 `device_name="Unknown"`, `device_class=""`, `driver_version="0.0.0.0"` 으로 파싱됨.

### 원인 3: scan_hardware 필터에서 전체 제거

```python
# device_class=""이고 driver_version="0.0.0.0"인 장치 전부 제거됨
meaningful = [d for d in devices if d.device_class not in ("", "Unknown") or d.driver_version != "0.0.0.0"]
```

### 원인 4: Driver Version 날짜 형식 파싱 오류

pnputil의 Driver Version 필드 형식: `MM/DD/YYYY VersionNumber` (예: `10/31/2023 1.0.9597.1`)

기존 `_parse_version`은 첫 번째 토큰(`10/31/2023`)을 버전으로 반환. 이 값은 `0.0.0.0`이 아니므로 필터는 통과했지만, 버전 비교에서 잘못된 결과 발생.

## 수정 내용

### 1. pnputil 명령 변경: `/enum-drivers` → `/enum-devices /ids` + `/enum-drivers`

기존 `/enum-drivers`는 INF 파일명만 제공하고 실제 장치명·Hardware ID가 없었음.

- `/enum-devices /ids`: 실제 장치명(`Device Description`), Hardware ID, 클래스, 제조사
- `/enum-drivers`: oem#.inf 별 버전 정보
- 두 결과를 `Driver Name` (oem#.inf) 기준으로 조인

### 2. 영어/한국어 로케일 이중 매핑 테이블 추가

```python
_PNPUTIL_DRIVERS_KEY_MAP   # /enum-drivers 필드명 정규화
_PNPUTIL_DEVICES_KEY_MAP   # /enum-devices /ids 필드명 정규화
```

### 3. `_parse_pnputil_version` 함수 추가

```python
def _parse_pnputil_version(raw: str) -> str:
    # "10/31/2023 1.0.9597.1" → "1.0.9597.1"
    for token in raw.strip().split():
        if re.match(r"^\d[\d.]*$", token):
            return token
    return "0.0.0.0"
```

### 4. `_build_pnputil_version_map` 함수 추가

`/enum-drivers` 결과를 `{oem26.inf: "1.0.9597.1"}` 형태의 딕셔너리로 변환.

### 5. `_detect_via_pnputil` 완전 재작성

- `/enum-devices /ids` 파싱 (다중 줄 Hardware IDs 지원)
- 들여쓰기 기반 Hardware IDs 연속 라인 처리
- 버전 맵과 조인하여 `DeviceInfo` 생성

## 수정 결과

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| 탐지 장치 수 | 0 | 274 |
| 실제 장치명 | Unknown (INF 파일명) | NVIDIA High Definition Audio 등 |
| Hardware ID | 없음 | HDAUDIO\FUNC_01&VEN_10DE&... |
| 드라이버 버전 | 0.0.0.0 | 1.4.5.7 등 실제 버전 |
| HWID 있는 장치 | 0 | 263 |

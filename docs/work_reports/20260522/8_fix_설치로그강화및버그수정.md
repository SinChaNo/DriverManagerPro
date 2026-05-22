# 드라이버 설치 로그 수집 강화 및 버그 수정

- 날짜: 2026-05-22
- 작업 유형: fix
- 작업자: Claude

## 문제

드라이버 업데이트 실행 시 버그가 발생하나, 로그 정보 부족으로 원인 파악 불가.

## 로그 수집 개선 (logger.py)

### 1. 세션별 독립 로그 파일

```
# 수정 전 — 날짜만 (하루에 여러 세션이 덮어쓰임)
install_20260522.log

# 수정 후 — 날짜+시간 (세션마다 고유 파일)
install_20260522_143512.log
```

### 2. 버퍼 2배 확대

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| 메모리 버퍼 | 500줄 | 2000줄 |
| 파일 로그 레벨 | INFO | DEBUG (전체 기록) |

### 3. 세션 구분선 함수 추가

`log_session_start(label)` / `log_session_end(label, success_count, total)` 로 설치 세션의 시작·종료를 구분선으로 표시한다.

```
================================================================
  SESSION START: 드라이버 설치 2건: NVIDIA GeForce ..., Realtek HD ...
  2026-05-22 14:35:12
================================================================
...
----------------------------------------------------------------
  SESSION END: 드라이버 설치  (1/2 성공)
----------------------------------------------------------------
```

### 4. ERROR 레벨 예외 자동 첨부 (`_ExcInfoErrorFilter`)

`logger.error("msg")` 호출 시 현재 활성 예외가 있으면 스택 트레이스를 자동으로 로그에 첨부한다.

## 버그 수정 (driver_install.py)

### 버그 1: _download_driver() Referer 누락 (403 위험)

```python
# 수정 전 — 헤더 없음
resp = requests.get(url, stream=True, timeout=600)

# 수정 후 — 도메인별 Referer 자동 적용
headers = _build_request_headers(url)
resp = requests.get(url, stream=True, timeout=600, headers=headers)
```

`_REFERER_MAP`, `_USER_AGENT`, `_build_request_headers()` 를 driver_install.py에 추가하여 downloader.py와 동일한 403 방지 정책 적용.

### 버그 2: 벤더별 사일런트 플래그 일괄 적용

```python
# 수정 전 — 모든 벤더에 동일 플래그
silent_flags = ["/s", "/silent", "/quiet", "/norestart"]

# 수정 후 — 벤더별 분기
_VENDOR_SILENT_FLAGS = {
    "nvidia":  ["-s", "-noeula", "-noreboot"],
    "amd":     ["--silent", "--noreboot"],
    "intel":   ["-s", "-norestart", "-q"],
    "realtek": ["/s"],
}
```

### 버그 3: EXE 설치 타임아웃 부족

```python
# 수정 전
timeout=300  # 5분 — NVIDIA 700MB 설치 시 시간 초과

# 수정 후
timeout=600  # 10분
```

## 로그 강화 항목 (driver_install.py)

| 위치 | 추가된 로그 |
|---|---|
| `install_driver()` 시작 | `driver_info` 전체 내용 DEBUG 기록 (id, name, vendor, path, inf, url) |
| `_run_pnputil()` | stdout/stderr 전문 DEBUG 기록, exit code DEBUG 기록 |
| `_run_vendor_exe()` | stdout/stderr 전문 DEBUG 기록, exit code DEBUG 기록 |
| `_download_driver()` | 적용된 Referer 헤더 DEBUG 기록 |
| `run_install_queue()` | 세션 시작/종료 구분선 + 각 드라이버 설치 번호 구분선 |
| 예외 처리 전반 | `exc_info=True` 추가로 스택 트레이스 기록 |

## 변경 파일

- `core/logger.py`: 세션 로그 파일, 버퍼 확대, 구분선 함수, ExcInfoFilter
- `core/driver_install.py`: Referer 헤더, 벤더 플래그, 타임아웃, 로그 강화

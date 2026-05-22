# 작업 보고서 — 드라이버 설치 경로 버그 수정 및 자동 다운로드 기능

- 날짜: 2026-05-22
- 유형: fix
- 커밋: 86f3744

---

## 문제 원인 분석

### 경로 버그

`install_driver()` 에서 드라이버 경로를 조합할 때 `download_path` 프리픽스가 누락되었다.

```
# manifest path 예시
"path": "nvidia/geforce/desktop/v572.83"

# install_driver()의 실제 조합 결과 (버그)
DriverManagerPro / nvidia/geforce/desktop/v572.83

# 올바른 경로 (수정 후)
DriverManagerPro / drivers / nvidia/geforce/desktop/v572.83
```

### 드라이버 파일 미존재

`drivers/` 폴더 내 `.exe` 파일들은 플레이스홀더(0바이트)이며 실제 인스톨러가 아니다.
"DB 업데이트" 없이 바로 설치를 시도하면 파일이 없어 항상 실패한다.

---

## 수정 내용

### 1. 경로 버그 수정 (`main.py`)

`start_install()` 에서 queue 빌드 시 `settings.download_path` (기본값: `"drivers"`)를 `latest_path` 앞에 붙인다.

```python
download_path = settings.get("download_path", "drivers")
for item in raw_queue:
    d = dict(item)
    raw = d.get("latest_path", "")
    if raw:
        d["latest_path"] = str(Path(download_path) / raw)
    queue.append(d)
```

### 2. `download_url` 전달 (`driver_compare.py`)

`compare_device_to_manifest()` 반환 dict에 `download_url` 필드 추가.

### 3. 자동 다운로드 후 설치 (`driver_install.py`)

`install_driver()` 로직:
1. 로컬 경로 존재 확인
2. 없으면 `download_url`에서 `_download_driver()` 호출
3. 다운로드 완료 후 설치 단계로 전환

`_download_driver()` 동작:
- `requests.get(stream=True)` 로 1MB 단위 스트리밍 다운로드
- `_progress.download_pct` 에 실시간 진행률 반영
- abort 플래그 감지 시 다운로드 중단 및 파일 삭제
- 플레이스홀더 EXE(1KB 미만) 제외 — 실제 다운로드된 파일만 실행

`_progress` 신규 필드:
- `stage`: `"idle"` | `"downloading"` | `"installing"`
- `download_pct`: 0~100 (현재 파일 다운로드 진행률)

### 4. 설치 화면 단계 표시 (`app.js`, `index.html`)

`startInstallPoll()` 에서 `progress.stage` 분기:
- `downloading`: 진행 바가 `download_pct` % 를 반영, opStageLabel "다운로드" (파란색)
- `installing`: 기존 shimmer 바 동작 유지, opStageLabel "설치 중" (파란 primary 색)

---

## 설치 흐름 (수정 후)

```
스캔 → 드라이버 선택 → 설치 클릭
  └→ 로컬 파일 확인
       ├─ 있으면: 바로 EXE/INF 설치
       └─ 없으면: download_url에서 다운로드 → 완료 후 EXE 설치
```

## 영향 파일

| 파일 | 변경 유형 |
|------|-----------|
| `core/driver_compare.py` | download_url 반환 추가 |
| `core/driver_install.py` | _download_driver 추가, 경로 fallback 로직 |
| `main.py` | latest_path 프리픽스 수정 |
| `ui/js/app.js` | 단계별 진행 표시 |
| `ui/index.html` | opStageLabel ID 추가 |

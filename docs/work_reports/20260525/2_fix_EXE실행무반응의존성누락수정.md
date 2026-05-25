# 작업 보고서: v1.1.0 EXE 실행 무반응 문제 수정 (v1.1.1)

작성일: 2026-05-25
작업자: Claude (Opus 4.7)

## 1. 증상

v1.1.0 빌드된 EXE를 더블클릭 후 UAC 권한 상승 창에서 수락을 눌렀으나
어떠한 UI 창도 나타나지 않고 프로세스가 즉시 종료되는 현상.

## 2. 원인 분석

`.venv` 환경에 런타임 의존성이 설치되어 있지 않은 채로 PyInstaller 빌드가 수행됨.

v1.1.0 빌드 로그를 다시 점검한 결과 다음 경고가 누락되어 있었음:

```
ERROR: Hidden import 'win32api' not found
ERROR: Hidden import 'win32con' not found
ERROR: Hidden import 'win32gui' not found
ERROR: Hidden import 'pywintypes' not found
```

`pip list` 검증:

```
packaging                 26.2
pyinstaller               6.20.0
pyinstaller-hooks-contrib 2026.5
pywin32-ctypes            0.2.3
```

→ `pywebview`, `pywin32`, `wmi`, `psutil`, `requests`, `pillow` 등
   `requirements.txt`에 정의된 핵심 의존성이 모두 누락.

PyInstaller가 의존성 모듈을 번들에 포함하지 못한 상태로 EXE가 만들어졌고,
main.py 첫 import 단계(`core.hardware_detect` → `wmi`)에서 ImportError로
프로세스가 조용히 종료된 것이 무반응의 정체.

산출물 크기로도 확인 가능: v1.1.0 portable EXE = 8.5 MB (비정상),
v1.1.1 portable EXE = 19.0 MB (정상).

## 3. 조치

### 3.1 .venv 의존성 일괄 설치

```
.venv/Scripts/pip.exe install -r requirements.txt
```

설치된 주요 패키지:
- pywebview 6.2.1 (+ bottle, proxy_tools, pythonnet, clr_loader)
- pywin32 311
- wmi 1.5.1
- psutil 7.2.2
- requests 2.34.2
- pillow 12.2.0
- packaging 26.2

설치 후 임포트 검증:
```
python -c "import wmi, psutil, requests, webview, win32api, win32con, win32gui, pywintypes, packaging"
→ ALL IMPORTS OK
```

### 3.2 버전 패치 (1.1.0 → 1.1.1)

버그 픽스에 해당하므로 마지막 소수점 단위 1 증가.
`config/app_version.json` "version" 필드 갱신.

### 3.3 v1.1.1 재빌드

`python build.py` 실행 → onedir + onefile 모두 정상 빌드.
PyInstaller 로그에 win32 관련 ERROR가 사라지고 `pyi_rth_pywintypes.py` /
`pyi_rth_pythoncom.py` 런타임 훅이 포함되는 것을 확인.

## 4. 변경 파일

| 경로 | 변경 종류 |
|------|----------|
| `config/app_version.json` | version 1.1.0 → 1.1.1 |
| `docs/work_reports/20260525/2_fix_EXE실행무반응의존성누락수정.md` | 신규 (본 보고서) |

코드 변경은 없음. `requirements.txt`는 이미 올바른 상태였음 — `.venv` 환경
설정 누락이 원인이었기 때문.

## 5. 산출물 위치 (v1.1.1)

- onedir: `dist/DriverManagerPro_v1.1.1/DriverManagerPro_v1.1.1.exe`
- onefile portable: `dist/DriverManagerPro_v1.1.1_portable.exe` (19.0 MB)

이전 v1.1.0 산출물은 빌드 시 `_clean_dist()`로 자동 제거되었음.

## 6. 재발 방지

`build.py`가 빌드 직전에 `.venv` 의존성 무결성을 확인하는 가드를 두면
이런 침묵 실패를 사전에 막을 수 있음. 다음 빌드 사이클에서 고려할 개선
사항으로 남겨둠 (이번 작업 범위 밖).

## 7. 검증 시 확인 사항 (사용자 측)

`dist/DriverManagerPro_v1.1.1_portable.exe`를 더블클릭하여:

1. UAC 수락 후 메인 창이 정상적으로 표시되는지
2. 창 표시 직후 자동 스캔이 시작되는지 (v1.1.0에서 추가된 기능)
3. 헤더 체크박스로 업데이트 가능 드라이버만 토글되는지

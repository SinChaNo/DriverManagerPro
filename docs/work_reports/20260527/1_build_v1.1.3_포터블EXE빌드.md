# v1.1.3 포터블 EXE 빌드 작업 보고서

- 작성일: 2026-05-27
- 작업 유형: build / modify
- 작업자: Claude (Opus 4.7)

---

## 1. 작업 목표

PyQt6 QtWebEngine 백엔드 전환 + 트리 UI 개선 사항을 반영하여 v1.1.3 포터블 EXE 산출.

---

## 2. 작업 전 상태

- `config/app_version.json` 버전: **1.1.2** (2026-05-25)
- 누적된 미반영 변경 사항
  - `79b4344` GUI 백엔드 교체 (pywebview → PyQt6 QtWebEngine)
  - `f75a764` QtWebEngine 외부 CDN 리소스 차단 수정
  - `c2733a5` 카테고리 체크박스 동기화 / 트리 ㄴ자 가지선 개선
- 발견된 환경 이슈
  - `.venv`에 **PyQt6 / PyQt6-WebEngine 미설치** (백엔드 교체 후 종속성 갱신 안 됨)
  - `requirements.txt`가 여전히 **`pywebview>=6.2.1`** 항목을 포함하고 PyQt6 항목은 누락
- `dist/`에 구버전 `DriverManagerPro_v1.1.2_portable.exe` 남아있음 (빌드 시 자동 정리)

---

## 3. 작업 단계 및 결과

### 3.1 의존성 매니페스트 정리 — `requirements.txt`

| 변경 | 항목 |
|------|------|
| 제거 | `pywebview>=6.2.1` |
| 추가 | `PyQt6>=6.7.0` |
| 추가 | `PyQt6-WebEngine>=6.7.0` |
| 추가 | `pywin32>=308` (명시) |
| 유지 | `wmi`, `psutil`, `requests`, `packaging`, `pyinstaller`, `pillow` |

### 3.2 버전 올림 — `config/app_version.json`

```json
{
  "version": "1.1.3",
  "build_date": "2026-05-27",
  "channel": "stable"
}
```

### 3.3 `.venv` 패키지 설치

```
.\.venv\Scripts\python.exe -m pip install -r requirements.txt --upgrade
```

신규 설치된 항목:
- `PyQt6-6.11.0`
- `PyQt6-Qt6-6.11.1`
- `PyQt6-WebEngine-6.11.0`
- `PyQt6-WebEngine-Qt6-6.11.1`
- `PyQt6-sip-13.11.1`

### 3.4 빌드 실행 — `python build.py --onefile`

- 모드: **onefile (포터블)**
- 사용 Python: `.venv` (Python 3.14.4)
- 자동 처리
  - `dist/` 사전 정리 (이전 v1.1.2 산출물 제거)
  - `assets/icon.ico`, `assets/app.manifest` 재생성
  - `DriverManagerPro_onefile.spec` 재작성 (PyQt6 hiddenimports 반영)
- PyInstaller 6.20.0이 `hook-PyQt6.*` 표준 훅을 적용해 QtCore/Gui/Widgets/Network/WebChannel/WebEngineCore/WebEngineWidgets/Quick/Qml/OpenGL 등 일괄 번들링.

### 3.5 산출물

| 파일 | 크기 | 비고 |
|------|------|------|
| `dist/DriverManagerPro_v1.1.3_portable.exe` | **196.71 MB** | UAC `requireAdministrator`, 단일 실행 EXE |

크기 증가 원인: QtWebEngine 런타임(Qt6 WebEngine 코어 + Chromium)이 onefile에 모두 포함됨.

---

## 4. 작업 후 상태

- 신규 커밋
  - `34124cd` modify: v1.1.3 — PyQt6 의존성 정리 및 빌드 버전 올림
- 워킹 트리 변경 (커밋 이후)
  - 본 작업 보고서: `docs/work_reports/20260527/1_build_v1.1.3_포터블EXE빌드.md`
- 빌드 산출물 (Git 무시 대상)
  - `dist/DriverManagerPro_v1.1.3_portable.exe`

---

## 5. 검증/확인 권장 사항

1. EXE 실행 → UAC 승인 → 정상 GUI(QtWebEngine 창) 표시 여부
2. 자동 스캔 후 드라이버 트리 렌더링 (카테고리 체크박스 동기화, ㄴ자 가지선 시각 확인)
3. 외부 CDN 차단으로 UI 깨짐이 재발하지 않는지 확인
4. 관리자 권한 하에서 실제 드라이버 설치 1건 시범 실행

---

## 6. 비고 / 후속 과제

- onedir 빌드도 동일 버전(1.1.3)으로 별도 산출하려면 `python build.py --onedir`. 본 작업에서는 사용자 결정에 따라 onefile만 산출.
- README의 시스템 요구사항 항목에 PyQt6 + WebEngine 런타임 의존성 변경 사항을 반영하면 좋음 (현재 별도 갱신 없음).
- `excludes`에서 `pywebview`, `clr`, `pythonnet` 등을 명시적으로 제외해 두어 잔존 패키지가 있어도 번들에 끌려오지 않도록 처리되어 있음.

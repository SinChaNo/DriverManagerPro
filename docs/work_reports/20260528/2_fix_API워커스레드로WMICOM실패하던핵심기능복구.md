# API 워커 스레드로 WMI/COM 실패하던 핵심 기능 복구

작업일: 2026-05-28
작업 유형: fix

## 증상

PyQt6 마이그레이션 후 `pywebviewready` 이벤트 디스패치 수정으로 `init()`이
호출되도록 한 뒤에도 다음 기능이 여전히 미동작:

- CPU/RAM/GPU/BIOS 카드 전부 "정보 없음"
- 하드웨어 자동 스캔이 결과 없음
- DB 업데이트 버튼을 눌러도 "연결 중..."에서 진행되지 않고
  `undefined / undefined 파일` 표시
- 헤더 온라인 상태(`is_online`)만 정상 동작 — 다른 기능은 전부 깨짐

## 근본 원인

`main.py`에서 API 객체를 별도 QThread로 이동:

```python
api = API()
api_thread = QThread()
api.moveToThread(api_thread)
api_thread.start()
```

이로 인해 다음 부작용 발생:

1. **WMI(COM) 호출 실패**
   - `core/hardware_detect.py`의 `scan_hardware()`, `get_system_summary()`,
     `get_bios_info()` 모두 `wmi.WMI()`로 COM 인터페이스 호출
   - Qt 워커 스레드는 COM이 자동 초기화되지 않음
   - 모든 WMI 쿼리가 silent fail → CPU/GPU/BIOS 필드가 dict에 추가되지 않음

2. **다운로드/설치 동작 불안정**
   - `start_download_thread()`가 Qt 워커 스레드에서 호출되며 `threading.Thread`
     스폰의 컨텍스트가 비정상적
   - 전역 상태 락(`_state_lock`) 접근 패턴이 예상과 달라질 가능성

3. **`is_online`만 동작했던 이유**
   - `check_connectivity()`는 `requests.get()`만 사용 (COM/WMI 무관)
   - 따라서 워커 스레드에서도 정상 동작

## 수정 내용

### 설계 변경: API를 GUI 메인 스레드에 유지

이전 pywebview의 동작 방식과 동일한 패턴으로 회귀. 긴 블로킹 작업은 슬롯
내부에서 별도 `threading.Thread`로 분리하는 표준 방식 사용 (이미 `start_install`,
`download_driver_db`가 이 패턴을 따름).

### `main.py`

1. **`QThread`, `moveToThread` 제거**
   ```python
   # Before
   api = API()
   api_thread = QThread()
   api.moveToThread(api_thread)
   api_thread.start()

   # After
   api = API()
   ```

2. **메인 스레드에서 COM 명시적 초기화** — `_init_com()` 신규
   ```python
   def _init_com() -> None:
       try:
           import pythoncom
           pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
       except Exception as exc:
           logger.warning("COM 초기화 경고(무시 가능): %s", exc)
   ```
   - `pythoncom.CoInitializeEx(COINIT_APARTMENTTHREADED)`로 STA 모드 초기화
   - WMI 등 COM 기반 라이브러리가 메인 스레드에서 정상 동작 보장
   - `main()` 시작 직후 호출

3. **App 종료 시 워커 스레드 정리 로직 제거** (워커 스레드가 없으므로 불필요)

### `build.py`

`hiddenimports`에 `pythoncom` 추가:
```python
hidden = [
    "wmi", "psutil", "requests", "packaging",
    "win32api", "win32con", "win32gui", "pywintypes", "pythoncom",  # ← 추가
    ...
]
```

PyInstaller가 `pythoncom`의 의존 DLL을 누락하지 않도록 명시.

### `config/app_version.json`

v1.1.4 → v1.1.5.

## 응답성 영향

API가 메인 스레드에 있으므로 동기 슬롯이 길어지면 GUI가 잠시 멈출 수 있다.
다음 작업은 슬롯 내부에서 이미 `threading.Thread`로 분리되어 영향 없음:

- `start_install()` — 설치 큐 실행을 Thread로 분리
- `download_driver_db()` → `start_download_thread()` — 다운로드를 Thread로 분리

`scan_hardware`, `get_system_summary`는 메인 스레드 블로킹이지만 보통 1~3초
수준이며 기존 pywebview 환경에서도 동일했던 동작.

## 재빌드 결과

```
산출물: dist/DriverManagerPro_v1.1.5_portable.exe
크기:   197.55 MB
빌드:   2026-05-28
```

## 검증

EXE 실행 후 다음 시나리오 확인:
- 헤더의 온라인 상태 갱신
- CPU/RAM/GPU/BIOS 카드에 실제 시스템 정보 표시
- "DB 업데이트" 버튼 클릭 시 진행률 갱신
- 자동/수동 스캔 결과 표시

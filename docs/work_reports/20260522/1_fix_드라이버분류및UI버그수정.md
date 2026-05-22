# 작업 보고서 — 드라이버 분류 오류 및 UI 버그 수정

- 날짜: 2026-05-22
- 유형: fix
- 커밋: 614ac7e

---

## 수정 이슈 목록

### 1. 드라이버 분류가 전부 "기타 장치"로 표기되는 문제

**원인**
- `Win32_PnPSignedDriver.DeviceClass` 가 일부 드라이버에서 빈 값(`""`) 반환
- `driver_compare.py` 반환 시 `device_class` 가 빈 값 그대로 전달
- JS `renderTree()`에서 `d.device_class || 'Other'` 로 처리되어 전부 "기타 장치" 표시

**수정 내용**
- `core/hardware_detect.py`: `_CLASS_NORMALIZE` 매핑 테이블 + `_normalize_class()` 함수 추가 (WMI DeviceClass → CAT 키 정규화)
- `core/hardware_detect.py`: `_infer_class_from_name()` 함수 추가 (DeviceClass가 빈 값일 때 장치명 키워드로 추론)
- `core/driver_compare.py`: 반환 dict의 `device_class` 필드에 manifest `class` fallback 적용
  ```python
  final_class = device_class if device_class else driver_entry.get("class", "Other")
  ```
- `ui/js/app.js`: CAT 카테고리 한국어 레이블로 변경, `Storage` / `Security` 카테고리 추가

### 2. CPU 내장 그래픽만 표시, Processor 클래스 제외

**수정 내용**
- `ui/js/app.js` `renderTree()` 에서 `Processor` 클래스 항목 필터링
  ```js
  if (cls === 'Processor') return;
  ```
- 내장 그래픽(Intel UHD/HD Graphics)은 `Win32_VideoController` 통해 `Display` 클래스로 별도 수집되므로 정상 표시됨

### 3. 메인보드 BIOS 버전 표시

**수정 내용**
- `core/hardware_detect.py`: `get_bios_info()` 함수 추가 (`Win32_BIOS.SMBIOSBIOSVersion` 조회)
- `core/hardware_detect.py`: `get_system_summary()` 에 `bios_version`, `bios_date`, `bios_manufacturer` 필드 추가
- `ui/js/app.js` `renderSysCards()`: BIOS 카드 4번째 항목으로 추가
- `ui/index.html`: sysCards 그리드를 `lg:grid-cols-4` 로 변경

### 4. 설치 실패 시 초록 아이콘 표시 문제

**수정 내용**
- `ui/index.html`: 완료 화면 modal, glow, icon span에 ID 추가 (`completeModal`, `completeGlow1`, `completeGlow2`, `completeIconSpan`)
- `ui/js/app.js` `showComplete()`: 성공/일부실패/전체실패 세 가지 테마를 런타임에 동적 적용
  - 전체 성공: 초록 테마 + `check_circle` 아이콘
  - 일부 실패: 노란 테마 + `warning` 아이콘
  - 전체 실패: 빨간 테마 + `cancel` 아이콘

### 5. 실패 오류 로그 확인 불가 문제

**수정 내용**
- `ui/js/app.js` `showComplete()`: 실패 항목에 `expand_more` 버튼 추가
- 클릭 시 `toggleErrLog(i)` 호출 → 설치 오류 메시지(`r.message`) 코드 블록으로 토글 표시
- `driver_install.py`의 `install_driver()` 반환값 `message` 필드 그대로 출력

### 6. 완료 후 확인 버튼 클릭 시 빈 화면 문제

**수정 내용**
- `ui/js/app.js` `btnCompleteDone` / `btnRestartLater` 핸들러 수정
  - 기존: `setMainState('idle')` → 스캔 초기 화면
  - 변경: `setMainState('results')` (기존 결과 유지) + `setTimeout(runScan, 400)` 자동 재스캔 실행
  - 시스템 카드(`sysCards`)는 상태 전환과 무관하게 유지됨 (상태 div 외부 위치)

---

## 영향 파일

| 파일 | 변경 유형 |
|------|-----------|
| `core/hardware_detect.py` | 기능 추가 (정규화, BIOS 조회) |
| `core/driver_compare.py` | 버그 수정 (class fallback) |
| `ui/js/app.js` | 버그 수정 + 기능 추가 |
| `ui/index.html` | ID 추가, 그리드 변경 |

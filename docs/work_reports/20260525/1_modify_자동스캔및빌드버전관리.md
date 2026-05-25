# 작업 보고서: 자동 스캔 및 빌드 버전 관리 도입

작성일: 2026-05-25
작업자: Claude (Opus 4.7)

## 1. 작업 배경

사용자가 다음 사항을 요청함:

1. 컬럼 헤더의 체크박스 하나로 업데이트 가능 드라이버 전체 선택/해제가 가능해야 함 (기존 "전체 선택" 버튼 제거)
2. 최신 버전 드라이버는 어떤 경로로도 선택되지 않아야 하며 설치 불가 상태여야 함
3. 프로그램이 처음 실행될 때 사용자가 스캔 버튼을 누르지 않아도 자동으로 스캔이 시작되어야 함
4. 빌드 시 dist/ 디렉토리의 이전 산출물을 모두 삭제한 뒤 새로 빌드해야 함
5. 빌드 산출물 파일명에 버전(예: v1.0, v1.1)을 접미사로 부여해 식별 가능해야 함
6. 버전 정책: 자잘한 버그 픽스는 소수점 1 단위 증가, 대규모 업데이트는 정수부 증가

## 2. 현황 검증 결과

코드 조사 결과 항목 1, 2는 직전 커밋(`aadcc7a fix: 전체 선택 버튼을 체크박스 헤더로 이동 및 업데이트 필요 드라이버만 선택되도록 수정`)에서 이미 적용되어 있었음:

- `ui/index.html` 라인 131: `#cbSelectAll` 체크박스가 컬럼 헤더 위치(w-12 영역)에 존재. 기존 `#btnSelectAll` 버튼은 제거된 상태
- `ui/js/app.js` `renderTree()` 내부:
  - `canSelect = hasUpdate` 로 업데이트 가능 여부에 따라 dev-cb 체크박스에 `disabled` 부여
  - 카테고리 체크박스(`.cat-cb`) 토글 시 `!dcb.disabled` 가드로 최신 드라이버 강제 선택 차단
  - `selectAllUpdates()` 가 `update_available` 필터링 후 `S.selectedIds`에만 추가
  - `runScan()` 완료 직후 자동 선택도 동일 필터 적용

따라서 항목 1, 2는 추가 수정 없이 동작 중이며, 사용자가 보았던 스크린샷은 이전 빌드 EXE 화면으로 판단됨.

## 3. 신규 변경 사항

### 3.1 `ui/js/app.js` — 시작 시 자동 스캔

`init()` 함수 수정:

- 파일 상단에 수정 이력 헤더 주석 추가 (2026-05-25 자동 스캔 추가 명시)
- 모듈 스코프에 `_initDone` 플래그 추가하여 `pywebviewready` 이벤트와 폴백이 모두 발화하는 경우 중복 init 방지
- `renderSysCards()` 를 먼저 호출하여 시스템 정보 카드가 그려진 뒤 스캔에 진입하도록 순서 조정
- `has_driver_db == true` 이면 자동으로 `runScan()` 호출. 콘솔 로그도 "자동 스캔을 시작합니다." 로 변경
- DB가 없는 경우는 기존과 동일하게 idle 상태 + 안내 메시지 유지

### 3.2 `config/app_version.json` — 버전 갱신

`1.0.0` → `1.1.0` 으로 변경. 자잘한 기능 추가(자동 스캔)에 해당하므로 소수점 1 단위 증가 정책 적용. `build_date` 도 2026-05-25 로 갱신.

### 3.3 `build.py` — 버전 접미사 및 dist 정리

주요 변경:

| 변경 항목 | 내용 |
|----------|------|
| 헤더 주석 | "버전 관리 정책" 절을 추가하여 산출물 명명 규칙과 버전업 정책을 문서화 |
| `_read_app_version()` | `config/app_version.json` 에서 버전을 읽어 반환. 실패 시 안전 기본값 `0.0.0` |
| `_clean_dist()` | `dist/` 내부 모든 파일/디렉토리 삭제. 파일 잠금 시 WARNING 으로 통과 |
| `_build_spec(mode, icon, manifest, version)` | 인자에 `version` 추가. 산출물명을 `DriverManagerPro_v{version}` 로 구성 |
| `run_build(mode, version)` | 인자에 version 추가. 중간 산출물 EXE 정리 시 새 base_name 사용 |
| `main()` | 모드 루프 시작 전 `_read_app_version()` 호출 후 `_clean_dist()` 로 1회 정리 |

산출물 명명 규칙:

- onedir 폴더: `dist/DriverManagerPro_v1.1.0/`
- onedir EXE: `dist/DriverManagerPro_v1.1.0/DriverManagerPro_v1.1.0.exe`
- onefile portable: `dist/DriverManagerPro_v1.1.0_portable.exe`

## 4. 영향 파일

| 경로 | 변경 종류 |
|------|----------|
| `ui/js/app.js` | 수정 (헤더 주석, init 자동 스캔) |
| `config/app_version.json` | 수정 (1.0.0 → 1.1.0, 빌드 날짜 갱신) |
| `build.py` | 수정 (버전 접미사, dist 정리) |
| `docs/work_reports/20260525/1_modify_자동스캔및빌드버전관리.md` | 신규 (본 보고서) |

## 5. 빌드 결과

- dist/ 사전 정리 정상 동작 확인:
  - 이전 산출물 `DriverManagerPro/`, `DriverManagerPro.exe`, `DriverManagerPro_portable.exe`, `config/`, `logs/` 모두 제거
- PyInstaller 가 .venv 에 누락되어 1회 실패 → `.venv/Scripts/pip.exe install pyinstaller` 로 설치 후 재실행
- v1.1.0 산출물 생성 (onedir + onefile)

## 6. 검증 시 확인 사항 (사용자 측)

빌드된 EXE 실행 후 다음을 확인:

1. 컬럼 헤더 좌측에 체크박스가 한 개 표시되고 별도 "전체 선택" 버튼이 없는지
2. 프로그램 실행 직후 자동으로 스캔이 시작되는지 (Idle 화면이 거의 즉시 Scanning 으로 전환)
3. 스캔 완료 후 업데이트 가능 드라이버가 자동 선택되고, 최신 드라이버 체크박스는 비활성(클릭 불가)인지
4. 헤더 체크박스 토글 시 최신 드라이버는 절대 선택되지 않는지

## 7. 버전 관리 정책 (이후 적용)

- `1.0` → `1.1`: 자잘한 기능 추가/버그 픽스 (소수점 1 단위 증가)
- `1.x` → `2.0`: 대규모 업데이트 (정수부 증가)
- 버전은 `config/app_version.json` 의 `version` 필드 단일 출처에서 관리하며 build.py 가 자동 참조

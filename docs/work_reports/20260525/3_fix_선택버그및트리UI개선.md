# 작업 보고서: 최신 드라이버 잘못 선택 버그 + 트리 UI + BIOS 카드 개선 (v1.1.2)

작성일: 2026-05-25
작업자: Claude (Opus 4.7)

## 1. 사용자 요청 사항

1. 헤더 체크박스로 전체 선택 시 "최신" 드라이버까지 같이 선택되는 버그 발생
2. 트리 구조가 한눈에 들어오지 않으니 시각적으로 더 명확하게 보이도록 개선
3. BIOS/메인보드 카드에서 글자가 깨져 보임. 또한 BIOS 버전이 최신인지 확인할 수 있어야 함
4. 작업은 사용자에게 묻지 말고 자율적으로 진행

## 2. 원인 분석

### 2.1 최신 드라이버 잘못 선택 버그

`querySelector('.dev-cb[data-id="${id}"]')`가 같은 `driver_id`를 가진 여러 행 중 첫 번째를 잡아낸다.
백엔드가 한 드라이버 매니페스트 항목을 여러 디바이스와 매칭하면 동일한 `driver_id`로 두 개 이상의 행이 만들어지는데,
그 중 한 행은 `update_available=true` (활성 체크박스), 다른 행은 `update_available=false` (disabled 체크박스)가 된다.
`querySelector`는 DOM 순서상 먼저 나오는 행을 잡으므로 disabled 행을 잡으면 `cb.checked = true`가 설정되어
시각적으로는 "최신" 라벨이 붙은 행에 체크가 들어간 것처럼 보였다.

증상 — 사용자 스크린샷에서 "선택 설치 (2)"만 표시되고 "최신" 라벨이 있는 두 행에 체크 표시가 있었던 것이 이 패턴.

### 2.2 BIOS 카드 글자 깨짐

`<span class="material-symbols-outlined">settings_firmware</span>` — `settings_firmware` 는 Material Symbols Outlined 폰트에 실존하지 않는 이름. 폰트가 해당 글리프를 찾지 못해 글자 그대로 "settings_firmware" 가 렌더링되었고, 카드 너비에서 잘려 "_FIRMWARE" 로 보였다.

### 2.3 트리 구조 가독성

카테고리와 디바이스 행이 같은 들여쓰기로 평행 배치되어 부모-자식 관계가 시각적으로 잘 드러나지 않았다.

## 3. 변경 사항

### 3.1 `ui/js/app.js`

| 함수 | 변경 |
|------|------|
| `renderSysCards` | BIOS 카드 아이콘을 실존 이름 `developer_board`로 교체. 라벨을 "BIOS / 메인보드"로 변경. 제조사를 부가 정보로 노출하고 "수동 확인 필요" 배지 추가 (BIOS 자동 검사는 위험하므로 사용자가 제조사 사이트에서 직접 확인). 우측 태그에 `whitespace-nowrap shrink-0` 적용으로 잘림 방지 |
| `_dedupeByDriverId` (신규) | `renderTree` 진입 시 동일 `driver_id` 중복을 제거. `update_available=true` 항목을 우선 보존 |
| `renderTree` | dedupe 결과를 `S.updateList`에 저장. 디바이스 행에 `is-updatable` / `is-current` 상태 클래스 부여. 자식 컨테이너 클래스 `bg-bg/40` → `tree-children` 으로 교체하여 가이드 라인 적용. 업데이트 없는 카테고리의 카테고리 체크박스 disabled 처리 |
| `selectAllUpdates`, `runScan` 자동 선택, 검색 selectedIds 복원 | 모두 `.dev-cb[data-id="…"]:not([disabled])` 가드를 적용. disabled 체크박스는 절대 `checked=true` 가 되지 않음 |

### 3.2 `ui/css/style.css`

- `.tree-category[open]` 상태에서 summary 배경 강조 + chevron 색상을 primary로 변경
- `.tree-category > summary` 좌측 3px primary 경계선 (펼침 상태일 때)
- `.tree-children` 신규: 자식 영역 padding-left + 어두운 배경. `::before` pseudo-element 로 수직 가이드 라인(linear-gradient로 자연스럽게 사라짐)
- `.device-row::before` pseudo-element 로 수평 분기 연결선
- `.device-row.is-updatable` 좌측 빨간 경계선으로 업데이트 필요 행 강조
- `.device-row.is-current` 행 전체 opacity 0.7로 옅게

### 3.3 `config/app_version.json`

1.1.1 → 1.1.2 (버그 픽스 + 시각 개선이므로 소수점 1 단위)

## 4. 영향 파일

| 경로 | 변경 종류 |
|------|----------|
| `ui/js/app.js` | 수정 (헤더 이력 갱신, BIOS 카드, dedup, disabled 가드, 트리 클래스) |
| `ui/css/style.css` | 수정 (트리 가이드 라인, 행 상태 시각화) |
| `config/app_version.json` | 수정 (1.1.1 → 1.1.2) |
| `docs/work_reports/20260525/3_fix_선택버그및트리UI개선.md` | 신규 (본 보고서) |

## 5. 결과

- 같은 `driver_id` 가 데이터에 여러 번 나타나도 disabled 체크박스가 잘못 체크되지 않음 (이중 방어: dedupe + `:not([disabled])` 가드)
- 트리 자식 영역에 수직 가이드 라인 + 수평 분기 연결선이 표시되어 부모-자식 관계가 분명히 보임
- 업데이트 필요한 행은 좌측 빨간 경계선으로 강조, 최신 행은 옅게 표시되어 우선순위 한눈에 파악 가능
- BIOS 카드: 정상 아이콘 + 제조사 + 날짜 + "수동 확인 필요" 노란 배지가 함께 표시됨

## 6. 산출물 위치 (v1.1.2)

- onedir: `dist/DriverManagerPro_v1.1.2/DriverManagerPro_v1.1.2.exe`
- onefile portable: `dist/DriverManagerPro_v1.1.2_portable.exe`

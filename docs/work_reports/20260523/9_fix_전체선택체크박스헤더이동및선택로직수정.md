# 작업 보고서: 전체 선택 체크박스 헤더 이동 및 선택 로직 수정

- **작업 유형**: fix
- **작업 일시**: 2026-05-23
- **담당**: Claude

## 문제 요약

스캔 완료 후 툴바의 "전체 선택" 버튼을 클릭하면 업데이트가 필요 없는 드라이버(최신 버전)까지 선택 상태로 표시되는 버그가 있었으며, UX 측면에서 전체 선택 컨트롤이 드라이버 목록 테이블과 분리되어 있어 직관성이 낮았음.

## 변경 내용

### ui/index.html

- 툴바 영역의 `btnSelectAll` 버튼(전체 선택/해제) 제거
- 테이블 헤더 "선택" 텍스트를 `id="cbSelectAll"` 체크박스로 교체
  - `disabled` 초기 상태, `title` 속성으로 툴팁 제공
  - 업데이트 가능 드라이버가 있을 때만 활성화

### ui/js/app.js

- `updateSelectionUI()`: `selectAllLabel` 텍스트 갱신 로직 제거, 헤더 체크박스(`cbSelectAll`)의 `checked` / `indeterminate` 상태 동기화 로직으로 교체
  - 전체 선택 시 `checked = true`
  - 일부 선택 시 `indeterminate = true` (중간 상태 표시)
  - 미선택 시 `checked = false`
- `selectAllUpdates()`: 토글 방식에서 헤더 체크박스의 `checked` 값을 기준으로 선택/해제 방향 결정 방식으로 변경
- `runScan()`: `$('btnSelectAll').disabled` 참조를 `cbSelectAll.disabled` 참조로 교체
- 이벤트 리스너: `btnSelectAll click` → `cbSelectAll change` 로 교체

## 기대 동작

- 스캔 완료 후 업데이트 가능(update_available=true) 드라이버만 자동 선택
- 최신 버전 드라이버는 체크박스가 disabled 상태로 선택 불가
- 헤더 체크박스 체크 시 업데이트 가능 드라이버 전체 선택, 해제 시 전체 해제
- 일부만 선택된 경우 헤더 체크박스가 indeterminate(중간) 상태로 표시

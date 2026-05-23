# 전체 선택 및 스캔 후 자동 선택 기능 추가 작업 보고서

- 작업 일자: 2026-05-23
- 작업 유형: modify
- 작업자: Claude

---

## 개요

드라이버 목록에서 업데이트 가능한 항목을 일괄 선택하는 기능과
스캔 완료 시 자동으로 업데이트 가능한 드라이버를 선택 상태로 표시하는 기능을 추가하였다.

---

## 수정 항목

### 1. 전체 선택/해제 토글 버튼 추가 (ui/index.html, ui/js/app.js)

**변경 내용:**
- 결과 상단 바에 `#btnSelectAll` 버튼 추가 (기존 설치 버튼 왼쪽)
- 업데이트 가능한 드라이버가 없으면 비활성화(disabled)
- `selectAllUpdates()` 함수 구현:
  - 업데이트 가능한 모든 드라이버 ID 수집
  - 전부 선택 상태이면 전체 해제, 아니면 전체 선택 (토글)
  - DOM 체크박스 checked 상태 동기화 후 `updateSelectionUI()` 호출
- `updateSelectionUI()`에 버튼 텍스트 갱신 로직 추가:
  - 업데이트 가능 드라이버가 모두 선택 상태이면 "전체 해제"
  - 그 외에는 "전체 선택"

---

### 2. 스캔 완료 시 자동 선택 (ui/js/app.js)

**변경 내용:**
- `runScan()` 에서 `renderTree()` 호출 직후 `update_available: true`인 드라이버를 자동으로 `S.selectedIds`에 추가하고 DOM 체크박스를 checked로 설정
- 자동 선택 후 `updateSelectionUI()` 호출하여 버튼 카운트 반영

---

### 3. 검색 필터링 시 선택 상태 보존 (ui/js/app.js)

**변경 내용:**
- `renderTree()`가 호출될 때마다 `S.selectedIds.clear()`를 실행하는 기존 구조로 인해, 검색 필터링 시 선택이 초기화되는 문제를 수정
- 검색 이벤트 핸들러에서 `savedIds = new Set(S.selectedIds)` 로 선택 보존
- `renderTree()` 호출 후 `savedIds`를 복원하고 DOM 체크박스 동기화

---

## 변경 파일 요약

| 파일 | 변경 내용 |
|------|-----------|
| `ui/index.html` | `#btnSelectAll` 버튼 추가 |
| `ui/js/app.js` | `selectAllUpdates()`, `updateSelectionUI()` 갱신, `runScan()` 자동 선택, 검색 선택 보존 |

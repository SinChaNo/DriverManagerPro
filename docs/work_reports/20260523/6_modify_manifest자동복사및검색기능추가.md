# manifest 자동 복사 및 검색 기능 추가 작업 보고서

- 작업 일자: 2026-05-23
- 작업 유형: modify
- 작업자: Claude

---

## 개요

improvement_roadmap.md 우선순위 즉시 항목 2건을 구현하였다.

1. **main.py** — 최초 실행 시 번들 manifest 자동 복사
2. **ui/js/app.js** — 검색창 실시간 필터링 기능 연결

---

## 수정 항목

### 1. manifest 자동 복사 (main.py)

**문제:** PyInstaller onedir 빌드 시 `manifest.json`은 `_internal/drivers/`(RESOURCE_DIR)에 번들되지만 앱은 `EXE옆/drivers/`(BASE_DIR)를 참조한다. 최초 실행 시 BASE_DIR에 파일이 없으면 `has_driver_db()` → false가 되어 스캔 불가.

**변경 내용:**
- `import shutil` 추가
- `_ensure_manifest()` 함수 추가: BASE_DIR에 manifest가 없을 때 RESOURCE_DIR에서 복사
- `main()` 함수 내 UAC 통과 직후 `_ensure_manifest()` 호출

```python
def _ensure_manifest() -> None:
    settings = _load_settings()
    download_path = settings.get("download_path", "drivers")
    dest = BASE_DIR / download_path / "manifest.json"
    if not dest.exists():
        src = RESOURCE_DIR / download_path / "manifest.json"
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            logger.info("번들 manifest를 데이터 디렉토리로 복사: %s", dest)
```

---

### 2. 검색창 실시간 필터링 (ui/js/app.js)

**문제:** `index.html`에 `#searchInput` 요소가 존재하지만 `app.js`에 이벤트 리스너가 없어 검색이 동작하지 않았다.

**변경 내용:**
- `S` 상태 객체에 `fullUpdateList: []` 필드 추가
- `runScan()` 내 `renderTree()` 호출 전에 `S.fullUpdateList = updateList` 저장 및 검색어 초기화
- `$('searchInput').addEventListener('input', ...)` 추가:
  - `mainState !== 'results'`이면 무시 (스캔 전/중 입력 차단)
  - 검색어가 없으면 전체 목록(`S.fullUpdateList`) 복원
  - device_name / driver_name / vendor 기준 부분 일치 필터링

**설계 근거:** `renderTree(list)`가 `S.updateList = list`를 덮어쓰므로, 검색 필터링 시 원본 보존을 위해 `S.fullUpdateList`를 별도 유지한다. 클릭 가능한 항목은 항상 현재 표시된 목록에 포함되어 있으므로 `S.updateList.find()` 동작에 영향 없음.

---

## 변경 파일 요약

| 파일 | 변경 내용 |
|------|-----------|
| `main.py` | `import shutil`, `_ensure_manifest()` 추가, `main()` 호출 |
| `ui/js/app.js` | `S.fullUpdateList` 추가, `runScan` 저장 로직, 검색 이벤트 리스너 |

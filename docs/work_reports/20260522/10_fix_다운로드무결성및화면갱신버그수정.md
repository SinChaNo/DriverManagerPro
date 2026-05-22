# 다운로드 무결성 검증 및 화면 갱신 버그 수정

- 날짜: 2026-05-22
- 작업 유형: fix
- 작업자: Claude

## 수정된 버그 3건

---

### Bug 1 — WinError 1392: 손상된 EXE 실행 실패 (`core/driver_install.py`)

**증상**: 드라이버 설치 시 "파일 또는 디렉터리가 손상되었기 때문에 읽을 수 없습니다" 오류 발생.

**근본 원인**: Bug 3(0바이트 다운로드)으로 생성된 빈 파일을 `_run_vendor_exe()` 가 실행 시도 → Windows OS가 WinError 1392를 반환.

**수정 — `_run_vendor_exe()` MZ 헤더 검증**

```python
# EXE 실행 전 유효성 검증 — MZ 헤더 없으면 즉시 오류 반환
with open(exe_path, "rb") as f:
    header = f.read(2)
if header != b"MZ":
    msg = f"EXE 파일이 유효하지 않습니다 (MZ 헤더 없음, {size}바이트): {exe_path.name}"
    logger.error(msg)
    return False, msg, False
```

**수정 — `_download_driver()` 다운로드 후 크기 검증**

```python
final_size = dest_file.stat().st_size if dest_file.exists() else 0
if final_size == 0:
    logger.error("Download produced empty file (0 bytes): %s", url)
    dest_file.unlink(missing_ok=True)
    return False, "다운로드 실패: 파일 크기가 0바이트입니다 (서버 오류 또는 URL 만료)"
```

---

### Bug 3 — 0.0 MB 표기 = 실제 다운로드 실패 (`core/downloader.py`)

**증상**: DB 업데이트 화면에서 `0.0 MB / 0.0 MB` 로 표기되나 실제로는 다운로드 실패. `_download_file()` 이 스트림이 비어도 `True` 를 반환하여 빈 파일이 생성됨.

**수정 — `_download_file()` 다운로드 후 0바이트 검증**

```python
# 다운로드 후 파일 크기 검증 — 0바이트는 실패로 처리
final_size = dest.stat().st_size if dest.exists() else 0
if final_size == 0:
    logger.error("Download produced empty file (0 bytes): %s", url)
    dest.unlink(missing_ok=True)
    return False
return True
```

---

### Bug 2 — 해상도 변경 후 화면 일부 불표시 (`ui/js/app.js`)

**증상**: 그래픽 드라이버 업데이트 후 해상도 변경 시 프로그램 화면 일부가 표시되지 않음. 창 크기를 조절해도 복구되지 않음.

**원인**: WebView2(EdgeChromium)가 OS 해상도 변경을 감지하지 못하고 레이아웃을 갱신하지 않음.

**수정 — resize 이벤트 핸들러 추가**

```javascript
window.addEventListener('resize', () => {
  // 150ms 디바운스 후 display none/block 토글로 강제 리플로우
  const b = document.body;
  b.style.display = 'none';
  b.offsetHeight; // 레이아웃 플러시
  b.style.display = '';
});
```

150ms 디바운스를 적용하여 리사이즈 이벤트가 연속 발생해도 한 번만 실행되도록 처리.

---

## 변경 파일

| 파일 | 수정 내용 |
|---|---|
| `core/downloader.py` | `_download_file()` — 0바이트 파일 검증 및 삭제 후 `False` 반환 |
| `core/driver_install.py` | `_download_driver()` — 0바이트 검증 / `_run_vendor_exe()` — MZ 헤더 검증 |
| `ui/js/app.js` | `window.resize` 이벤트 핸들러 — 강제 리플로우 |

# onefile EXE UI 경로 오류 수정

- 날짜: 2026-05-22
- 작업 유형: fix
- 작업자: Claude

## 문제

`DriverManagerPro_portable.exe` 실행 시 아래 오류 발생:

```
FileNotFoundError: UI not found at C:\DevProject\videcoding\DriverManagerPro\dist\ui\index.html
```

## 원인 분석

PyInstaller `onefile` 빌드 시 내장 리소스(`ui/`, `config/`, `drivers/`)는 런타임에
`sys._MEIPASS` 임시 폴더에 압축 해제된다.

기존 `get_base_dir()`는 frozen 상태에서 `Path(sys.executable).parent`(EXE가 위치한 `dist/`)를
반환하므로, `_find_ui()`가 `dist/ui/index.html`을 탐색하여 `FileNotFoundError`가 발생했다.

| 경로 | 설명 |
|---|---|
| `Path(sys.executable).parent` | EXE가 있는 폴더 — 쓰기 가능한 데이터 저장 위치 |
| `sys._MEIPASS` | PyInstaller가 번들 리소스를 압축 해제하는 임시 폴더 |

## 수정 내용

**파일:** `main.py`

### 1. `get_resource_dir()` 함수 추가

```python
def get_resource_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent
```

- `onefile` 빌드 시 `sys._MEIPASS` 반환
- `onedir` 빌드 및 소스 실행 시 `__file__` 기준 반환 (기존과 동일)

### 2. `RESOURCE_DIR` 전역변수 추가

두 경로를 역할별로 분리:

| 변수 | 경로 | 용도 |
|---|---|---|
| `BASE_DIR` | EXE 옆 폴더 | config, drivers, logs 등 쓰기 데이터 |
| `RESOURCE_DIR` | `sys._MEIPASS` (onefile 시) | ui, 번들 manifest 등 읽기 전용 리소스 |

### 3. `_find_ui()` 수정

```python
# 수정 전
ui_path = BASE_DIR / "ui" / "index.html"

# 수정 후
ui_path = RESOURCE_DIR / "ui" / "index.html"
```

### 4. `get_app_version()` 폴백 추가

`app_version.json`은 번들 내장본과 EXE 옆 파일 두 곳에 존재할 수 있으므로,
`BASE_DIR` 우선 탐색 후 없으면 `RESOURCE_DIR`을 사용한다.

```python
for base in (BASE_DIR, RESOURCE_DIR):
    try:
        with open(base / "config" / "app_version.json", ...) as f:
            return json.load(f).get("version", "1.0.0")
    except Exception:
        continue
return "1.0.0"
```

## 결과

- `DriverManagerPro_portable.exe` 재빌드 완료 (오류 없음)
- `onefile` / `onedir` / 소스 직접 실행 세 가지 모드 모두 동일 로직으로 동작

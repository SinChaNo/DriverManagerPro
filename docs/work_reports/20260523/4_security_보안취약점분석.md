# 보안 취약점 분석 보고서

- 작업 일자: 2026-05-23
- 작업 유형: security
- 작업자: Claude

---

## 개요

DriverManagerPro 프로젝트 전체 소스 코드를 대상으로 정적 보안 취약점 분석을 수행하였다.
총 **7개의 취약점**이 발견되었으며 Critical 1건, High 3건, Medium 2건, Low 1건으로 분류된다.

---

## 취약점 목록

| # | 취약점 | 파일 | 라인 | 심각도 |
|---|--------|------|------|--------|
| 1 | 관리자 재실행 시 커맨드 인젝션 | driver_install.py | 415 | Critical |
| 2 | 배치 스크립트 생성 시 경로 인젝션 | selfupdate.py | 162-169 | High |
| 3 | 다운로드 파일명 경로 순회 | downloader.py | 226-231 | High |
| 4 | 서브프로세스 실행 시 입력 미검증 | driver_install.py | 187-189 | High |
| 5 | 매니페스트 역직렬화 스키마 미검증 | driver_compare.py | 129-135 | Medium |
| 6 | 다운로드 URL 미검증 | driver_install.py | 298-307 | Medium |
| 7 | 정규식 ReDoS 취약점 | driver_compare.py | 82-122 | Low |

---

## 상세 분석

### 1. [Critical] 관리자 재실행 시 커맨드 인젝션

**파일:** `core/driver_install.py:415`

**설명:** `relaunch_as_admin()` 함수에서 `sys.argv`를 아무 검증 없이 직접 연결하여 관리자 권한으로 실행한다. 공격자가 특수 문자가 포함된 인수를 전달하면 관리자 권한으로 임의 명령이 실행될 수 있다.

**취약 코드:**
```python
params = " ".join(sys.argv)  # 검증 없이 직접 연결
ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
```

**조치 방안:**
```python
import shlex
# 허용된 인수만 필터링 후 이스케이프 처리
params = " ".join(shlex.quote(arg) for arg in sys.argv[1:] if arg.startswith("--"))
ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
```

---

### 2. [High] 배치 스크립트 생성 시 경로 인젝션

**파일:** `core/selfupdate.py:162-169`

**설명:** 업데이트 적용 시 생성하는 배치 스크립트에 검증되지 않은 경로 변수를 삽입한다. 경로에 따옴표나 줄바꿈 문자가 포함된 경우 임의 명령이 주입될 수 있다.

**취약 코드:**
```python
f'move /y "{new_exe}" "{current_exe}"\n'   # 경로 미검증
f'start "" "{current_exe}"\n'
```

**조치 방안:**
- 경로 문자열에서 따옴표, 줄바꿈 등 특수 문자를 제거하거나 이스케이프 처리
- `os.path.normpath()`로 경로 정규화 후 기대 디렉토리 내 경로인지 검증

---

### 3. [High] 다운로드 파일명 경로 순회 (Path Traversal)

**파일:** `core/downloader.py:226-231`

**설명:** URL의 마지막 세그먼트를 파일명으로 사용할 때 `../` 등 경로 순회 시퀀스를 검증하지 않는다. 조작된 URL을 통해 의도하지 않은 디렉토리에 파일이 저장될 수 있다.

**취약 코드:**
```python
filename = url.rstrip("/").split("/")[-1]  # 경로 순회 미검증
dest_file = dest_dir / filename
```

**조치 방안:**
```python
import os
filename = os.path.basename(url.rstrip("/").split("/")[-1])
filename = filename.replace("..", "_")
dest_file = dest_dir / filename
# 최종 경로가 dest_dir 내에 있는지 확인
if not str(dest_file.resolve()).startswith(str(dest_dir.resolve())):
    raise ValueError(f"경로 순회 감지: {dest_file}")
```

---

### 4. [High] 서브프로세스 실행 시 입력 미검증

**파일:** `core/driver_install.py:187-189`

**설명:** `_run_vendor_exe()` 함수에서 EXE 경로가 심볼릭 링크인지, 실제 파일인지 충분히 검증되지 않는다. 악의적인 매니페스트가 심볼릭 링크를 통해 임의 실행 파일을 지정할 수 있다.

**조치 방안:**
- 실행 전 `exe_path.resolve()`로 실제 경로 확인
- 심볼릭 링크 여부 검사 (`exe_path.is_symlink()`)
- 예상 드라이버 디렉토리 내에 있는 경로인지 검증

---

### 5. [Medium] 매니페스트 역직렬화 스키마 미검증

**파일:** `core/driver_compare.py:129-135`

**설명:** `load_manifest()`에서 JSON을 불러올 때 스키마 검증이 없다. 악의적인 매니페스트가 경로 순회 값이나 비정상 데이터를 포함할 경우 하위 로직에서 예기치 않은 동작이 발생할 수 있다.

**조치 방안:**
- 필수 필드 존재 여부 검증 (`id`, `vendor`, `versions`)
- `path` 필드에 `..` 또는 절대 경로 포함 여부 검증
- 버전 문자열 길이 및 형식 제한

---

### 6. [Medium] 다운로드 URL 미검증

**파일:** `core/driver_install.py:298-307`

**설명:** 매니페스트의 `download_url` 값을 검증 없이 사용한다. `file://`, `ftp://` 등 비정상 스킴이나 허용되지 않은 도메인에서 파일을 다운로드하는 공격이 가능하다.

**조치 방안:**
```python
from urllib.parse import urlparse

def _validate_download_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    approved_domains = {
        "us.download.nvidia.com",
        "international.download.nvidia.com",
        "drivers.amd.com",
        "downloadmirror.intel.com",
        "download.intel.com",
    }
    return parsed.netloc in approved_domains
```

---

### 7. [Low] 정규식 ReDoS 취약점

**파일:** `core/driver_compare.py:82-122`

**설명:** 하드웨어 ID 매칭에 사용되는 정규식 패턴 `VEN_([0-9A-Fa-f]{4}).*DEV_`의 `.*`가 조작된 긴 하드웨어 ID 입력 시 지수적 역추적(catastrophic backtracking)을 일으킬 수 있다.

**조치 방안:**
- 하드웨어 ID 최대 길이 제한 (`MAX_HWID_LEN = 256`)
- `.*` 패턴을 `[^A-Za-z0-9]*` 또는 `\s*`처럼 더 구체적인 패턴으로 교체
- Python 3.11 이상의 `re.timeout` 파라미터 활용 검토

---

## 추가 보안 관찰 사항

| 항목 | 파일 | 설명 |
|------|------|------|
| SSL 인증서 고정 미적용 | vendor_api.py, downloader.py | HTTPS 사용 중이나 인증서 고정(pinning) 없어 MITM 공격에 취약 |
| 로그 정보 노출 | core/logger.py | 전체 실행 경로, 오류 메시지가 로그에 기록되어 정보 노출 가능성 |
| 서브프로세스 오류 처리 미흡 | driver_install.py:147-169 | 일부 예외 상황에서 민감 정보가 로그에 노출될 수 있음 |

---

## 우선순위별 조치 권고

**즉시 조치 (Priority 1 - Critical/High):**
1. `relaunch_as_admin()` 인수 이스케이프 처리
2. 다운로드 파일명 경로 순회 방지
3. 배치 스크립트 경로 검증

**단기 조치 (Priority 2 - Medium):**
4. 매니페스트 스키마 검증 추가
5. 다운로드 URL 화이트리스트 검증

**장기 조치 (Priority 3 - Low/관찰):**
6. 정규식 복잡도 제한
7. SSL 인증서 고정 검토
8. 로그 민감 정보 마스킹

---

## 영향 파일

- `core/driver_install.py`
- `core/selfupdate.py`
- `core/downloader.py`
- `core/driver_compare.py`
- `core/vendor_api.py`
- `core/logger.py`

# 보안 취약점 패치 작업 보고서

- 작업 일자: 2026-05-23
- 작업 유형: fix
- 작업자: Claude

---

## 개요

보안 취약점 분석 보고서(4_security_보안취약점분석.md)에서 식별된 7개 취약점에 대해 순서대로 코드 수정 조치를 완료하였다.

---

## 수정 항목

### 1. [Critical] relaunch_as_admin() 커맨드 인젝션

**파일:** [core/driver_install.py](../../../core/driver_install.py)

**변경 내용:**
- `" ".join(sys.argv)` → `subprocess.list2cmdline(sys.argv[1:])`
- Windows 명령줄 규칙에 따라 따옴표·공백이 포함된 인수를 안전하게 이스케이프
- `sys.argv[0]`(스크립트 경로) 제외, 나머지 인수만 전달

---

### 2. [High] 배치 스크립트 경로 인젝션

**파일:** [core/selfupdate.py](../../../core/selfupdate.py)

**변경 내용:**
- 배치 스크립트 생성 전 `new_exe`, `current_exe` 경로에 `"`, `\n`, `\r`, `&`, `|`, `<`, `>` 포함 여부 검증
- 위험 문자 발견 시 다운로드된 파일 삭제 후 즉시 `False` 반환

---

### 3. [High] 다운로드 파일명 경로 순회 (Path Traversal)

**파일:** [core/driver_install.py](../../../core/driver_install.py), [core/downloader.py](../../../core/downloader.py)

**변경 내용 (driver_install.py `_download_driver`):**
- `url.split("/")[-1]` → `Path(raw_name).name` 으로 디렉토리 구성요소 제거
- `.replace("..", "_")` 추가 방어
- `dest_file.resolve().relative_to(dest_dir.resolve())` 로 최종 경로가 dest_dir 내부인지 검증

**변경 내용 (downloader.py):**
- `_local_file_exists()`: 파일명 추출에 `Path(raw_name).name` 적용, `candidate` None 가드 추가
- `_collect_download_tasks()`: 파일명 추출에 `Path(raw_name).name` 적용

---

### 4. [High] EXE 실행 전 심볼릭 링크/경로 탈출 검증

**파일:** [core/driver_install.py](../../../core/driver_install.py) — `_run_vendor_exe()`

**변경 내용:**
- `exe_path.resolve()` 로 실제 경로 확인
- `real_path.relative_to(get_base_dir().resolve())` 로 프로젝트 기본 디렉토리 이탈 여부 검증
- 이탈 감지 시 즉시 `False` 반환 및 오류 로깅

---

### 5. [Medium] 매니페스트 스키마 검증

**파일:** [core/driver_compare.py](../../../core/driver_compare.py)

**변경 내용:**
- `_validate_manifest_schema(data)` 함수 신규 추가
  - `data`가 dict인지 검증
  - `drivers` 필드가 list인지 검증
  - 각 버전의 `path` 필드에 `..` 또는 절대경로(`/` 시작) 포함 여부 검증
- `load_manifest()` 에서 JSON 로드 후 즉시 스키마 검증 호출
- `ValueError` 발생 시 빈 manifest 반환 및 오류 로깅

---

### 6. [Medium] 다운로드 URL 도메인 화이트리스트 검증

**파일:** [core/driver_install.py](../../../core/driver_install.py)

**변경 내용:**
- `_ALLOWED_DOWNLOAD_DOMAINS` frozenset 상수 추가 (NVIDIA, AMD, Intel, Realtek, GitHub)
- `_validate_download_url(url)` 함수 추가
  - `https` 스킴 외 차단 (`file://`, `ftp://` 등 차단)
  - 허용 도메인 외 차단
- `install_driver()` 내 다운로드 전 `_validate_download_url()` 호출 추가

---

### 7. [Low] 정규식 ReDoS 방지

**파일:** [core/driver_compare.py](../../../core/driver_compare.py) — `_hardware_ids_match()`

**변경 내용:**
- `_MAX_HWID_LEN = 256` 상수 추가 — 초과 HWID 건너뜀
- PCI 패턴: `VEN_...*DEV_` → `VEN_...[^&]*DEV_` (& 구분자 경계 제한으로 역추적 폭발 방지)
- USB 패턴: `VID_...*PID_` → `VID_...[^&]*PID_` (동일)
- 길이 초과 HWID 경고 로그 추가

---

## 변경 파일 요약

| 파일 | 변경 취약점 |
|------|-------------|
| core/driver_install.py | 1, 3, 4, 6 |
| core/selfupdate.py | 2 |
| core/downloader.py | 3 |
| core/driver_compare.py | 5, 7 |

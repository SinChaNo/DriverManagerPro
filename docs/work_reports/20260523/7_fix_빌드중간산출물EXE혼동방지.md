# 빌드 중간 산출물 EXE 혼동 방지 작업 보고서

- 작업 일자: 2026-05-23
- 작업 유형: fix
- 작업자: Claude

---

## 개요

onedir 빌드 시 `dist\DriverManagerPro.exe`(실행 불가한 중간 산출물)와
`dist\DriverManagerPro\DriverManagerPro.exe`(실제 실행 파일)가 공존하여
사용자가 잘못된 EXE를 실행하는 문제를 수정하였다.

---

## 원인

PyInstaller onedir 빌드 과정:
1. `EXE()` 단계: `dist\DriverManagerPro.exe` 생성 (DLL 없는 부트로더)
2. `COLLECT()` 단계: 모든 파일을 `dist\DriverManagerPro\`로 수집 (최종 산출물)

`EXE()` 단계의 중간 파일이 삭제되지 않고 남아 사용자가 이를 실행하면
`dist\_internal\python311.dll` 경로에서 DLL을 찾으려다 실패한다.
실제 DLL은 `dist\DriverManagerPro\_internal\`에만 존재한다.

---

## 수정 내용

**파일:** `build.py`

- `_remove_stale_exe()` 헬퍼 함수 추가
  - 빌드 **전** 선제 삭제 (`pre_build=True`): 잠금 전 제거
  - 빌드 **후** 재시도 (`pre_build=False`): 잔여 파일 정리
  - `PermissionError` 시 올바른 실행 경로 안내 메시지 출력
- `run_build()`에서 onedir 모드일 때 빌드 전/후 각각 호출

---

## 올바른 실행 파일 경로

```
dist\DriverManagerPro\DriverManagerPro.exe
```

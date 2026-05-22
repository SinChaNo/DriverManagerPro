# 포터블 EXE 빌드

- 날짜: 2026-05-22
- 작업 유형: build
- 작업자: Claude

## 목표

DriverManagerPro를 테스트 배포용 단일 포터블 EXE 파일로 빌드한다.

## 작업 내용

### 1. 환경 진단

- Python 3.14.5 환경 확인
- 의존성 전무 상태 (pip에 pip만 존재)
- `pywebview>=6.2.1`의 의존성인 `pythonnet 2.5.2`가 Python 3.14에서 빌드 불가 확인
  - nuget.exe 빌드 단계에서 `CalledProcessError` 발생

### 2. 의존성 설치 전략

`pythonnet`은 Python 3.14 미지원(소스 빌드 실패)이므로, pywebview의 EdgeChromium(WebView2) 백엔드를 활용하는 방향으로 우회 설치:

| 패키지 | 설치 방법 | 비고 |
|---|---|---|
| wmi, psutil, requests, packaging | 일반 설치 | 정상 |
| pyinstaller, pillow, pywin32 | 일반 설치 | 정상 |
| pywebview | `--no-deps` | pythonnet 제외 |
| proxy_tools, bottle, typing_extensions | 별도 설치 | pywebview 런타임 의존성 |
| pythonnet | **미설치** | Python 3.14 미지원, EdgeChromium 백엔드로 대체 |

Windows 10/11에는 WebView2 런타임이 기본 내장되어 있으므로 pythonnet 없이도 정상 동작한다.

### 3. EXE 빌드

기존 `build.py --onefile` 실행으로 PyInstaller 단일 파일 빌드 수행:

```
python build.py --onefile
```

- UAC 관리자 권한 매니페스트 포함
- UPX 압축 적용
- tkinter, matplotlib, scipy, numpy 제외로 크기 최소화

### 4. build.py 버그 수정

빌드 성공 메시지 출력 시 em dash(`—`) 문자가 Windows CP949 환경에서 인코딩 오류 발생:

```python
# 수정 전
print(f"  Build OK — output in {DIST}")

# 수정 후
print(f"  Build OK - output in {DIST}")
```

## 결과

| 항목 | 내용 |
|---|---|
| 출력 파일 | `dist/DriverManagerPro_portable.exe` |
| 파일 크기 | 16.97 MB |
| 빌드 방식 | onefile (단일 포터블 EXE) |
| 관리자 권한 | UAC requireAdministrator 포함 |
| 지원 OS | Windows 10 / Windows 11 (64-bit) |

## 변경 파일

- `build.py`: em dash → 하이픈 수정 (CP949 인코딩 오류 수정)
- `assets/icon.ico`: 빌드 시 자동 생성 (블루 원형 아이콘)
- `assets/app.manifest`: 빌드 시 자동 생성 (UAC 매니페스트)
- `DriverManagerPro_onefile.spec`: PyInstaller 스펙 파일 (자동 생성)
- `dist/DriverManagerPro_portable.exe`: 빌드 산출물

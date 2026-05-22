# pywebview EdgeChromium 백엔드 강제 지정

- 날짜: 2026-05-22
- 작업 유형: fix
- 작업자: Claude

## 문제

`DriverManagerPro_portable.exe` 실행 시 아래 오류 발생:

```
webview.errors.WebViewException: You must have pythonnet installed in order to use pywebview.
  File "webview#__init__.py", line 248, in start
  File "webview#guilib.py", line 135, in initialize
```

## 원인 분석

pywebview는 Windows에서 기본적으로 `winforms` 백엔드를 선택한다.
`winforms` 백엔드는 .NET/WinForms를 Python에서 사용하기 위해 `pythonnet`을 필요로 한다.

`pythonnet 2.5.2`는 Python 3.14 환경에서 소스 빌드가 불가능하여 미설치 상태이므로,
백엔드를 명시적으로 `edgechromium`(WebView2)으로 지정해야 한다.

| 백엔드 | pythonnet 필요 | 비고 |
|---|---|---|
| `winforms` | 필요 (기본값) | Python 3.14에서 pythonnet 설치 불가 |
| `edgechromium` | 불필요 | Windows 10/11 기본 내장 WebView2 활용 |

## 수정 내용

**파일:** `main.py`

```python
# 수정 전
webview.start(debug=False)

# 수정 후
webview.start(gui="edgechromium", debug=False)
```

`webview.start()`의 `gui` 파라미터에 `"edgechromium"`을 명시하여
pythonnet 없이 Windows 내장 WebView2 런타임을 사용하도록 강제한다.

## 결과

- `DriverManagerPro_portable.exe` 재빌드 완료 (오류 없음)
- Windows 10/11 기본 탑재 WebView2로 UI 렌더링

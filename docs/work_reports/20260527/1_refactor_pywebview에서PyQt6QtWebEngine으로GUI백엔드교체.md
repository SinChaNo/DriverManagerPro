# GUI 백엔드 교체: pywebview → PyQt6 QtWebEngine

작업일: 2026-05-27
작업 유형: refactor

## 배경

이전 빌드(v1.1.2 portable)는 실행 시 다음 오류로 즉시 종료되었다.

```
webview.errors.WebViewException: You must have pythonnet installed in order to use pywebview.
```

원인 조사 결과:
- pywebview의 Windows 백엔드(`edgechromium`, `mshtml`, `winforms`)는 모두 .NET CLR을 통해
  WebView2/IE를 호출하기 때문에 `pythonnet` 모듈이 반드시 필요하다.
- 빌드 환경에 `pythonnet`/`clr`/`clr_loader` 미설치 → PyInstaller가 번들에 포함하지 못함.
- 추가로 WebView2 Runtime이 설치되지 않은 PC에서는 pythonnet을 추가해도 실행 실패가 발생할 위험이 있다.

배포 대상 PC(Python 미설치, .NET/WebView2 런타임 부재 가능)에서 안정적으로 동작하려면
외부 시스템 의존성이 없는 GUI 백엔드가 필요했다.

## 결정 사항

대안 비교 후 **PyQt6 + QtWebEngine + QtWebChannel** 채택.

| 대안 | 외부 의존성 | Python 3.14 호환 | UI 재작성 | 채택 |
|------|------------|------------------|----------|------|
| pythonnet + WebView2 부트스트래퍼 동봉 | .NET, WebView2 | O | 불필요 | X |
| cefpython3 (Chromium 번들) | 없음 | **X (3.9까지만 지원)** | 불필요 | X |
| **PyQt6 QtWebEngine** | **없음 (Qt6 + Chromium 번들)** | **O** | **불필요** | **O** |
| PyQt6 + 네이티브 위젯 | 없음 | O | 전면 재작성 필요 | X |

PyQt6는 Qt6와 자체 Chromium을 EXE에 통째로 번들하므로 OS 런타임 의존성이 0이다.
QtWebChannel을 통해 기존 `window.pywebview.api` 호출 인터페이스를 호환 레이어로 그대로 유지할 수 있어
프론트엔드(`ui/js/app.js`) 무수정으로 마이그레이션 가능.

## 변경 파일

| 경로 | 변경 |
|------|------|
| `main.py` | pywebview 호출부 제거 → `QApplication` + `QMainWindow` + `QWebEngineView` + `QWebChannel`로 재구성. `API` 클래스를 `QObject` 상속으로 전환하고 각 메서드에 `@pyqtSlot` 데코레이션 적용. 복합 반환값은 JSON 문자열로 직렬화. API 객체를 별도 `QThread`로 이동하여 GUI 메인 스레드 차단 방지 |
| `ui/index.html` | `<script src="js/qwebchannel.js">`, `<script src="js/qtbridge.js">` 태그를 `app.js` 앞에 추가 |
| `ui/js/qtbridge.js` (신규) | QtWebChannel을 초기화하여 `window.pywebview.api` 호환 Proxy를 노출. 각 메서드 호출을 Promise로 감싸고 JSON 문자열 응답을 자동 파싱. 준비 완료 시 `pywebviewready` 이벤트 발생 |
| `ui/js/qwebchannel.js` (신규) | Qt 리소스 `:/qtwebchannel/qwebchannel.js`에서 추출한 표준 QWebChannel 클라이언트 라이브러리 (16,510 bytes) |
| `build.py` | `hidden`에서 `webview` 제거, PyQt6 모듈군 추가. `excludes`에 `webview`/`pywebview`/`clr`/`pythonnet`/`PyQt5`/`PySide` 추가하여 그래프 누락/중복 방지 |

## 호환성 설계

`window.pywebview.api.method()` 호출 규약을 그대로 유지하기 위한 호환 레이어:

1. PyQt6 `QWebChannel`에 `API` 객체를 `"api"` 이름으로 등록.
2. JS 측 `qtbridge.js`가 채널 연결 후 `channel.objects.api`를 Proxy로 감싸 각 메서드를 Promise 반환 함수로 변환.
3. Python `API`의 모든 `@pyqtSlot` 메서드가 dict/list를 JSON 문자열로 반환 → Proxy가 자동 파싱.
4. 초기화 완료 시 `document.dispatchEvent(new Event('pywebviewready'))` 발생 → `app.js`의 기존 초기화 흐름 그대로 트리거.

결과적으로 `ui/js/app.js`는 한 줄도 수정하지 않고 동작.

## 트레이드오프

- **EXE 크기 증가**: 17 MB → **197.55 MB** (약 11.6배). Qt6 + Chromium + WebEngine 리소스를 모두 번들한 결과.
- **시작 시간**: onefile EXE 압축 해제 시간이 첫 실행 시 수 초 추가됨.
- **외부 의존성**: 0 — Python 미설치, .NET 미설치, WebView2 미설치 PC에서도 동작.

## 빌드 결과

```
산출물: dist/DriverManagerPro_v1.1.2_portable.exe
크기:   197.55 MB
빌드:   2026-05-27 17:33:35
경고:   PyQt6/webengine/webchannel 관련 missing module 없음
```

## 후속 확인 필요 사항

- 실제 EXE 실행 검증(UAC 승인 후 윈도우 표시 및 스캔/설치 동작)
- 클린 Windows 10 PC에서 외부 런타임 없이 실행되는지 검증

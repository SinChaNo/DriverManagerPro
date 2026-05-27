# QtWebEngine 외부 CDN 리소스 차단으로 UI 깨짐 수정

작업일: 2026-05-27
작업 유형: fix

## 증상

PyQt6 QtWebEngine으로 GUI 백엔드 교체 후 EXE 실행 시:
- Tailwind CSS 클래스가 전혀 적용되지 않음 (모든 스타일/레이아웃 깨짐)
- Material Symbols 아이콘이 텍스트 그대로 노출 (`memory`, `radar`, `cloud_download` 등)
- Google Fonts (Space Grotesk, Fira Code) 미적용
- `is-hidden`, `fixed`, `w-96` 등의 클래스 무시 → 설정 드로어가 항상 본문에 노출

## 원인

QtWebEngine의 기본 보안 정책:
- `file://` 스킴으로 로드된 페이지에서 `https://` 외부 리소스 접근 차단
- 관련 설정: `QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls` (기본 False)

`ui/index.html`은 다음 CDN 리소스에 의존:
- `https://cdn.tailwindcss.com` — Tailwind CSS JIT 컴파일러
- `https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined...` — 아이콘 폰트
- `https://fonts.googleapis.com/css2?family=Space+Grotesk...&family=Fira+Code...` — 본문 폰트

이전 pywebview(EdgeChromium 백엔드)에서는 이 정책이 기본 허용이었으나, QtWebEngine은
기본 차단이므로 GUI 백엔드 교체 후 동일 HTML이 다르게 동작.

## 수정 내용

### `main.py`

`QWebEngineView` 생성 직후 `view.settings()`에 다음 두 속성을 활성화:

```python
from PyQt6.QtWebEngineCore import QWebEngineSettings

web_settings = view.settings()
web_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
web_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
```

- `LocalContentCanAccessRemoteUrls=True` — file:// 페이지가 https:// 리소스 로드 허용
- `LocalContentCanAccessFileUrls=True` — file:// 페이지가 다른 file:// 리소스(이미지, JS, CSS) 로드 허용 (대부분 기본 True지만 명시)

## 재빌드 결과

```
산출물: dist/DriverManagerPro_v1.1.2_portable.exe
크기:   197.55 MB
빌드:   2026-05-27 17:51:01
```

## 후속 고려 사항

CDN 의존은 오프라인 환경에서 동일 문제를 재발시킨다. 추후 다음 옵션 검토 필요:
- Tailwind 정적 CSS 빌드 후 `ui/css/` 번들 (CDN 의존 제거)
- Material Symbols 폰트 파일을 `ui/` 폴더에 번들
- 본문 폰트도 동일하게 로컬 번들

본 수정은 인터넷 연결이 있는 환경에서의 UI 깨짐을 해결하는 즉시 조치이며,
오프라인 완전 대응은 별도 작업으로 분리.

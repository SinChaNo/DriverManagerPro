# pywebviewready 이벤트 디스패치 대상 불일치 수정

작업일: 2026-05-28
작업 유형: fix

## 증상

PyQt6 QtWebEngine 백엔드로 교체된 EXE 실행 시:
- UI는 정상 표시되지만 헤더의 온라인 상태가 "확인 중..." 그대로 멈춤
- 시스템 카드(CPU/RAM/GPU/BIOS)가 전부 "정보 없음"
- 드라이버 목록이 항상 비어 있음 ("일치하는 드라이버가 없습니다")
- 자동 스캔 / DB 감지 / 콘솔 로그 전부 미동작

UI 렌더링 자체는 문제 없으나 **`init()` 함수가 한 번도 호출되지 않은 상태**.

## 원인

`pywebviewready` 이벤트의 디스패치 대상과 수신 대상이 일치하지 않음.

| 파일 | 위치 | 동작 |
|------|------|------|
| ui/js/qtbridge.js | line 80 | `document.dispatchEvent(new Event('pywebviewready'))` |
| ui/js/app.js | line 993 | `window.addEventListener('pywebviewready', init)` |

`new Event(name)`은 `bubbles` 기본값이 `false`이므로 `document`에 디스패치된 이벤트는 `window`까지 버블링하지 않는다. 결과적으로 `init()`이 호출되지 않아 모든 후속 API 호출(`is_online`, `get_system_summary`, `has_driver_db` 등)이 발생하지 않는다.

app.js line 971에 fallback으로 `document.addEventListener`가 있으나, 이 fallback은 `init()` 내부에서 등록되므로 init()이 한 번도 실행되지 않은 현재 상황에서는 도움이 되지 않는다.

기존 pywebview의 EdgeChromium 백엔드는 `window`에 직접 디스패치하므로 이 문제가 발생하지 않았다.

## 수정 내용

### `ui/js/qtbridge.js`

`pywebviewready` 이벤트를 `window`와 `document` 양쪽에 모두 디스패치하도록 변경. 양쪽 listener 형태 모두를 지원하여 미래의 코드 변경에도 안전.

```js
// Before
document.dispatchEvent(new Event('pywebviewready'));

// After
window.dispatchEvent(new Event('pywebviewready'));
document.dispatchEvent(new Event('pywebviewready'));
```

### `config/app_version.json`

버전을 v1.1.3 → v1.1.4로 패치 증가, `build_date`를 2026-05-28로 갱신.

## 재빌드 결과

```
산출물: dist/DriverManagerPro_v1.1.4_portable.exe
크기:   197.55 MB
빌드:   2026-05-28 12:35:52
```

## 검증

EXE 실행 후 다음 동작을 확인:
- 헤더 온라인 상태가 "온라인" 또는 "오프라인"으로 갱신되는지
- CPU/RAM/GPU 카드에 실제 시스템 정보가 표시되는지
- DB 존재 시 자동 스캔이 트리거되어 드라이버 목록이 채워지는지

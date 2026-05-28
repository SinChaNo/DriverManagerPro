# UI 폰트 로컬 번들 및 NVIDIA 최신 버전 수동 갱신

작업일: 2026-05-28
작업 유형: fix

## 증상

1. **UI 아이콘 누락**: Material Symbols 아이콘(스캔, 검색, cloud_download, settings 등)이
   전부 표시되지 않음. 헤더가 "확인 중..."에 멈춰 init이 늦게 시작되는 인상까지 줌.
2. **그래픽 카드 "최신" 판정 오류**: 사용자 NVIDIA GPU가 v572.83 이상이면 "최신"으로
   표시되지만 실제 NVIDIA 공식 최신은 v610.47 (2026-05-26).

## 근본 원인

### 1. Material Symbols 폰트 CDN 의존
[ui/index.html](DriverManagerPro/ui/index.html#L10)이 `fonts.googleapis.com`에서 Material
Symbols 폰트를 로드했음. QtWebEngine의 SSL/네트워크 상태에 따라 폰트 woff2 파일이
간헐적으로 로드되지 않아 아이콘 전체가 사라지는 현상.

### 2. NVIDIA GFE API의 pfid 무효화
v1.1.8 새 로깅으로 정확한 응답 확인:
```
NVIDIA API: pfid=816 → 1개 결과 수신
첫 항목 raw={'downloadInfo': {'Success': '0', 'ID': '',
  'Messaging': [{'MessageCode': 'DriverDownloadIDNotFound',
                 'MessageValue': 'The Driver Download not found for Manual Lookup requested'}]}}
```

NVIDIA가 제품ID/API 체계를 개편하여 기존 `pfid=816` (GeForce Desktop DCH)이 무효화.
응답 HTTP 200이지만 내용은 명시적 실패 메시지. 자동 갱신 불가 상태.

## 수정 내용

### 1. `ui/fonts/` 디렉토리 신규 + 폰트 로컬 번들
PowerShell로 Google Fonts CSS를 파싱 후 다음 7개 woff2를 다운로드 → `ui/fonts/`:
- `material-symbols-outlined.woff2` (3.94 MB) — 아이콘
- `space-grotesk-{400,500,600,700}.woff2` — 본문 폰트
- `fira-code-{400,500}.woff2` — 모노스페이스 폰트

### 2. `ui/index.html`
Google Fonts `<link>` 3개 제거. 로컬 번들로 대체.

```html
<!-- Before -->
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk..." rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined..." rel="stylesheet"/>

<!-- After -->
<!-- 폰트는 로컬 번들로 제공 (CDN 의존 제거) — css/style.css의 @font-face 참조 -->
```

### 3. `ui/css/style.css`
파일 상단에 `@font-face` 7개 선언 + `.material-symbols-outlined` 클래스 정의 추가.
`font-display: block`으로 아이콘 폰트가 로드되기 전 fallback 텍스트가 노출되는
현상 방지.

### 4. `drivers/manifest.json`
NVIDIA GeForce Desktop/Notebook DCH의 `versions[0]`을 v610.47 (2026-05-26)로 갱신.
v572.83은 `tag: "previous"`로 강등.

```json
{
  "version": "610.47",
  "date": "2026-05-26",
  "tag": "latest",
  "path": "nvidia/geforce/desktop/v610.47",
  "download_url": "https://us.download.nvidia.com/Windows/610.47/...",
  "size_mb": 978
}
```

NVIDIA의 `us.download.nvidia.com` 도메인은 안정적이고 표준 URL 패턴을 유지하므로
직접 다운로드는 가능. 다만 NVIDIA API 자동 갱신은 pfid 무효화로 불가.

### 5. `core/vendor_api.py`
NVIDIA API 응답에서 `Success="0"` + `Messaging` 코드를 명시적으로 감지하여
경고 로그 출력 후 정적 manifest 유지. 이전에는 "유효 항목 없음"으로만 표시되어
원인 파악이 어려웠음.

```python
if first_info.get("Success") == "0":
    msg_codes = [m.get("MessageCode", "") for m in messages if isinstance(m, dict)]
    logger.warning(
        "NVIDIA API: pfid=%s 가 더 이상 유효하지 않음 (Success=0, 메시지=%s). "
        "NVIDIA가 제품ID/API 구조를 개편한 것으로 추정. manifest 정적 버전 유지.",
        pfid, msg_codes,
    )
    return None
```

### 6. `build.py`
`datas`에 이미 `ui` 디렉토리 전체가 포함되어 있어 `ui/fonts/`도 자동 번들됨.
별도 수정 불필요.

## "최신 드라이버" 판정 메커니즘 (참고)

| 단계 | 동작 |
|------|------|
| 설치 버전 추출 | `core/hardware_detect.py` — WMI PnPSignedDriver 조회 (실패 시 `pnputil` fallback). NVIDIA는 Windows 4-part(`32.0.15.7283`)를 NVIDIA 2-part(`572.83`)로 자동 변환 |
| 비교 기준 | `drivers/manifest.json`의 `versions[0]` (= `tag: "latest"`) |
| 비교 알고리즘 | `_parse_version`로 점 split → int tuple 변환 후 사전식 비교 |
| 갱신 경로 | 앱 시작 시: 번들 manifest 사용 / "DB 업데이트": vendor API로 자동 갱신 시도 (NVIDIA pfid 무효화 시 정적 유지) |

## 재빌드 결과

```
산출물: dist/DriverManagerPro_v1.1.9_portable.exe
크기:   ~201 MB (폰트 4MB 추가)
빌드:   2026-05-28
```

## 검증

EXE 실행 후 확인:
- 모든 Material Symbols 아이콘이 즉시 표시됨 (네트워크 무관)
- 시스템 카드와 헤더 정보 정상 갱신
- NVIDIA GPU가 v610.47 미만이면 "업데이트 필요 → 610.47"로 표시
- "DB 업데이트" 클릭 시 로그에 `NVIDIA API: pfid=816 가 더 이상 유효하지 않음` 명시

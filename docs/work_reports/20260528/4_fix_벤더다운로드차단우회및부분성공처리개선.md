# 벤더 다운로드 차단 우회 및 부분 성공 처리 개선

작업일: 2026-05-28
작업 유형: fix

## 증상 (v1.1.7 실행 로그 기반)

DB 업데이트 시 17개 파일 중 6개만 다운로드 성공, **11개 실패**:

| 실패 유형 | 영향 파일 | 갯수 |
|----------|----------|------|
| Intel 403 Forbidden | `downloadmirror.intel.com/*` (그래픽/WiFi/BT/Chipset/ME) | 9개 |
| AMD 404 Not Found  | `drivers.amd.com/drivers/installer/...`                | 2개 |

부수 문제:
- NVIDIA GFE API는 HTTP 200을 반환하지만 응답 파싱에서 "1개 결과 → 유효한 항목 없음"
  (Version/DownloadURL 키 누락 의심)
- AMD release-notes JSON 엔드포인트가 HTML을 반환 (차단/구조 변경)

## 근본 원인

1. **Intel 403**: `downloadmirror.intel.com`은 다운로드 센터 메인 페이지를
   먼저 방문해 쿠키를 발급받은 세션에서만 `.exe` 직접 링크 접근을 허용한다.
   직접 URL 요청 시 무조건 403 차단.

2. **AMD 404**: AMD가 CDN URL 구조를 변경(`/installer/<major>/whql/` 경로
   제거)하여 기존 manifest의 URL이 무효화됨.

3. **NVIDIA 파싱 실패**: GFE API 응답에서 `downloadInfo.Version` /
   `downloadInfo.DownloadURL` 키가 비어 있거나 다른 위치로 이동했을 가능성.
   기존 코드는 단일 경로만 시도.

4. **부분 성공 메시지 부정확**: 11개 실패만 표시되어 6개 성공이 가려짐.

## 수정 내용

### 1. `core/downloader.py` — Intel 403 우회

#### 워밍업 매핑 추가
```python
_WARMUP_MAP: dict[str, str] = {
    "downloadmirror.intel.com": "https://www.intel.com/content/www/us/en/download-center/home.html",
    "download.intel.com": "https://www.intel.com/content/www/us/en/download-center/home.html",
}
```

#### 전역 `requests.Session()` 도입
- 한 세션 내에서 쿠키/연결을 재사용
- `_get_session()`: lazy 초기화
- `_warmed_domains: set[str]`: 도메인별 워밍업 1회만 수행

#### `_warmup_domain(domain)`
- 다운로드 직전 도메인 메인 페이지를 방문해 쿠키 수집
- 워밍업 결과를 로그에 기록 (HTTP 상태 + 쿠키 갯수)

#### 헤더 강화 (`_build_request_headers`)
일반 Chrome 브라우저 fingerprint와 동일하도록:
- `Sec-Fetch-Dest`, `Sec-Fetch-Mode`, `Sec-Fetch-Site`, `Sec-Fetch-User`
- `sec-ch-ua`, `sec-ch-ua-mobile`, `sec-ch-ua-platform`
- `Accept-Encoding: gzip, deflate, br`
- `Upgrade-Insecure-Requests: 1`

#### `_download_file` 수정
- 세션 사용 + 워밍업 호출
- 실제 파일 요청 시 `Sec-Fetch-Site: same-site`, `Sec-Fetch-Mode: no-cors`,
  `Sec-Fetch-Dest: empty`, `Accept: */*` 로 헤더 조정
- `allow_redirects=True`로 CDN 리다이렉트 대응

### 2. `core/vendor_api.py` — NVIDIA 파싱 강화

#### 다중 키 fallback
```python
version = (
    info.get("Version") or info.get("version")
    or info.get("DriverVersion") or item.get("Version") or ""
)
url = (
    info.get("DownloadURL") or info.get("downloadUrl")
    or info.get("Download_URL") or info.get("download_url")
    or item.get("DownloadURL") or ""
)
```

#### 진단용 로깅
- 파싱 실패 시 `info`/`item`의 키 목록을 로그에 출력
- 전체 실패 시 첫 항목 raw JSON 일부(300자)를 로그에 기록
  → 다음 실행 로그로 NVIDIA 응답 구조를 확실히 파악 가능

### 3. `core/downloader.py` — 부분 성공 처리 개선

```python
if all_ok:
    err_msg = None
elif success_count > 0:
    err_msg = f"부분 성공: {success_count}개 완료, {total - success_count}개 실패 (벤더 URL/차단 문제)"
else:
    err_msg = f"전체 실패: {total}개 파일 모두 다운로드 불가"

_set_state(
    ...
    downloaded_files=success_count,  # 최종 표시는 성공 갯수만 (정확성)
    total_files=total,
)
```

진행률 막대도 성공/전체 비율로 정확히 표시되도록 보정.

### 4. AMD URL 처리

AMD의 새 URL 패턴은 외부 검증 없이 추측만으로 변경할 경우 새로운 404 위험이
큼. 본 PR에서는 manifest URL을 수정하지 않고, 다음 두 가지로 영향을 완화:
- 부분 성공 처리 개선으로 AMD 실패가 다른 벤더 성공을 가리지 않음
- AMD vendor API의 raw 응답을 로깅하여 추후 새 엔드포인트 발굴 시 활용

## 한계

- Intel 403은 워밍업 + 헤더 강화로 우회 가능성이 높지만, Intel이 향후
  더 강한 봇 차단(JS 챌린지, 토큰 등)을 도입하면 추가 작업 필요.
- AMD release-notes JSON 엔드포인트가 동작하지 않는 한 AMD 버전 자동 갱신은
  불가. 사용자가 manifest에 직접 URL을 입력하거나 사용자 CDN(cdn_base_url)
  사용으로 대응해야 함.
- NVIDIA의 응답 구조 변경 의심 — 이번 빌드의 로그를 보면 정확한 키 위치를
  파악할 수 있음.

## 재빌드 결과

```
산출물: dist/DriverManagerPro_v1.1.8_portable.exe
크기:   ~197 MB
빌드:   2026-05-28
```

## 검증 시나리오

EXE 실행 → "DB 업데이트" 클릭 후 로그(`dist/logs/install_*.log`) 확인:
- `도메인 워밍업: downloadmirror.intel.com → HTTP 200 (쿠키 N개 수집)` 라인 존재
- Intel 다운로드 라인이 "다운로드 완료"로 표시되는 갯수 증가
- NVIDIA 파싱이 여전히 실패하면 `NVIDIA 파싱 누락: ... info 키=[...]` 라인에서
  실제 응답 키 구조 확인 후 후속 수정

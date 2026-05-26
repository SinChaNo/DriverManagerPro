# DriverManagerPro 개선사항 및 발전 방향

- 작성일: 2026-05-23
- 기준 버전: 1.0.0
- 상태: 초안

---

## 현재 구현 수준 요약

| 영역 | 수준 | 비고 |
|------|------|------|
| 핵심 기능 (스캔/비교/설치) | 완성 | 견고하고 안정적 |
| 보안 | 양호 | 취약점 7건 패치 완료 |
| UI/UX | 부분 완성 | 검색·설정 화면 미구현 |
| 벤더 API 연동 | 부분 완성 | NVIDIA/AMD만 동적, Intel/Realtek은 정적 |
| 오류 처리 | 보통 | 프론트엔드 null 체크 부족 |
| 테스트 커버리지 | 보통 | 단위 47개, 통합/E2E 없음 |

---

## 1. 단기 개선사항 (1~2 스프린트 이내)

이 항목들은 현재 코드베이스에 이미 자리(placeholder)가 마련되어 있으나 기능이 없거나 미완성인 부분이다.

### 1-1. 드라이버 검색 기능 구현

**현황:** `ui/index.html`에 검색창(`#searchInput`)이 렌더링되어 있으나 `ui/js/app.js`에서 이벤트 리스너가 연결되지 않아 동작하지 않음.

**개선 방향:**
- `input` 이벤트 리스너를 등록하여 현재 표시된 드라이버 트리를 필터링
- 장치명, 벤더명, 드라이버 ID 기준 실시간 검색
- 검색어 초기화 버튼 추가

**영향 파일:** `ui/js/app.js`

---

### 1-2. 설정 화면 구현

**현황:** 메인 헤더의 설정 아이콘(`btnMainSettings`)이 존재하나 클릭 이벤트가 연결되지 않음. `config/settings.json`은 직접 파일 편집으로만 수정 가능.

**개선 방향:**
- 설정 뷰(v-settings) 추가
- 편집 가능 항목:
  - CDN 기본 URL (cdn_base_url)
  - 유지 버전 수 (keep_versions: 1~5)
  - 로그 레벨 (log_level: DEBUG / INFO / WARNING)
  - 자동 업데이트 확인 (auto_update_check: 토글)
  - 재부팅 안내 (reboot_prompt: 토글)
- 설정 저장 시 `API.save_settings()` 호출

**영향 파일:** `ui/index.html`, `ui/js/app.js`

---

### 1-3. 프론트엔드 오류 처리 강화

**현황:** `app.js`의 `call()` 함수가 API 실패 시 `null`을 반환하지만, 호출 지점 다수에서 null 체크 없이 결과를 직접 사용하여 런타임 오류 발생 가능.

```javascript
// 현재: null 체크 없음
const result = await call('get_update_list');
renderTree(result.items); // result가 null이면 TypeError
```

**개선 방향:**
- 각 API 호출 결과에 null 가드 추가
- 오류 발생 시 사용자에게 토스트/배너 알림 표시
- 네트워크 오류와 앱 로직 오류를 구분하여 메시지 제공

**영향 파일:** `ui/js/app.js`

---

### 1-4. 설치 결과 화면 개선

**현황:** 설치 완료 후 v-complete 뷰에서 성공/실패 요약은 보이지만, 실패한 드라이버에 대한 구체적인 오류 원인이 노출되지 않음.

**개선 방향:**
- 실패 항목 클릭 시 해당 드라이버의 로그 발췌 모달 표시
- 실패 원인 분류 표시 (다운로드 실패 / EXE 오류 / 타임아웃 등)
- 실패한 드라이버만 재시도 버튼 추가

**영향 파일:** `ui/index.html`, `ui/js/app.js`, `core/driver_install.py`

---

### 1-5. Intel/Realtek 벤더 API 연동

**현황:** `core/vendor_api.py`에서 NVIDIA/AMD만 동적 조회하고, Intel과 Realtek은 manifest의 기존 버전을 그대로 유지한다.

**Intel 현황 조사:**
- Intel DSA(Driver & Support Assistant) API 공개 여부 확인 필요
- `downloadcenter.intel.com` RSS 또는 JSON 피드 활용 가능성 검토

**Realtek 현황 조사:**
- 공식 다운로드 페이지 파싱(HTML scraping) 방식 검토
- 버전 패턴: `HD Audio Driver XXXX`

**영향 파일:** `core/vendor_api.py`, `drivers/manifest.json`

---

## 2. 중기 개선사항 (1~2개월)

기능 확장이나 구조적 개선이 필요한 항목이다.

### 2-1. 드라이버 롤백 기능

**필요성:** 드라이버 업데이트 후 시스템 불안정이 발생하는 경우, 현재는 수동 복원만 가능하다.

**구현 방향:**
- 설치 전 기존 INF 정보 또는 드라이버 파일 백업 (pnputil 활용)
- manifest에 이미 previous 버전이 포함되어 있으므로 이를 활용
- 롤백 대상 목록 표시 + 롤백 실행 버튼 추가
- `pnputil /delete-driver` + 이전 버전 재설치 흐름 구현

**영향 파일:** `core/driver_install.py`, `ui/index.html`, `ui/js/app.js`

---

### 2-2. 드라이버 설치 예약 및 자동 업데이트 스케줄링

**필요성:** 현재는 사용자가 수동으로 스캔 및 설치를 실행해야 한다.

**구현 방향:**
- Windows 작업 스케줄러(Task Scheduler) 등록 기능
- 주기 설정: 매주 / 매월 / 수동
- 앱 시작 시 자동 업데이트 확인 여부 설정 (현재 `auto_update_check` 설정은 있으나 비활성)
- 시스템 트레이 아이콘으로 백그라운드 실행 지원

**영향 파일:** 신규 `core/scheduler.py`, `main.py`

---

### 2-3. 드라이버 서명(Hash) 검증

**필요성:** 다운로드된 EXE 파일의 무결성을 현재는 MZ 헤더 + 0바이트 체크만으로 확인한다. 악의적인 파일 교체에 취약할 수 있다.

**구현 방향:**
- manifest에 `sha256` 필드 추가
- 다운로드 완료 후 SHA-256 해시 검증
- 불일치 시 파일 삭제 + 오류 반환
- 벤더 API로 해시값을 수집하거나 자체 CDN에서 관리

**영향 파일:** `core/driver_install.py`, `core/downloader.py`, `drivers/manifest.json`

---

### 2-4. 다국어 지원 (i18n)

**현황:** UI는 한국어로 고정되어 있고 README만 한/영 이중 언어이다.

**구현 방향:**
- `ui/js/i18n.js` 언어 파일 분리 (ko / en)
- `settings.json`에 `language` 필드 추가
- 설정 화면에서 언어 선택 드롭다운
- 동적 텍스트 치환 (`t('key')` 패턴 사용)

**영향 파일:** `ui/js/app.js`, `ui/index.html`, 신규 `ui/js/i18n.js`

---

### 2-5. 설치 이력 관리

**필요성:** 현재 설치 로그는 세션별 파일로만 존재하며, 과거 설치 내역을 앱 내에서 확인할 수 없다.

**구현 방향:**
- 설치 결과를 SQLite 또는 JSON DB에 누적 저장
- 이력 뷰(v-history) 추가: 설치 날짜 / 드라이버명 / 버전 / 결과
- 날짜 필터 및 성공/실패 필터
- CSV 내보내기 기능

**영향 파일:** 신규 `core/history.py`, `main.py`, `ui/index.html`

---

### 2-6. 오프라인 번들 지원 강화

**현황:** `_internal/drivers/manifest.json`이 번들되어 있으나, 앱이 EXE 옆의 `drivers/`를 참조하므로 최초 실행 시 manifest가 없으면 스캔 결과가 0이 된다.

**개선 방향:**
- 최초 실행 시 `_internal/drivers/manifest.json`을 `drivers/`로 자동 복사하는 초기화 로직 추가
- 네트워크 없이도 번들된 버전 기준으로 업데이트 확인 가능하도록 개선
- 번들 manifest 버전과 로컬 manifest 버전 비교 표시

**영향 파일:** `main.py`

---

## 3. 장기 발전 방향 (3~6개월)

제품 성숙도와 사용자 기반 확장을 위한 방향이다.

### 3-1. 기업용 배포 지원

**필요성:** 관리자가 다수 PC에 일괄 배포하거나, 정책 기반으로 드라이버를 관리해야 하는 기업 환경 지원.

**구현 방향:**
- MSI 패키지 지원 (WiX Toolset 또는 Inno Setup 통합)
- 무인 설치 모드: `--silent --auto-install` 명령줄 인수
- 중앙 집중형 manifest 서버 지원 (내부 CDN URL 설정)
- 그룹 정책(GPO) 기반 설정 배포 지원

---

### 3-2. 드라이버 충돌 감지 및 진단

**필요성:** 특정 드라이버 업데이트 후 장치 오동작이 발생하는 경우를 사전/사후에 감지.

**구현 방향:**
- 설치 전후 이벤트 로그 비교 (Windows Event Log 파싱)
- 장치 상태 코드 모니터링 (WMI `Win32_PnPEntity.ConfigManagerErrorCode`)
- 문제 장치 코드 매핑: Code 10(장치 시작 불가), Code 43(알 수 없는 오류) 등
- 설치 후 장치 상태 자동 재확인

---

### 3-3. 커뮤니티 manifest 기여 시스템

**필요성:** 현재 manifest는 NVIDIA/AMD로 한정되어 있으며, 소수 벤더(Logitech, Corsair, Creative 등)의 드라이버는 지원되지 않는다.

**구현 방향:**
- GitHub 기반 manifest 기여 워크플로우 설계
- PR 기반 신규 드라이버 엔트리 추가
- manifest 버전 관리 (semantic versioning)
- 사용자 신고 기능 (잘못된 버전 정보 피드백)

---

### 3-4. 성능 최적화

**대규모 manifest 처리:**
- 수천 개 드라이버 엔트리 시 파싱 성능 개선
- 인덱싱 구조 도입 (vendor/class 기준 사전 그루핑)
- 지연 로딩 (필요한 항목만 로드)

**UI 렌더링 최적화:**
- 드라이버 목록 가상 스크롤(virtual scroll) 도입 (100+ 항목 대응)
- 폴링 간격 동적 조절 (작업 중: 1초, 유휴: 10초)

---

### 3-5. 보안 강화 지속

**코드 서명:**
- EXE 파일 코드 서명 (Authenticode) 적용
- SmartScreen 경고 제거

**샌드박스 격리:**
- 드라이버 설치 프로세스를 별도 격리 프로세스로 분리
- 권한 최소화 원칙 적용 (현재 전체 관리자 권한 필요)

**감사 로그:**
- 설치/변경 작업에 대한 감사 이벤트 Windows 이벤트 로그 기록
- 무단 변경 감지 (manifest 무결성 주기적 확인)

---

## 4. 기술 부채 정리

현재 코드베이스에 존재하는 기술 부채 목록이다.

| 항목 | 파일 | 설명 | 우선순위 |
|------|------|------|----------|
| 최초 실행 시 manifest 미복사 | `main.py` | `_internal/drivers/manifest.json` → `drivers/` 자동 복사 로직 없음 | 높음 |
| app.js null 체크 누락 | `ui/js/app.js` | API 반환값 null 가드 부재 | 높음 |
| 검색창 미연결 | `ui/js/app.js` | `#searchInput` 이벤트 리스너 없음 | 높음 |
| 설정 화면 미구현 | `ui/index.html` | 설정 뷰 없음 | 중간 |
| NVIDIA pfid 하드코딩 | `core/vendor_api.py` | pfid=816/851이 변경되면 수동 업데이트 필요 | 중간 |
| Intel/Realtek 정적 유지 | `core/vendor_api.py` | 벤더 API 없어 버전이 갱신되지 않음 | 중간 |
| 통합/E2E 테스트 부재 | `tests/` | 단위 테스트만 존재 | 중간 |
| UI 언어 하드코딩 | `ui/index.html` | 한국어 고정 | 낮음 |
| manifest 스키마 버전 관리 | `drivers/manifest.json` | schema_version이 있지만 마이그레이션 로직 없음 | 낮음 |

---

## 5. 개선 우선순위 요약

```
[즉시] 오프라인 번들 지원 강화 (manifest 자동 복사)
[즉시] app.js null 체크 보강
[단기] 검색 기능 구현
[단기] 설정 화면 구현
[단기] 설치 결과 화면 상세화
[중기] 드라이버 롤백 기능
[중기] SHA-256 다운로드 무결성 검증
[중기] 설치 이력 관리
[중기] Intel/Realtek 벤더 API 연동
[장기] 기업용 배포 지원
[장기] 드라이버 충돌 감지
[장기] 코드 서명 (Authenticode)
```

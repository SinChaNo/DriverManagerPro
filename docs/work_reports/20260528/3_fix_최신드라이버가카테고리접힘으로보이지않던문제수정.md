# 최신 드라이버가 카테고리 접힘으로 보이지 않던 문제 수정

작업일: 2026-05-28
작업 유형: fix

## 증상

스캔 결과에서 업데이트가 필요하지 않은(`update_available=false`) 드라이버가
사용자 눈에 띄지 않음. 사용자 의도:
> "업데이트 완료되어있는 드라이버는 선택이 안되게 해달라고 했지(전체 선택을
> 눌렀을 시), 아예 안보이게 해달라고는 하지 않았어"

특히 그래픽 카드 드라이버가 표시되지 않는 것으로 보임.

## 근본 원인

[ui/js/app.js:238-239](DriverManagerPro/ui/js/app.js#L238-L239)에서 카테고리
펼침 상태를 업데이트 개수로 결정:

```js
const clsUpdates = devices.filter(d => d.update_available).length;
const isOpen = clsUpdates > 0;  // ← 업데이트 없는 카테고리는 접힘
```

`<details>` 요소가 `open` 속성 없이 시작 → 사용자는 카테고리 헤더만 보이고
내부의 "최신" 드라이버 행은 시각적으로 가려짐.

이전 실행 로그 분석:
```
2026-05-28 12:45:01 [INFO] Version comparison complete: 9 matches, 4 updates available
```

→ 9개 매치 중 5개는 "최신" 상태로 접힌 카테고리 안에 있었음.

## 수정 내용

### `ui/js/app.js`

`isOpen`을 항상 `true`로 설정. 모든 카테고리가 펼친 상태로 표시:

```js
// Before
const isOpen = clsUpdates > 0;

// After
// 카테고리는 항상 펼친 상태로 시작한다. 업데이트가 필요 없는 드라이버도
// 사용자가 확인할 수 있어야 하므로 자동 접힘은 사용하지 않는다.
const isOpen = true;
```

업데이트 가능한 드라이버는 `is-updatable` 클래스로 적색 좌측 경계선이 강조되고,
최신 드라이버는 `is-current` 클래스로 `opacity: 0.7` 흐리게 표시되어 시각적
구분은 유지됨.

"전체 선택" 체크박스 동작은 변경 없음 — 기존대로 `update_available=true`인
드라이버만 선택 대상이며, 최신 드라이버의 체크박스는 `disabled`라 클릭 불가.

### `core/vendor_api.py`

NVIDIA API 호출 시 응답 상태를 더 자세히 로깅하여, DB 업데이트 시 GPU 최신
버전이 갱신되지 않을 때 원인 추적이 용이하도록 함:

```python
logger.info("NVIDIA API 호출: pfid=%s", pfid)
...
logger.info("NVIDIA API: HTTP %s 수신 (pfid=%s)", resp.status_code, pfid)
...
logger.warning("NVIDIA API: pfid=%s 에 대한 결과 없음. 응답 키: %s", pfid, list(data.keys()))
...
logger.info("NVIDIA API: pfid=%s → %d개 결과 수신", pfid, len(ids))
```

## 그래픽 카드가 "최신"으로 표시되는 이슈

번들된 manifest의 NVIDIA GeForce 최신은 **572.83** (2025-02-27).
NVIDIA 공식 최신은 **610.47** (2026-05-26).

→ 사용자가 v572.83 이상을 설치한 상태라면 "최신"으로 표시됨.

해결: 앱의 **"DB 업데이트"** 버튼으로 NVIDIA GFE API에서 최신 버전을 가져와
manifest를 갱신해야 함. 보강된 로그를 통해 DB 업데이트 동작 여부를 추적할 수
있다.

## 재빌드 결과

```
산출물: dist/DriverManagerPro_v1.1.6_portable.exe
크기:   197.55 MB
빌드:   2026-05-28
```

## 검증

EXE 실행 후 확인:
- 모든 드라이버 카테고리가 펼친 상태로 시작
- "최신" 드라이버도 행으로 표시됨 (체크박스는 disabled, "최신" 배지 + 흐림 효과)
- "DB 업데이트" 클릭 시 로그 파일에 `NVIDIA API: HTTP 200` 또는 실패 사유 기록

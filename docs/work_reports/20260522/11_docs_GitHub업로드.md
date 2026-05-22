# GitHub 업로드 작업 보고서

- **날짜:** 2026-05-22
- **작업 유형:** docs
- **담당:** Claude (servot@devman.pe.kr)

---

## 목표

`DriverManagerPro` 프로젝트를 GitHub Public 레포지토리에 업로드

---

## 작업 경위

### 1. 사전 확인

- 프로젝트 경로: `C:\DevProject\videcoding\DriverManagerPro`
- Git 저장소: 이미 초기화 완료 (커밋 13개 존재)
- 원격(remote): 미설정 상태
- 미추적 파일: `assets/` 폴더 (아이콘, app.manifest)

### 2. gh CLI 설치

`gh` CLI가 설치되어 있지 않아 winget으로 설치 진행.

```powershell
winget install --id GitHub.cli --silent --accept-package-agreements --accept-source-agreements
# 설치 버전: gh v2.92.0
```

### 3. GitHub 인증

```
# 사용자가 직접 터미널에서 실행
gh auth login
# → GitHub.com / HTTPS / Login with a web browser 선택
# → 인증 계정: SinChaNo
```

### 4. 초기 푸시 실패 (HTTP 500)

`assets/` 커밋 후 GitHub 레포 생성 및 푸시 시도.

```powershell
gh repo create DriverManagerPro --public --source . --remote origin --push
# → 레포 생성 성공 (https://github.com/SinChaNo/DriverManagerPro)
# → 푸시 실패: HTTP 500 / send-pack: unexpected disconnect
```

**원인 분석:**

```
git count-objects -vH
# → size: 2.12 GiB  ← GitHub 권장 한도(1GB) 초과
```

git 이력에 포함된 대용량 파일 목록:

| 파일 | 크기 |
|------|------|
| `drivers/nvidia/geforce/desktop/v572.83/572.83-desktop-win10-win11-64bit-international-dch-whql.exe` | 805.9 MB |
| `drivers/nvidia/geforce/desktop/v566.36/566.36-desktop-win10-win11-64bit-international-dch-whql.exe` | 699.0 MB |
| `drivers/nvidia/geforce/desktop/v560.94/560.94-desktop-win10-win11-64bit-international-dch-whql.exe` | 668.6 MB |

---

## 해결 방법

### 5. git-filter-repo 설치

```powershell
python -m pip install git-filter-repo
# 설치 경로: C:\Users\chanhyoi\AppData\Local\Python\pythoncore-3.14-64\Scripts\
```

### 6. .gitignore 업데이트

드라이버 바이너리 패키지를 이후 커밋에서 자동 제외하도록 패턴 추가.

```gitignore
# 드라이버 바이너리 패키지 (대용량, git 제외)
drivers/**/*.exe
drivers/**/*.msi
drivers/**/*.zip
drivers/**/*.7z
drivers/**/*.cab
```

### 7. git 이력에서 대용량 파일 제거

```powershell
git filter-repo --path-glob "drivers/**/*.exe" --invert-paths --force
# 처리 결과: 13개 커밋 재작성
# 소요 시간: 약 1초
```

**결과:**

```
git count-objects -vH
# → size-pack: 83.40 KiB  (2.12 GiB → 83 KiB)
```

> 주의: `filter-repo` 실행 시 origin remote가 자동 제거되며 .gitignore 수정 내용도 초기화됨.

### 8. .gitignore 재수정 및 커밋

`filter-repo`가 working tree를 재작성 이력 기준으로 초기화해 .gitignore 수정이 사라짐. 재편집 후 커밋.

```
커밋: modify: .gitignore 드라이버 바이너리 패키지 제외 패턴 추가
```

### 9. 원격 재등록 및 최종 푸시 성공

```powershell
git remote add origin https://github.com/SinChaNo/DriverManagerPro.git
git push -u origin master
# → * [new branch]  master -> master  ✓
```

---

## 최종 결과

| 항목 | 내용 |
|------|------|
| GitHub URL | https://github.com/SinChaNo/DriverManagerPro |
| 공개 여부 | Public |
| 최종 저장소 크기 | 83.4 KiB |
| 푸시된 커밋 수 | 14개 (기존 13 + .gitignore 수정 1) |
| 제거된 파일 | NVIDIA 드라이버 EXE 3개 (총 ~2.17 GiB) |

---

## 주의사항 및 교훈

- **드라이버 바이너리(EXE/ZIP 등)는 git에 포함하지 않는다.** `.gitignore`에 `drivers/**/*.exe` 등 패턴이 등록되어 있으므로 이후 커밋에서 자동 제외됨.
- `git filter-repo` 실행 후 origin remote가 삭제되므로 반드시 재등록 필요.
- `git filter-repo`는 working tree도 재작성하므로 실행 전 local 변경사항은 커밋하거나 별도 보관 필요.
- GitHub 파일 크기 제한: **파일당 100MB**, 레포 권장 크기 1GB 이하.

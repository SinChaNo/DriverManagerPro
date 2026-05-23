# Driver Manager Pro

USB 포터블 Windows 드라이버 관리 도구. 오프라인 번들 드라이버 DB와 벤더 공식 API 자동 갱신을 지원합니다.

---

## 목차

- [요구 사항](#요구-사항)
- [빠른 시작](#빠른-시작-소스-실행)
- [처음 실행](#처음-실행)
- [DB 업데이트](#db-업데이트)
- [오프라인 / USB 모드](#오프라인--usb-모드)
- [빌드](#빌드)
- [드라이버 수동 추가](#드라이버-수동-추가)
- [디렉토리 구조](#디렉토리-구조)
- [참고 사항](#참고-사항)

---

## 요구 사항

- Windows 10 (1903 이상) 또는 Windows 11, x64
- Python 3.11 이상
- 관리자 권한 (UAC 요청 자동 처리)

## 빠른 시작 (소스 실행)

```powershell
cd DriverManagerPro
pip install -r requirements.txt
python main.py
```

## 처음 실행

1. 앱 실행 시 `drivers/manifest.json` 유무를 확인합니다.
2. 파일이 없으면 **환영 화면**이 표시됩니다. **DB 다운로드 시작**을 클릭하세요.
3. 다운로드 완료 후 **하드웨어 스캔**을 클릭하면 설치된 드라이버를 자동 감지합니다.
4. 업데이트할 항목을 선택하거나 **전체 업데이트 설치**를 클릭합니다.

## DB 업데이트

**DB 업데이트** 버튼을 클릭하면 다음 순서로 동작합니다.

1. 네트워크 연결 확인 (오프라인이면 즉시 중단)
2. 벤더 공식 API에서 최신 드라이버 버전 조회
   - **NVIDIA**: GeForce Experience 서비스 API
   - **AMD**: Radeon 릴리스 JSON
   - **Intel / Realtek**: 공개 API 없어 정적 유지
3. `drivers/manifest.json` 자동 갱신 (최신 + 이전 버전 2개 유지)
4. 갱신된 DB 기준으로 미다운로드 드라이버 파일 다운로드

> 핵심 기능(하드웨어 스캔, 버전 비교, 드라이버 설치)은 **인터넷 연결 없이** 동작합니다.
> 네트워크는 DB 업데이트와 드라이버 파일 다운로드 시에만 사용됩니다.

## 오프라인 / USB 모드

`DriverManagerPro/` 폴더 전체(드라이버가 채워진 `drivers/` 포함)를 USB에 복사한 뒤 `DriverManagerPro.exe`를 실행합니다. 별도 설치 불필요.

## 빌드

```powershell
pip install pyinstaller pillow
python build.py             # onedir + onefile(포터블) 동시 빌드
python build.py --onefile   # 포터블 단일 EXE만 빌드
python build.py --onedir    # 폴더 빌드만
```

빌드 결과는 `dist/` 폴더에 생성됩니다.

## 드라이버 수동 추가

1. 드라이버 패키지를 `drivers/<vendor>/<family>/v<version>/` 경로에 배치합니다.
2. `drivers/manifest.json`에 항목을 추가합니다.

```json
{
  "id": "realtek-hd-audio",
  "vendor": "Realtek",
  "class": "Media",
  "name": "Realtek HD Audio Driver",
  "hardware_ids": ["HDAUDIO\\FUNC_01&VEN_10EC&DEV_0867"],
  "versions": [
    {
      "version": "6.0.9563.1",
      "date": "2024-03-01",
      "tag": "latest",
      "path": "realtek/audio/v6.0.9563.1/",
      "inf": "RTKVHD64.inf",
      "size_mb": 120,
      "os": ["win10", "win11"],
      "arch": "x64"
    }
  ]
}
```

3. 앱을 재시작하고 스캔하면 새 드라이버가 업데이트 목록에 나타납니다.

## 디렉토리 구조

```
DriverManagerPro/
├── main.py                   # 진입점
├── build.py                  # PyInstaller 빌드 스크립트
├── requirements.txt
├── core/
│   ├── hardware_detect.py    # WMI 기반 장치 스캐너
│   ├── driver_compare.py     # 시맨틱 버전 비교기
│   ├── driver_install.py     # pnputil / 벤더 EXE 설치기
│   ├── downloader.py         # DB 업데이트 및 파일 다운로드
│   ├── vendor_api.py         # NVIDIA / AMD 벤더 API 조회
│   ├── selfupdate.py         # 앱 자체 업데이트
│   └── logger.py             # 로그 기록
├── ui/
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── drivers/
│   └── manifest.json         # 드라이버 메타데이터 인덱스
├── config/
│   ├── settings.json
│   └── app_version.json
└── logs/
    └── install_YYYYMMDD.log
```

## 참고 사항

- 드라이버 설치는 **관리자 권한**이 필요하며, 앱이 자동으로 UAC 권한을 요청합니다.
- 일부 드라이버 설치 후 재부팅이 필요할 수 있으며, 앱이 안내 메시지를 표시합니다.
- 설치 로그는 `logs/install_YYYYMMDD.log`에 기록됩니다.
- 앱은 EXE 위치를 기준으로 모든 상태를 저장합니다. 레지스트리 쓰기 없음, 완전한 포터블.

---
---

# Driver Manager Pro

USB portable Windows driver management tool. Supports offline bundled driver database and automatic updates via official vendor APIs.

---

## Table of Contents

- [Requirements](#requirements)
- [Quick Start](#quick-start-source)
- [First Run](#first-run)
- [DB Update](#db-update)
- [Offline / USB Mode](#offline--usb-mode)
- [Building](#building)
- [Adding Drivers Manually](#adding-drivers-manually)
- [Directory Structure](#directory-structure)
- [Notes](#notes)

---

## Requirements

- Windows 10 (1903+) or Windows 11, x64
- Python 3.11+
- Administrator privileges (UAC prompt appears automatically)

## Quick Start (Source)

```powershell
cd DriverManagerPro
pip install -r requirements.txt
python main.py
```

## First Run

1. On launch the app checks for `drivers/manifest.json`.
2. If not found, the **Welcome screen** appears — click **DB 다운로드 시작** to fetch the driver database.
3. After download completes, click **하드웨어 스캔** to detect installed drivers.
4. Select updates or click **전체 업데이트 설치**.

## DB Update

Clicking the **DB 업데이트** button triggers the following sequence:

1. Network connectivity check (stops immediately if offline)
2. Fetch the latest driver versions from official vendor APIs
   - **NVIDIA**: GeForce Experience service API
   - **AMD**: Radeon release JSON
   - **Intel / Realtek**: No public API — kept static
3. `drivers/manifest.json` is updated automatically (latest + previous, 2 versions per driver)
4. Any missing driver files are downloaded based on the updated DB

> Core features (hardware scan, version comparison, driver install) work **without an internet connection**.
> Network is used only for DB updates and driver file downloads.

## Offline / USB Mode

Copy the entire `DriverManagerPro/` folder (with a populated `drivers/` directory) to a USB drive and run `DriverManagerPro.exe` directly. No installation required.

## Building

```powershell
pip install pyinstaller pillow
python build.py             # builds both onedir + onefile (portable)
python build.py --onefile   # portable single EXE only
python build.py --onedir    # folder build only
```

Output is placed in `dist/`.

## Adding Drivers Manually

1. Place the driver package in `drivers/<vendor>/<family>/v<version>/`.
2. Add an entry to `drivers/manifest.json`:

```json
{
  "id": "realtek-hd-audio",
  "vendor": "Realtek",
  "class": "Media",
  "name": "Realtek HD Audio Driver",
  "hardware_ids": ["HDAUDIO\\FUNC_01&VEN_10EC&DEV_0867"],
  "versions": [
    {
      "version": "6.0.9563.1",
      "date": "2024-03-01",
      "tag": "latest",
      "path": "realtek/audio/v6.0.9563.1/",
      "inf": "RTKVHD64.inf",
      "size_mb": 120,
      "os": ["win10", "win11"],
      "arch": "x64"
    }
  ]
}
```

3. Restart the app and scan — the new driver will appear in the update list.

## Directory Structure

```
DriverManagerPro/
├── main.py                   # Entry point
├── build.py                  # PyInstaller build script
├── requirements.txt
├── core/
│   ├── hardware_detect.py    # WMI-based device scanner
│   ├── driver_compare.py     # Semantic version comparator
│   ├── driver_install.py     # pnputil / vendor EXE installer
│   ├── downloader.py         # DB update and file download
│   ├── vendor_api.py         # NVIDIA / AMD vendor API queries
│   ├── selfupdate.py         # App self-updater
│   └── logger.py             # Timestamped log writer
├── ui/
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── drivers/
│   └── manifest.json         # Driver metadata index
├── config/
│   ├── settings.json
│   └── app_version.json
└── logs/
    └── install_YYYYMMDD.log
```

## Notes

- Driver installation requires **administrator privileges** — the app requests UAC elevation automatically.
- A reboot may be required after installing certain drivers; the app will prompt you.
- Install logs are written to `logs/install_YYYYMMDD.log`.
- The app stores all state relative to the EXE location — no registry writes, fully portable.

# Driver Manager Pro

USB Portable Windows driver update tool with offline bundled driver database.

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

1. On first launch the app checks for `drivers/manifest.json`.
2. If not found, the **Welcome screen** appears — click **DB 다운로드 시작** to fetch the driver database.
3. After download completes, click **하드웨어 스캔** to detect installed drivers.
4. Select updates or click **전체 업데이트 설치**.

## Offline / USB Mode

Copy the entire `DriverManagerPro/` folder (with a populated `drivers/` folder) to a USB drive and run `DriverManagerPro.exe` directly. No installation required.

## Building

```powershell
pip install pyinstaller pillow
python build.py             # builds both onedir + onefile (portable)
python build.py --onefile   # portable single EXE only
python build.py --onedir    # folder build only
```

Output is placed in `dist/`.

## Adding Drivers to the DB

1. Place the driver package (extracted) in `drivers/<vendor>/<family>/v<version>/`.
2. Edit `drivers/manifest.json` to add or update the entry:

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

## Configuring CDN for Online Updates

Edit `config/settings.json`:

```json
{
  "cdn_base_url": "https://your-cdn.example.com/drivers",
  "remote_manifest_url": "https://your-cdn.example.com/manifest_remote.json",
  "app_update_url": "https://api.github.com/repos/your-org/driver-manager-pro/releases/latest"
}
```

The remote manifest follows the same schema as `drivers/manifest.json`. When **DB 업데이트** is triggered, only missing/newer driver packages are downloaded (delta update).

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
│   ├── downloader.py         # Online DB fetch & delta update
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

- Driver installation requires **administrator privileges** — the app will request UAC elevation automatically.
- A reboot may be required after installing certain drivers; the app will prompt you.
- Install logs are written to `logs/install_YYYYMMDD.log`.
- The app stores all state relative to the EXE location — no registry writes, fully portable.

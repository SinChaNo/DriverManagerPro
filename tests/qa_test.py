"""
Driver Manager Pro — QA 테스트 스위트

실행 방법:
    python tests/qa_test.py

테스트 범위:
    - driver_compare.py : 버전 파싱, NVIDIA 변환, 비교, HWID 매칭, manifest 통합
    - logger.py         : 버퍼, 세션 구분선, 파일 네이밍
    - driver_install.py : Referer 헤더, 벤더 플래그
    - downloader.py     : Referer 헤더 빌드
"""

import sys
import os
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# 프로젝트 루트를 경로에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# driver_compare.py 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestParseVersion(unittest.TestCase):
    """_parse_version: 버전 문자열 → int 튜플 변환"""

    def setUp(self):
        from core.driver_compare import _parse_version
        self.f = _parse_version

    def test_standard_4part(self):
        self.assertEqual(self.f("32.0.15.7283"), (32, 0, 15, 7283))

    def test_2part_nvidia(self):
        self.assertEqual(self.f("572.83"), (572, 83, 0, 0))

    def test_3part(self):
        self.assertEqual(self.f("24.10.1"), (24, 10, 1, 0))

    def test_empty_string(self):
        self.assertEqual(self.f(""), (0, 0, 0, 0))

    def test_non_numeric(self):
        self.assertEqual(self.f("abc"), (0, 0, 0, 0))

    def test_leading_trailing_spaces(self):
        self.assertEqual(self.f("  10.1.46.5  "), (10, 1, 46, 5))

    def test_realtek_version(self):
        self.assertEqual(self.f("11.058.1003.2024"), (11, 58, 1003, 2024))


class TestNvidiaVersionConvert(unittest.TestCase):
    """_nvidia_win_to_nvidia_ver: Windows 4-part → NVIDIA 2-part 변환"""

    def setUp(self):
        from core.driver_compare import _nvidia_win_to_nvidia_ver
        self.f = _nvidia_win_to_nvidia_ver

    def test_572_83(self):
        self.assertEqual(self.f("32.0.15.7283"), "572.83")

    def test_566_36(self):
        self.assertEqual(self.f("32.0.15.6636"), "566.36")

    def test_560_94(self):
        self.assertEqual(self.f("32.0.15.6094"), "560.94")

    def test_invalid_2part(self):
        """2-part 버전은 변환 불가 → None 반환"""
        self.assertIsNone(self.f("572.83"))

    def test_invalid_empty(self):
        self.assertIsNone(self.f(""))

    def test_invalid_non_numeric(self):
        self.assertIsNone(self.f("a.b.c.d"))


class TestNormalizeInstalledVersion(unittest.TestCase):
    """_normalize_installed_version: 벤더별 버전 정규화"""

    def setUp(self):
        from core.driver_compare import _normalize_installed_version
        self.f = _normalize_installed_version

    def test_nvidia_converts(self):
        """NVIDIA 4-part → 2-part 변환"""
        self.assertEqual(self.f("32.0.15.7283", "572.83", "NVIDIA"), "572.83")

    def test_nvidia_case_insensitive(self):
        self.assertEqual(self.f("32.0.15.7283", "572.83", "nvidia"), "572.83")

    def test_nvidia_already_2part(self):
        """이미 2-part면 변환 없음"""
        self.assertEqual(self.f("572.83", "572.83", "NVIDIA"), "572.83")

    def test_intel_no_convert(self):
        """Intel은 변환하지 않음"""
        result = self.f("10.0.26100.7705", "31.0.101.5592", "Intel")
        self.assertEqual(result, "10.0.26100.7705")

    def test_amd_no_convert(self):
        """AMD는 변환하지 않음"""
        result = self.f("24.5.1", "24.10.1", "AMD")
        self.assertEqual(result, "24.5.1")

    def test_realtek_no_convert(self):
        result = self.f("6.0.9490.1", "6.0.9490.1", "Realtek")
        self.assertEqual(result, "6.0.9490.1")


class TestVersionComparison(unittest.TestCase):
    """version_gt / version_eq: 버전 대소 비교"""

    def setUp(self):
        from core.driver_compare import version_gt, version_eq
        self.gt = version_gt
        self.eq = version_eq

    def test_nvidia_same_after_normalize(self):
        """정규화 후 동일 버전 → update_available=False"""
        from core.driver_compare import _normalize_installed_version
        normalized = _normalize_installed_version("32.0.15.7283", "572.83", "NVIDIA")
        self.assertFalse(self.gt("572.83", normalized))

    def test_newer_greater(self):
        self.assertTrue(self.gt("572.83", "566.36"))

    def test_older_not_greater(self):
        self.assertFalse(self.gt("566.36", "572.83"))

    def test_equal(self):
        self.assertTrue(self.eq("572.83", "572.83"))

    def test_intel_4part_greater(self):
        self.assertTrue(self.gt("31.0.101.5592", "31.0.101.5379"))

    def test_realtek_greater(self):
        self.assertTrue(self.gt("11.058.1003.2024", "6.0.9490.1"))


class TestHardwareIdMatch(unittest.TestCase):
    """_hardware_ids_match: HWID 매칭 로직"""

    def setUp(self):
        from core.driver_compare import _hardware_ids_match
        self.f = _hardware_ids_match

    def test_exact_match(self):
        device = ["PCI\\VEN_10DE&DEV_2216&SUBSYS_00001043"]
        driver = ["PCI\\VEN_10DE&DEV_2216"]
        self.assertTrue(self.f(device, driver))

    def test_ven_only_match_nvidia(self):
        """VEN-only HWID: PCI\\VEN_10DE 형식"""
        device = ["PCI\\VEN_10DE&DEV_2216&SUBSYS_00001043&REV_A1"]
        driver = ["PCI\\VEN_10DE"]
        self.assertTrue(self.f(device, driver))

    def test_ven_only_no_cross_vendor(self):
        """VEN_10DE는 VEN_8086 기기에 매칭되지 않아야 함"""
        device = ["PCI\\VEN_8086&DEV_7A04"]
        driver = ["PCI\\VEN_10DE"]
        self.assertFalse(self.f(device, driver))

    def test_full_ven_dev_match(self):
        device = ["PCI\\VEN_8086&DEV_46A6&SUBSYS_00001043"]
        driver = ["PCI\\VEN_8086&DEV_46A6"]
        self.assertTrue(self.f(device, driver))

    def test_dev_mismatch(self):
        """동일 벤더지만 DEV가 다르면 불일치"""
        device = ["PCI\\VEN_8086&DEV_9999"]
        driver = ["PCI\\VEN_8086&DEV_46A6"]
        self.assertFalse(self.f(device, driver))

    def test_empty_lists(self):
        self.assertFalse(self.f([], []))

    def test_usb_hwid(self):
        device = ["USB\\VID_8087&PID_0026&REV_0002"]
        driver = ["USB\\VID_8087&PID_0026"]
        self.assertTrue(self.f(device, driver))


class TestFuzzyMatchKeywords(unittest.TestCase):
    """퍼지 매칭: 'intel' 키워드 제거 확인"""

    def setUp(self):
        from core.driver_compare import compare_device_to_manifest
        self.compare = compare_device_to_manifest

    def _make_manifest_with(self, vendor, name, class_, hwids, version):
        return {
            "drivers": [{
                "id": "test-driver",
                "vendor": vendor,
                "class": class_,
                "name": name,
                "hardware_ids": hwids,
                "versions": [{"version": version, "path": "test/path",
                               "download_url": "", "inf": ""}],
            }]
        }

    def test_intel_chipset_not_match_intel_graphics(self):
        """Intel 칩셋 기기가 Intel Graphics 드라이버에 매칭되지 않아야 함"""
        manifest = self._make_manifest_with(
            "Intel", "Intel Graphics Driver (DCH)", "Display",
            ["PCI\\VEN_8086&DEV_46A6"], "31.0.101.5592",
        )
        # 칩셋 기기: 다른 DEV ID
        device = {
            "device_name": "Intel Chipset Device",
            "device_class": "System",
            "hardware_ids": ["PCI\\VEN_8086&DEV_7A04"],
            "driver_version": "10.1.46.5",
        }
        result = self.compare(device, manifest)
        self.assertIsNone(result, "Intel 칩셋 기기가 Intel Graphics에 오매칭됨")

    def test_geforce_fuzzy_match(self):
        """NVIDIA GeForce 기기는 퍼지 매칭으로 정상 매칭되어야 함"""
        manifest = self._make_manifest_with(
            "NVIDIA", "NVIDIA GeForce Game Ready Driver (Desktop DCH)", "Display",
            ["PCI\\VEN_10DE"], "572.83",
        )
        device = {
            "device_name": "NVIDIA GeForce RTX 3080",
            "device_class": "Display",
            "hardware_ids": ["PCI\\VEN_10DE&DEV_2206"],
            "driver_version": "32.0.15.7283",
        }
        result = self.compare(device, manifest)
        self.assertIsNotNone(result, "GeForce 기기가 매칭되지 않음")
        self.assertFalse(result["update_available"], "최신 드라이버인데 업데이트 필요 오탐")
        self.assertEqual(result["installed_version"], "572.83")

    def test_realtek_audio_fuzzy_match(self):
        """Realtek Audio 기기 퍼지 매칭"""
        manifest = self._make_manifest_with(
            "Realtek", "Realtek HD Audio Driver", "Media",
            ["HDAUDIO\\FUNC_01&VEN_10EC&DEV_0867"], "6.0.9490.1",
        )
        device = {
            "device_name": "Realtek High Definition Audio",
            "device_class": "Media",
            "hardware_ids": ["HDAUDIO\\FUNC_01&VEN_10EC&DEV_0867"],
            "driver_version": "6.0.9490.1",
        }
        result = self.compare(device, manifest)
        self.assertIsNotNone(result)
        self.assertFalse(result["update_available"])


class TestManifestIntegration(unittest.TestCase):
    """실제 manifest.json 기반 통합 테스트"""

    def setUp(self):
        from core.driver_compare import load_manifest, compare_device_to_manifest
        manifest_path = ROOT / "drivers" / "manifest.json"
        self.manifest = load_manifest(manifest_path)
        self.compare = compare_device_to_manifest

    def test_manifest_loaded(self):
        self.assertIn("drivers", self.manifest)
        self.assertGreater(len(self.manifest["drivers"]), 0)

    def test_nvidia_latest_no_update(self):
        """최신 NVIDIA 드라이버(572.83) → 업데이트 불필요"""
        device = {
            "device_name": "NVIDIA GeForce RTX 3080",
            "device_class": "Display",
            "hardware_ids": ["PCI\\VEN_10DE&DEV_2206"],
            "driver_version": "32.0.15.7283",  # Windows 형식의 572.83
        }
        result = self.compare(device, self.manifest)
        self.assertIsNotNone(result)
        self.assertFalse(result["update_available"],
                         f"최신 NVIDIA 드라이버인데 update_available=True. "
                         f"installed={result['installed_version']}, "
                         f"latest={result['latest_bundled']}")

    def test_nvidia_old_needs_update(self):
        """구버전 NVIDIA 드라이버(560.94) → 업데이트 필요"""
        device = {
            "device_name": "NVIDIA GeForce RTX 3080",
            "device_class": "Display",
            "hardware_ids": ["PCI\\VEN_10DE&DEV_2206"],
            "driver_version": "32.0.15.6094",  # Windows 형식의 560.94
        }
        result = self.compare(device, self.manifest)
        self.assertIsNotNone(result)
        self.assertTrue(result["update_available"],
                        f"구버전 NVIDIA인데 update_available=False.")

    def test_realtek_audio_latest_no_update(self):
        device = {
            "device_name": "Realtek High Definition Audio",
            "device_class": "Media",
            "hardware_ids": ["HDAUDIO\\FUNC_01&VEN_10EC&DEV_0867"],
            "driver_version": "6.0.9490.1",
        }
        result = self.compare(device, self.manifest)
        self.assertIsNotNone(result)
        self.assertFalse(result["update_available"])

    def test_amd_old_needs_update(self):
        device = {
            "device_name": "AMD Radeon RX 6800 XT",
            "device_class": "Display",
            "hardware_ids": ["PCI\\VEN_1002&DEV_73BF"],
            "driver_version": "24.5.1",
        }
        result = self.compare(device, self.manifest)
        self.assertIsNotNone(result)
        self.assertTrue(result["update_available"])


# ─────────────────────────────────────────────────────────────────────────────
# logger.py 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestLoggerBuffer(unittest.TestCase):
    """로그 버퍼 동작"""

    def test_buffer_limit(self):
        """버퍼가 2000줄을 초과하지 않아야 함"""
        from core import logger as lg
        # 버퍼 상한 확인
        self.assertEqual(lg._MAX_BUFFER, 2000)

    def test_get_all_log_lines_returns_list(self):
        from core.logger import get_all_log_lines
        result = get_all_log_lines()
        self.assertIsInstance(result, list)

    def test_log_lines_appended(self):
        from core.logger import logger, get_all_log_lines
        before = len(get_all_log_lines())
        logger.info("QA 테스트 버퍼 확인용 메시지")
        after = len(get_all_log_lines())
        self.assertGreater(after, before)


class TestLoggerSession(unittest.TestCase):
    """세션 구분선 함수"""

    def test_log_session_start_exists(self):
        from core.logger import log_session_start
        self.assertTrue(callable(log_session_start))

    def test_log_session_end_exists(self):
        from core.logger import log_session_end
        self.assertTrue(callable(log_session_end))

    def test_session_start_writes_to_buffer(self):
        from core.logger import log_session_start, get_all_log_lines
        before = len(get_all_log_lines())
        log_session_start("QA 테스트")
        after = len(get_all_log_lines())
        self.assertGreater(after, before)

    def test_session_end_writes_to_buffer(self):
        from core.logger import log_session_end, get_all_log_lines
        before = len(get_all_log_lines())
        log_session_end("QA 테스트", success_count=1, total=2)
        after = len(get_all_log_lines())
        self.assertGreater(after, before)


class TestLoggerFileNaming(unittest.TestCase):
    """로그 파일 네이밍: 날짜+시간 형식"""

    def test_log_file_has_time(self):
        """로그 파일에 시간 정보가 포함되어야 함 (HHMMSS)"""
        import re
        from core.logger import get_base_dir
        log_dir = get_base_dir() / "logs"
        if not log_dir.exists():
            self.skipTest("logs 디렉토리 없음")
        log_files = list(log_dir.glob("install_*.log"))
        if not log_files:
            self.skipTest("생성된 로그 파일 없음")
        # 날짜+시간 패턴: install_20260522_143512.log
        pattern = re.compile(r"install_\d{8}_\d{6}\.log")
        matched = [f for f in log_files if pattern.match(f.name)]
        self.assertGreater(len(matched), 0,
                           f"시간 포함 로그 파일 없음. 발견된 파일: {[f.name for f in log_files]}")


# ─────────────────────────────────────────────────────────────────────────────
# driver_install.py 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestInstallRequestHeaders(unittest.TestCase):
    """_build_request_headers: 도메인별 Referer 헤더"""

    def setUp(self):
        from core.driver_install import _build_request_headers
        self.f = _build_request_headers

    def test_intel_referer(self):
        h = self.f("https://downloadmirror.intel.com/836861/gfx_win_101.5592.exe")
        self.assertEqual(h.get("Referer"), "https://www.intel.com/")

    def test_nvidia_referer(self):
        h = self.f("https://us.download.nvidia.com/Windows/572.83/572.83-desktop.exe")
        self.assertEqual(h.get("Referer"), "https://www.nvidia.com/")

    def test_amd_referer(self):
        h = self.f("https://drivers.amd.com/drivers/installer/amd-software.exe")
        self.assertEqual(h.get("Referer"), "https://www.amd.com/")

    def test_realtek_referer(self):
        h = self.f("https://www.realtek.com/drivers/realtek-hd-audio.exe")
        self.assertEqual(h.get("Referer"), "https://www.realtek.com/")

    def test_unknown_domain_no_referer(self):
        """알 수 없는 도메인은 Referer 없음"""
        h = self.f("https://unknown-cdn.example.com/driver.exe")
        self.assertNotIn("Referer", h)

    def test_user_agent_present(self):
        h = self.f("https://downloadmirror.intel.com/test.exe")
        self.assertIn("Chrome", h.get("User-Agent", ""))

    def test_headers_always_have_accept(self):
        for url in [
            "https://downloadmirror.intel.com/test.exe",
            "https://us.download.nvidia.com/test.exe",
            "https://unknown.com/test.exe",
        ]:
            with self.subTest(url=url):
                h = self.f(url)
                self.assertIn("Accept", h)


class TestVendorSilentFlags(unittest.TestCase):
    """_get_silent_flags: 벤더별 사일런트 플래그"""

    def setUp(self):
        from core.driver_install import _get_silent_flags
        self.f = _get_silent_flags

    def test_nvidia_flags(self):
        flags = self.f("nvidia")
        self.assertIn("-s", flags)
        self.assertIn("-noeula", flags)
        self.assertIn("-noreboot", flags)

    def test_nvidia_case_insensitive(self):
        self.assertEqual(self.f("NVIDIA"), self.f("nvidia"))

    def test_amd_flags(self):
        flags = self.f("amd")
        self.assertIn("--silent", flags)
        self.assertIn("--noreboot", flags)

    def test_intel_flags(self):
        flags = self.f("intel")
        self.assertIn("-s", flags)
        self.assertIn("-norestart", flags)

    def test_realtek_flags(self):
        flags = self.f("realtek")
        self.assertIn("/s", flags)

    def test_unknown_vendor_returns_default(self):
        from core.driver_install import _DEFAULT_SILENT_FLAGS
        flags = self.f("unknown_vendor")
        self.assertEqual(flags, _DEFAULT_SILENT_FLAGS)

    def test_empty_vendor_returns_default(self):
        from core.driver_install import _DEFAULT_SILENT_FLAGS
        flags = self.f("")
        self.assertEqual(flags, _DEFAULT_SILENT_FLAGS)


# ─────────────────────────────────────────────────────────────────────────────
# downloader.py 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestDownloaderRequestHeaders(unittest.TestCase):
    """downloader._build_request_headers: 도메인별 Referer"""

    def setUp(self):
        from core.downloader import _build_request_headers
        self.f = _build_request_headers

    def test_intel_mirror_referer(self):
        h = self.f("https://downloadmirror.intel.com/836861/gfx_win_101.5592.exe")
        self.assertEqual(h.get("Referer"), "https://www.intel.com/")

    def test_intel_download_referer(self):
        h = self.f("https://download.intel.com/some/driver.exe")
        self.assertEqual(h.get("Referer"), "https://www.intel.com/")

    def test_nvidia_us_referer(self):
        h = self.f("https://us.download.nvidia.com/Windows/572.83/driver.exe")
        self.assertEqual(h.get("Referer"), "https://www.nvidia.com/")

    def test_amd_referer(self):
        h = self.f("https://drivers.amd.com/drivers/amd.exe")
        self.assertEqual(h.get("Referer"), "https://www.amd.com/")

    def test_realtek_referer(self):
        h = self.f("https://www.realtek.com/drivers/realtek.exe")
        self.assertEqual(h.get("Referer"), "https://www.realtek.com/")

    def test_unknown_no_referer(self):
        h = self.f("https://example.com/driver.exe")
        self.assertNotIn("Referer", h)

    def test_user_agent_is_full_browser(self):
        h = self.f("https://us.download.nvidia.com/test.exe")
        ua = h.get("User-Agent", "")
        self.assertIn("AppleWebKit", ua, "User-Agent가 완전한 브라우저 형식이 아님")
        self.assertIn("Chrome", ua)


# ─────────────────────────────────────────────────────────────────────────────
# 테스트 실행
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        # driver_compare
        TestParseVersion,
        TestNvidiaVersionConvert,
        TestNormalizeInstalledVersion,
        TestVersionComparison,
        TestHardwareIdMatch,
        TestFuzzyMatchKeywords,
        TestManifestIntegration,
        # logger
        TestLoggerBuffer,
        TestLoggerSession,
        TestLoggerFileNaming,
        # driver_install
        TestInstallRequestHeaders,
        TestVendorSilentFlags,
        # downloader
        TestDownloaderRequestHeaders,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

"""Guards for the installed-app startup crash: unsupported CUDA arch and config replace."""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import _replace_with_retry, save_config
from src.llm_model_manager import decide_n_gpu_layers, parse_cuda_arch_tokens, scan_cuda_binary_architectures


class CudaOffloadGuard(unittest.TestCase):
    def test_parse_consumer_and_blackwell_arch_tokens(self):
        blob = b"prefix sm_89 sm_90 compute_120 sm_100 tail sm_75"
        self.assertEqual(
            parse_cuda_arch_tokens(blob),
            {(8, 9), (9, 0), (12, 0), (10, 0), (7, 5)},
        )

    def test_blackwell_with_sm90_uses_gpu_offload_via_ptx_jit(self):
        # NVIDIA Driver PTX JIT forward-compiles sm_90 PTX to Blackwell CC 12.0
        layers, note = decide_n_gpu_layers("cuda", True, True, (12, 0), {(9, 0)})
        self.assertEqual(layers, -1)
        self.assertEqual(note, "")

    def test_matching_arch_keeps_gpu_offload(self):
        layers, note = decide_n_gpu_layers("cuda", True, True, (8, 9), {(7, 5), (8, 6), (8, 9), (9, 0)})
        self.assertEqual(layers, -1)
        self.assertEqual(note, "")

    def test_cpu_device_never_offloads(self):
        layers, note = decide_n_gpu_layers("cpu", True, True, (8, 9), {(8, 9)})
        self.assertEqual((layers, note), (0, ""))

    def test_legacy_gpu_below_min_arch_falls_back_to_cpu(self):
        # GPUs below minimum supported architecture safely fall back to CPU
        layers, note = decide_n_gpu_layers("cuda", True, True, (3, 5), {(7, 5), (8, 0)})
        self.assertEqual(layers, 0)
        self.assertIn("3.5", note)

    def test_cuda_pack_marker_rejects_an_old_ggml_only_install(self):
        import src.cuda_utils as cu
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(cu, "get_llama_cuda_pack_dir", return_value=folder):
            with open(os.path.join(folder, "ggml-cuda.dll"), "wb") as handle:
                handle.write(b"x" * (51 * 1024 * 1024))
            with open(os.path.join(folder, "llama.dll"), "wb") as handle:
                handle.write(b"x")
            self.assertFalse(cu.is_llama_cuda_pack_installed())
            with open(os.path.join(folder, "wise_cuda_pack.txt"), "w", encoding="utf-8") as handle:
                handle.write(cu.LLAMA_CUDA_PACK_ID)
            self.assertTrue(cu.is_llama_cuda_pack_installed())

    def test_ggml_archs_literal_wins_over_partial_sm_tokens(self):
        # 공식 cu124 빌드는 fatbin 에 sm_90 만 문자열로 남아 RTX 40(8.9)을 미지원으로 오판했다.
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "ggml-cuda.dll")
            with open(path, "wb") as handle:
                handle.write(b"x" * 64 + b"sm_90" + b"y" * 64
                             + b"ARCHS\x00\x00\x00\x00\x00\x00\x00600,610,700,750,800,860,890,900\x00FORCE_MMQ")
            archs = scan_cuda_binary_architectures(path)
        self.assertIn((8, 9), archs)
        self.assertEqual(decide_n_gpu_layers("cuda", True, True, (8, 9), archs), (-1, ""))

    def test_scan_reads_arch_token_across_chunk_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "ggml-cuda.dll")
            payload = b"x" * 64 + b"sm_120"
            with open(path, "wb") as handle:
                handle.write(payload)
            self.assertIn((12, 0), scan_cuda_binary_architectures(path))


class LlamaBackendSelection(unittest.TestCase):
    """NVIDIA 가 없거나 드라이버가 낡은 PC 는 CPU 전용 llama.cpp, 로드된 뒤에는 교체하지 않는다."""

    def setUp(self):
        import src.cuda_utils as cu
        self.cu = cu
        self._saved_state = dict(cu._LLAMA_STATE)
        self._saved_env = os.environ.get("LLAMA_CPP_LIB_PATH")
        self.pack = patch.object(cu, "is_llama_cuda_pack_installed", return_value=True)
        self.pack_dir = patch.object(cu, "get_llama_cuda_pack_dir", return_value=r"C:\pack\cu130")
        self.bundled = patch.object(cu, "get_bundled_llama_cuda_dir", return_value=None)
        self.default = patch.object(cu, "get_default_llama_lib_dir", return_value=r"C:\app\llama_cpp\lib")
        for p in (self.pack, self.pack_dir, self.bundled, self.default):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.cu._LLAMA_STATE.clear()
        self.cu._LLAMA_STATE.update(self._saved_state)
        if self._saved_env is None:
            os.environ.pop("LLAMA_CPP_LIB_PATH", None)
        else:
            os.environ["LLAMA_CPP_LIB_PATH"] = self._saved_env

    def _select(self, nvidia, driver=(581, 0), cc=(8, 9)):
        with patch.object(self.cu, "is_nvidia_gpu_present", return_value=nvidia), \
                patch.object(self.cu, "get_nvidia_driver_info", return_value=(driver, cc)):
            return self.cu.select_llama_backend()

    def test_no_nvidia_uses_cpu_even_if_pack_exists(self):
        sel = self._select(nvidia=False)
        self.assertEqual(sel["backend"], "cpu")
        self.assertIn("NVIDIA", sel["issue"])

    def test_old_driver_blocks_cuda13_pack(self):
        sel = self._select(nvidia=True, driver=(552, 22))
        self.assertEqual(sel["backend"], "cpu")
        self.assertIn("580", sel["issue"])

    def test_pre_turing_gpu_blocks_cuda13_pack(self):
        sel = self._select(nvidia=True, cc=(6, 1))
        self.assertEqual(sel["backend"], "cpu")
        self.assertIn("7.5", sel["issue"])

    def test_compatible_nvidia_selects_pack(self):
        sel = self._select(nvidia=True)
        self.assertEqual((sel["backend"], sel["path"]), ("cuda", r"C:\pack\cu130"))

    def test_loaded_cpu_library_is_not_swapped(self):
        self.cu._LLAMA_STATE.update(configured=True, backend="cpu", path=None, restart_required=False)
        os.environ.pop("LLAMA_CPP_LIB_PATH", None)
        with patch.object(self.cu, "is_llama_loaded", return_value=True), \
                patch.object(self.cu, "is_nvidia_gpu_present", return_value=True), \
                patch.object(self.cu, "get_nvidia_driver_info", return_value=((581, 0), (8, 9))):
            state = self.cu.configure_llama_backend()
        self.assertEqual(state["backend"], "cpu")
        self.assertTrue(state["restart_required"])
        self.assertNotIn("LLAMA_CPP_LIB_PATH", os.environ)


class CleanInstallMarker(unittest.TestCase):
    """클린 설치 표식이 있으면 그 설치 이후 첫 실행에서 한 번만 사용자 설정을 지운다."""

    def test_marker_resets_config_once_per_install(self):
        from src.config import _consume_clean_install_marker
        with tempfile.TemporaryDirectory() as app_dir, tempfile.TemporaryDirectory() as user_dir:
            cfg = os.path.join(user_dir, "config.json")
            exe = os.path.join(app_dir, "WiseEinstein.exe")
            with open(os.path.join(app_dir, "clean_install.id"), "w", encoding="utf-8") as handle:
                handle.write("20261001000000")
            with patch.object(sys, "executable", exe):
                with open(cfg, "w", encoding="utf-8") as handle:
                    handle.write('{"translation_engine": "exaone7b"}')
                _consume_clean_install_marker(cfg)
                self.assertFalse(os.path.exists(cfg))

                with open(cfg, "w", encoding="utf-8") as handle:
                    handle.write('{"translation_engine": "hymt"}')
                _consume_clean_install_marker(cfg)
                self.assertTrue(os.path.exists(cfg), "같은 설치에서 두 번째 실행부터는 사용자가 바꾼 설정을 유지해야 한다")

                with open(os.path.join(app_dir, "clean_install.id"), "w", encoding="utf-8") as handle:
                    handle.write("20261002000000")
                _consume_clean_install_marker(cfg)
                self.assertFalse(os.path.exists(cfg), "새 클린 설치는 다시 초기화해야 한다")


class ConfigSaveGuard(unittest.TestCase):
    def test_replace_retries_windows_access_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            src = os.path.join(folder, "config.json.tmp")
            dst = os.path.join(folder, "config.json")
            with open(src, "w", encoding="utf-8") as handle:
                handle.write("new")
            with open(dst, "w", encoding="utf-8") as handle:
                handle.write("old")
            os.chmod(dst, stat.S_IREAD)
            calls = {"n": 0}
            real_replace = os.replace

            def flaky(src_path, dst_path):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise PermissionError(13, "Access is denied", src_path, 5, dst_path)
                return real_replace(src_path, dst_path)

            with patch("src.config.os.replace", side_effect=flaky):
                _replace_with_retry(src, dst, attempts=5, delay=0)
            with open(dst, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "new")
            self.assertEqual(calls["n"], 3)

    def test_save_config_overwrites_when_replace_stays_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"old": True}, handle)

            def always_denied(src_path, dst_path):
                raise PermissionError(13, "Access is denied", src_path, 5, dst_path)

            with patch("src.config.os.replace", side_effect=always_denied):
                save_config({"translation_engine": "gemma"}, config_file=path)
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["translation_engine"], "gemma")
            leftovers = [name for name in os.listdir(folder) if name.endswith(".tmp")]
            self.assertEqual(leftovers, [])

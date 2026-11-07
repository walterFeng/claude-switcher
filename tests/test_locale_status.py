"""地区判定回归测试:抽取核心脚本函数,用 defaults 桩模拟系统与 Claude 单独语言设置。"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "core" / "claude-switch.sh").read_text(encoding="utf-8")
LOCALE_FN = re.search(r"(?ms)^locale_status\(\) \{\n.*?^\}", CORE).group(0)
FIX_B4 = re.search(r"(?ms)^    # B4\. .*?(?=^    # B2\. )", CORE).group(0)
REGION_WRITE = re.search(r"(?m)^    \[\[ \"\$\(locale_status\)\" == fail:\* \]\] && defaults write -g AppleLocale \"\$nlocale\"$",
                         CORE)


def defaults_stub(global_locale, app_langs):
    app = "" if app_langs is None else "(\n" + "".join(f'    "{l}",\n' for l in app_langs) + ")"
    return f"""
defaults() {{
    case "$*" in
        "read -g AppleLocale") [ -n {global_locale!r} ] && echo {global_locale!r} || return 1 ;;
        "read com.anthropic.claudefordesktop AppleLanguages") [ -n ${app!r} ] && printf '%s\\n' ${app!r} || return 1 ;;
        write*) echo "WRITE:$*" ;;
    esac
}}
"""


def run(target, global_locale, app_langs, body):
    script = f'LOCALE_TARGET="{target}"\n' + defaults_stub(global_locale, app_langs) + LOCALE_FN + "\n" + body
    return subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=10).stdout.strip()


class LocaleStatusTests(unittest.TestCase):
    def status(self, target, global_locale, app_langs):
        return run(target, global_locale, app_langs, "locale_status")

    def test_exact_system_locale_passes(self):
        self.assertEqual(self.status("en_US", "en_US", None), "ok")

    def test_region_match_with_claude_language_passes(self):
        self.assertEqual(self.status("en_US", "zh-Hans_US", ["en-US", "zh-Hans", "zh-Hans-US"]),
                         "ok:按 Claude 单独语言(en-US)")
        self.assertEqual(self.status("en_US", "zh-Hans_US", ["en"]), "ok:按 Claude 单独语言(en)")
        self.assertEqual(self.status("ja_JP", "zh-Hans_JP", ["ja-JP"]), "ok:按 Claude 单独语言(ja-JP)")

    def test_fails_without_claude_language_override(self):
        self.assertEqual(self.status("en_US", "zh-Hans_US", None), "fail:zh-Hans_US")

    def test_fails_when_claude_language_not_first(self):
        self.assertEqual(self.status("en_US", "zh-Hans_US", ["zh-Hans", "en-US"]), "fail:zh-Hans_US")

    def test_fails_when_region_differs(self):
        self.assertEqual(self.status("en_US", "zh-Hans_CN", ["en-US"]), "fail:zh-Hans_CN")
        self.assertEqual(self.status("en_US", "en_GB", ["en-US"]), "fail:en_GB")

    def test_fails_when_claude_language_region_differs(self):
        self.assertEqual(self.status("en_US", "zh-Hans_US", ["en-GB"]), "fail:zh-Hans_US")

    def test_fails_when_system_locale_unreadable(self):
        self.assertEqual(self.status("en_US", "", ["en-US"]), "fail:")

    def test_fix_keeps_system_locale_when_claude_language_satisfies(self):
        out = run("en_US", "zh-Hans_US", ["en-US"], FIX_B4)
        self.assertNotIn("WRITE:", out)

    def test_fix_writes_system_locale_when_check_fails(self):
        out = run("en_US", "zh-Hans_CN", ["en-US"], FIX_B4)
        self.assertIn("WRITE:write -g AppleLocale en_US", out)

    def test_set_region_writes_only_on_failure(self):
        self.assertIsNotNone(REGION_WRITE, "set-region 只应在地区判定失败时写入系统区域格式")
        line = REGION_WRITE.group(0).replace("$nlocale", "en_US")
        self.assertNotIn("WRITE:", run("en_US", "zh-Hans_US", ["en-US"], line))
        self.assertIn("WRITE:write -g AppleLocale en_US", run("en_US", "zh-Hans_CN", ["en-US"], line))

    def test_check_and_checkdetail_use_locale_status(self):
        check = re.search(r"(?ms)^check\(\) \{\n.*?^\}", CORE).group(0)
        detail = re.search(r"(?ms)^checkdetail\(\) \{\n.*?^\}", CORE).group(0)
        self.assertIn("locale_st=$(locale_status)", check)
        self.assertIn('echo "地区=$(locale_status)"', detail)
        self.assertNotIn('[ "$locale" = "$LOCALE_TARGET" ]', check + detail)


if __name__ == "__main__":
    unittest.main()

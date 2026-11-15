# tests/test_neutralize_links.py
# Agent 的回答以 Markdown 顯示。模型可能把郵件／網頁裡的釣魚網址整理成可點
# 連結；不在白名單網域的連結必須變成不可點的純文字網址。

import re
import unittest

from ui_render import is_allowed_link, neutralize_links

ALLOW = ["example.com"]

# Markdown 會產生可點連結的語法：[x](url)、![x](url)、<url>、程式碼外的裸網址
_CLICKABLE = re.compile(r"\]\(|<https?://")


def _outside_code(text: str) -> str:
    return re.sub(r"```.*?```|`[^`\n]*`", "", text, flags=re.S)


class NeutralizeLinksTest(unittest.TestCase):
    def assert_not_clickable(self, out: str, url: str):
        rest = _outside_code(out)
        self.assertNotRegex(rest, _CLICKABLE)
        self.assertNotIn(url, rest)          # 網址只出現在行內程式碼裡
        self.assertIn(f"`{url}`", out)       # 但使用者仍看得到完整網址

    def test_markdown_link(self):
        out = neutralize_links("請到[這裡更新密碼](https://evil.test/login)。", ALLOW)
        self.assertEqual(out, "請到這裡更新密碼（`https://evil.test/login`）。")

    def test_markdown_link_with_title(self):
        out = neutralize_links('[點我](https://evil.test "官方") 吧', ALLOW)
        self.assert_not_clickable(out, "https://evil.test")

    def test_image(self):
        out = neutralize_links("![logo](https://evil.test/a.png)", ALLOW)
        self.assertEqual(out, "[圖片：logo]（`https://evil.test/a.png`）")

    def test_bare_url_and_trailing_punctuation(self):
        out = neutralize_links("網址是 https://evil.test/x，請點擊。", ALLOW)
        self.assertEqual(out, "網址是 `https://evil.test/x`，請點擊。")

    def test_www_url(self):
        out = neutralize_links("見 www.evil.test/path", ALLOW)
        self.assertEqual(out, "見 `www.evil.test/path`")

    def test_angle_autolink(self):
        out = neutralize_links("<https://evil.test>", ALLOW)
        self.assertEqual(out, "`https://evil.test`")

    def test_reference_style_link(self):
        out = neutralize_links("[點我][1]\n\n[1]: https://evil.test", ALLOW)
        self.assertNotRegex(out, r"^\[1\]:", )
        self.assertIn("`https://evil.test`", out)

    def test_disguised_label(self):
        # 連結文字寫正常網址、實際導向惡意網址
        out = neutralize_links("[https://example.com](https://evil.test)", ["other.org"])
        self.assertNotIn("](", out)
        self.assertIn("`https://evil.test`", out)
        self.assertIn("`https://example.com`", out)

    def test_userinfo_trick_not_allowed(self):
        self.assertFalse(is_allowed_link("https://example.com@evil.test/", ALLOW))
        out = neutralize_links("[x](https://example.com@evil.test/)", ALLOW)
        self.assertNotIn("](", out)

    def test_lookalike_domain_not_allowed(self):
        self.assertFalse(is_allowed_link("https://evilexample.com", ALLOW))
        self.assertFalse(is_allowed_link("https://example.com.evil.test", ALLOW))

    def test_non_http_scheme_not_allowed(self):
        self.assertFalse(is_allowed_link("javascript:alert(1)", ALLOW))
        out = neutralize_links("[x](javascript:alert(1))", ALLOW)
        self.assertNotIn("](javascript", out)

    def test_allowlisted_links_kept(self):
        src = "[手冊](https://intranet.example.com/hr) 與 https://example.com/faq"
        self.assertEqual(neutralize_links(src, ALLOW), src)

    def test_empty_allowlist_blocks_everything(self):
        out = neutralize_links("[手冊](https://example.com/hr)", [])
        self.assertEqual(out, "手冊（`https://example.com/hr`）")

    def test_code_untouched(self):
        src = "執行 `curl https://evil.test` 或\n```\nhttps://evil.test\n```"
        self.assertEqual(neutralize_links(src, ALLOW), src)

    def test_plain_text_and_empty(self):
        self.assertEqual(neutralize_links("根據《員工手冊》，年假 7 天。", ALLOW), "根據《員工手冊》，年假 7 天。")
        self.assertEqual(neutralize_links("", ALLOW), "")
        self.assertEqual(neutralize_links(None, ALLOW), "")


if __name__ == "__main__":
    unittest.main()

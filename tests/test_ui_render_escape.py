# tests/test_ui_render_escape.py
# ui_render 的輸出會以 unsafe_allow_html=True 渲染，而內容來自工具輸入／輸出
# （Email、網頁、知識庫文字）。外部文字裡的 HTML 必須被轉義成純文字，
# 不能變成助理介面上真的連結、表單或標籤。

import unittest

from ui_render import render_sources, render_steps, render_tool_badge

PAYLOAD = (
    '<a href="https://evil.example">點我領獎</a>'
    '<form action="https://evil.example"><input name="pw"></form>'
    '<img src=x onerror="alert(1)">'
)


class UiRenderEscapeTest(unittest.TestCase):
    def assert_neutralized(self, out: str):
        for tag in ("<a ", "<form", "<input", "<img"):
            self.assertNotIn(tag, out)
        self.assertIn("&lt;a href=&quot;https://evil.example&quot;&gt;", out)

    def test_steps_escape_input_and_output(self):
        out = render_steps([{"tool": "search_email", "input": {"query": PAYLOAD}, "output": PAYLOAD}])
        self.assert_neutralized(out)
        # 版面本身的 HTML 仍然保留
        self.assertIn('<div class="step-card', out)

    def test_sources_escaped(self):
        out = render_sources([PAYLOAD])
        self.assert_neutralized(out)
        self.assertIn('<span class="source-tag">', out)

    def test_tool_badge_escaped(self):
        out = render_tool_badge(PAYLOAD)
        self.assert_neutralized(out)

    def test_plain_text_unchanged(self):
        out = render_sources(["員工手冊.pdf"])
        self.assertIn(">員工手冊.pdf</span>", out)

    def test_blank_lines_do_not_break_html_block(self):
        # 空行會結束 Markdown 的 HTML 區塊，之後的 [x](url) 會重新變成可點連結
        output = "寄件者：a\n\n---\n\n[點我](https://evil.example)\r\n結尾"
        out = render_steps([{"tool": "search_email", "input": {}, "output": output}])
        self.assertNotIn("\n\n", out.split('<div class="step-io">', 1)[1])
        self.assertIn("<br><br>---<br><br>", out)

    def test_external_tools_labelled(self):
        for tool in ("search_email", "web_search", "list_calendar_events"):
            out = render_steps([{"tool": tool, "input": {}, "output": "x"}])
            self.assertIn('class="step-card external"', out)
            self.assertIn("外部內容", out)

    def test_internal_tools_not_labelled(self):
        for tool in ("search_knowledge_base", "run_sql_query", "calculate"):
            out = render_steps([{"tool": tool, "input": {}, "output": "x"}])
            self.assertIn('class="step-card"', out)
            self.assertNotIn("外部內容", out)

    def test_empty_inputs(self):
        self.assertEqual(render_sources([]), "")
        self.assertEqual(render_steps([]), "")


if __name__ == "__main__":
    unittest.main()

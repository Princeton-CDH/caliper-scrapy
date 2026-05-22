# SPDX-FileCopyrightText: 2024-present Center for Digital Humanities, Princeton University
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import csv
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from caliper.crawl import (
    FORMAT_HTML,
    FORMAT_TEXT,
    ReportSubscription,
    USER_AGENT,
    content_column_names,
    crawl,
    main,
    parse_formats,
)


def make_page(
    url="https://example.com/page",
    status_code=200,
    title="Page Title",
    headers=None,
    content=b"hello",
):
    page = MagicMock()
    page.url = url
    page.status_code = status_code
    page.title.return_value = title
    page.headers = headers if headers is not None else {}
    page.content = content
    return page


@pytest.fixture
def output(tmp_path):
    return tmp_path / "report.csv"


@pytest.fixture
def subscription(output):
    return ReportSubscription(output, show_progress=False)


@pytest.fixture
def subscription_with_selector(output):
    # backward-compatible default: HTML format only
    return ReportSubscription(
        output, show_progress=False, selector="p.content", formats=(FORMAT_HTML,)
    )


class TestParseFormats:
    def test_empty_returns_empty_tuple(self):
        assert parse_formats("") == ()
        assert parse_formats(None) == ()

    def test_single_html(self):
        assert parse_formats("html") == ("html",)

    def test_single_text(self):
        assert parse_formats("text") == ("text",)

    def test_multiple_preserves_order(self):
        assert parse_formats("html,text") == ("html", "text")
        assert parse_formats("text,html") == ("text", "html")

    def test_whitespace_tolerant(self):
        assert parse_formats(" html , text ") == ("html", "text")

    def test_case_insensitive(self):
        assert parse_formats("HTML,Text") == ("html", "text")

    def test_dedupes(self):
        assert parse_formats("html,html,text") == ("html", "text")

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unsupported format 'markdown'"):
            parse_formats("markdown")

    def test_unknown_format_in_list_raises(self):
        with pytest.raises(ValueError, match="Unsupported format"):
            parse_formats("html,markdown")


class TestContentColumnNames:
    def test_empty(self):
        assert content_column_names(()) == ()

    def test_html_only_uses_legacy_name(self):
        assert content_column_names(("html",)) == ("content",)

    def test_text_only(self):
        assert content_column_names(("text",)) == ("content_text",)

    def test_multiple_uses_suffixed_names(self):
        assert content_column_names(("html", "text")) == (
            "content_html",
            "content_text",
        )

    def test_multiple_preserves_given_order(self):
        assert content_column_names(("text", "html")) == (
            "content_text",
            "content_html",
        )


class TestReportSubscription:
    def test_columns_classvar(self):
        assert "url" in ReportSubscription.columns
        assert "timestamp" in ReportSubscription.columns
        assert "content" not in ReportSubscription.columns

    def test_csv_header(self, subscription, output):
        subscription.filehandle.flush()
        rows = list(csv.reader(output.open()))
        assert rows[0] == [
            "url",
            "status_code",
            "title",
            "content_type",
            "last_modified",
            "content_length",
            "date",
            "size",
            "timestamp",
        ]

    def test_writes_page_data(self, subscription, output):
        page = make_page(
            url="https://example.com/about",
            status_code=200,
            title="About",
            headers={
                "content-type": "text/html; charset=utf-8",
                "last-modified": "Wed, 01 Jan 2025 00:00:00 GMT",
                "content-length": "4321",
                "date": "Wed, 08 May 2026 12:00:00 GMT",
            },
            content=b"x" * 750,
        )
        subscription(page)
        subscription.filehandle.flush()

        rows = list(csv.reader(output.open()))
        assert len(rows) == 2
        url, status, title, ctype, last_mod, content_len, date, size, ts = rows[1]
        assert url == "https://example.com/about"
        assert status == "200"
        assert title == "About"
        assert ctype == "text/html; charset=utf-8"
        assert last_mod == "Wed, 01 Jan 2025 00:00:00 GMT"
        assert content_len == "4321"
        assert date == "Wed, 08 May 2026 12:00:00 GMT"
        assert size == "750"

    def test_strips_title_whitespace(self, subscription, output):
        subscription(make_page(title="  \n  Padded Title \t "))
        subscription.filehandle.flush()
        rows = list(csv.reader(output.open()))
        assert rows[1][2] == "Padded Title"

    def test_timestamp_is_iso_format(self, subscription, output):
        subscription(make_page())
        subscription.filehandle.flush()
        rows = list(csv.reader(output.open()))
        ts = rows[1][8]
        # isoformat produces e.g. "2026-05-08T12:00:00+00:00"
        assert "T" in ts
        assert ts.endswith("+00:00")

    def test_page_count_increments(self, subscription):
        assert subscription.page_count == 0
        subscription(make_page())
        assert subscription.page_count == 1
        subscription(make_page())
        assert subscription.page_count == 2

    def test_missing_headers_written_as_empty(self, subscription, output):
        subscription(make_page(headers={}))
        subscription.filehandle.flush()
        rows = list(csv.reader(output.open()))
        _, _, _, ctype, last_mod, content_len, date, _, _ = rows[1]
        assert ctype == ""
        assert last_mod == ""
        assert content_len == ""
        assert date == ""

    def test_selector_html_format_adds_content_column_to_header(
        self, subscription_with_selector, output
    ):
        subscription_with_selector.filehandle.flush()
        rows = list(csv.reader(output.open()))
        assert rows[0][-1] == "content"
        assert len(rows[0]) == 10

    def test_selector_text_format_adds_content_text_column(self, output):
        sub = ReportSubscription(
            output, show_progress=False, selector="p", formats=(FORMAT_TEXT,)
        )
        sub.filehandle.flush()
        rows = list(csv.reader(output.open()))
        assert rows[0][-1] == "content_text"

    def test_multiple_formats_adds_two_columns(self, output):
        sub = ReportSubscription(
            output,
            show_progress=False,
            selector="p",
            formats=(FORMAT_HTML, FORMAT_TEXT),
        )
        sub.filehandle.flush()
        rows = list(csv.reader(output.open()))
        assert rows[0][-2:] == ["content_html", "content_text"]
        assert len(rows[0]) == 11

    def test_selector_without_formats_omits_content_columns(self, output):
        # selector set but no formats requested: do not add any content columns
        sub = ReportSubscription(output, show_progress=False, selector="p", formats=())
        sub.filehandle.flush()
        rows = list(csv.reader(output.open()))
        assert len(rows[0]) == 9
        assert "content" not in rows[0]

    def test_del_with_no_attributes_does_not_raise(self):
        # simulate GC after __init__ raised before filehandle/status/pbar were set
        sub = ReportSubscription.__new__(ReportSubscription)
        sub.__del__()

    def test_invalid_selector_raises_valueerror(self, output):
        with pytest.raises(ValueError, match="Invalid CSS selector"):
            ReportSubscription(output, show_progress=False, selector="[invalid{{")

    def test_validate_selector_passes_for_valid(self):
        ReportSubscription._validate_selector("p.content")

    def test_validate_selector_raises_for_invalid(self):
        with pytest.raises(ValueError, match="Invalid CSS selector"):
            ReportSubscription._validate_selector("[invalid{{")

    def test_no_selector_omits_content_column(self, subscription, output):
        subscription.filehandle.flush()
        rows = list(csv.reader(output.open()))
        assert "content" not in rows[0]
        assert len(rows[0]) == 9

    def test_non_html_content_type_skips_extraction(
        self, subscription_with_selector, output
    ):
        for ctype in ("text/css", "application/javascript", "image/png"):
            page = make_page(
                content=b"<p class='content'>ignored</p>",
                headers={"content-type": ctype},
            )
            subscription_with_selector(page)
        subscription_with_selector.filehandle.flush()
        rows = list(csv.reader(output.open()))
        for row in rows[1:]:
            assert row[-1] == "", "expected empty content for non-HTML page"

    def test_missing_content_type_skips_extraction(
        self, subscription_with_selector, output
    ):
        page = make_page(content=b"<p class='content'>ignored</p>", headers={})
        subscription_with_selector(page)
        subscription_with_selector.filehandle.flush()
        rows = list(csv.reader(output.open()))
        assert rows[1][-1] == ""

    def test_selector_html_content_written_to_csv(
        self, subscription_with_selector, output
    ):
        page = make_page(
            content=b"<html><body><p class='content'>Hi</p></body></html>",
            headers={"content-type": "text/html"},
        )
        subscription_with_selector(page)
        subscription_with_selector.filehandle.flush()
        rows = list(csv.reader(output.open()))
        assert rows[1][-1] == '<p class="content">Hi</p>'

    def test_selector_text_content_written_to_csv(self, output):
        sub = ReportSubscription(
            output, show_progress=False, selector="p", formats=(FORMAT_TEXT,)
        )
        page = make_page(
            content=b"<html><body><p>Hello <em>world</em></p></body></html>",
            headers={"content-type": "text/html"},
        )
        sub(page)
        sub.filehandle.flush()
        rows = list(csv.reader(output.open()))
        assert rows[1][-1] == "Hello world"

    def test_multiple_formats_written_to_csv(self, output):
        sub = ReportSubscription(
            output,
            show_progress=False,
            selector="p",
            formats=(FORMAT_HTML, FORMAT_TEXT),
        )
        page = make_page(
            content=b"<html><body><p>Hello <em>world</em></p></body></html>",
            headers={"content-type": "text/html"},
        )
        sub(page)
        sub.filehandle.flush()
        rows = list(csv.reader(output.open()))
        html_col, text_col = rows[1][-2:]
        assert html_col == "<p>Hello <em>world</em></p>"
        assert text_col == "Hello world"


HTML_FIXTURE = b"<html><body><p class='content'>Hello <em>world</em></p></body></html>"


class TestExtractContent:
    def _make_sub(self, output, selector="p.content", formats=(FORMAT_HTML,)):
        return ReportSubscription(
            output, show_progress=False, selector=selector, formats=formats
        )

    def _page(self, content):
        page = MagicMock()
        page.content = content
        return page

    def test_returns_dict_keyed_by_format(self, output):
        sub = self._make_sub(output, formats=(FORMAT_HTML, FORMAT_TEXT))
        result = sub._extract_content(self._page(HTML_FIXTURE))
        assert set(result.keys()) == {FORMAT_HTML, FORMAT_TEXT}

    def test_returns_outer_html_of_first_match(self, output):
        sub = self._make_sub(output)
        result = sub._extract_content(self._page(HTML_FIXTURE))
        assert result[FORMAT_HTML] == '<p class="content">Hello <em>world</em></p>'

    def test_returns_plain_text_when_text_format_requested(self, output):
        sub = self._make_sub(output, formats=(FORMAT_TEXT,))
        result = sub._extract_content(self._page(HTML_FIXTURE))
        assert result[FORMAT_TEXT] == "Hello world"

    def test_plain_text_preserves_block_linebreaks(self, output):
        sub = self._make_sub(output, selector="div", formats=(FORMAT_TEXT,))
        page = self._page(b"<div><p>First</p><p>Second</p></div>")
        text = sub._extract_content(page)[FORMAT_TEXT]
        # inscriptis renders block elements separated by newlines
        assert "First" in text
        assert "Second" in text
        assert text.index("First") < text.index("Second")
        assert "\n" in text

    def test_no_match_returns_empty_strings(self, output):
        sub = self._make_sub(output, formats=(FORMAT_HTML, FORMAT_TEXT))
        result = sub._extract_content(
            self._page(b"<html><body><div>nope</div></body></html>")
        )
        assert result == {FORMAT_HTML: "", FORMAT_TEXT: ""}

    def test_empty_content_returns_empty_strings(self, output):
        sub = self._make_sub(output, formats=(FORMAT_HTML, FORMAT_TEXT))
        assert sub._extract_content(self._page(b"")) == {
            FORMAT_HTML: "",
            FORMAT_TEXT: "",
        }

    def test_parse_error_returns_empty_strings(self, output):
        sub = self._make_sub(output, formats=(FORMAT_HTML, FORMAT_TEXT))
        with patch("caliper.crawl.HTMLParser", side_effect=Exception("parse error")):
            result = sub._extract_content(self._page(b"<html></html>"))
        assert result == {FORMAT_HTML: "", FORMAT_TEXT: ""}


@pytest.fixture
def mock_website():
    with patch("caliper.crawl.Website") as mock_cls:
        instance = MagicMock()
        for method in (
            "with_full_resources",
            "with_respect_robots_txt",
            "with_user_agent",
            "with_whitelist_url",
            "with_store_page_results",
        ):
            getattr(instance, method).return_value = instance
        mock_cls.return_value = instance
        yield mock_cls, instance


class TestCrawl:
    def test_website_initialized_with_url(self, tmp_path, mock_website):
        mock_cls, _ = mock_website
        asyncio.run(
            crawl("https://example.com/", tmp_path / "out.csv", show_progress=False)
        )
        mock_cls.assert_called_once_with("https://example.com/")

    def test_website_options_configured(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(
            crawl("https://example.com/", tmp_path / "out.csv", show_progress=False)
        )
        instance.with_full_resources.assert_called_once_with(True)
        instance.with_respect_robots_txt.assert_called_once_with(True)
        instance.with_user_agent.assert_called_once_with(USER_AGENT)

    def test_html_only_disables_full_resources(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(
            crawl(
                "https://example.com/",
                tmp_path / "out.csv",
                show_progress=False,
                html_only=True,
            )
        )
        instance.with_full_resources.assert_called_once_with(False)

    def test_whitelist_applied_for_subpath(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(
            crawl(
                "https://example.com/blog/", tmp_path / "out.csv", show_progress=False
            )
        )
        instance.with_whitelist_url.assert_called_once_with(["/blog/"])

    def test_whitelist_applied_for_path_without_trailing_slash(
        self, tmp_path, mock_website
    ):
        _, instance = mock_website
        asyncio.run(
            crawl(
                "https://example.com/licenses",
                tmp_path / "out.csv",
                show_progress=False,
            )
        )
        instance.with_whitelist_url.assert_called_once_with(["/licenses"])

    def test_no_whitelist_for_root_slash(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(
            crawl("https://example.com/", tmp_path / "out.csv", show_progress=False)
        )
        instance.with_whitelist_url.assert_not_called()

    def test_no_whitelist_for_bare_domain(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(
            crawl("https://example.com", tmp_path / "out.csv", show_progress=False)
        )
        instance.with_whitelist_url.assert_not_called()

    def test_crawl_called_with_subscription(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(
            crawl("https://example.com/", tmp_path / "out.csv", show_progress=False)
        )
        instance.crawl.assert_called_once()
        assert isinstance(instance.crawl.call_args[0][0], ReportSubscription)

    def test_selector_passed_to_subscription(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(
            crawl(
                "https://example.com/",
                tmp_path / "out.csv",
                show_progress=False,
                selector="main",
            )
        )
        subscription = instance.crawl.call_args[0][0]
        assert subscription.selector == "main"

    def test_formats_passed_to_subscription(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(
            crawl(
                "https://example.com/",
                tmp_path / "out.csv",
                show_progress=False,
                selector="main",
                formats=(FORMAT_HTML, FORMAT_TEXT),
            )
        )
        subscription = instance.crawl.call_args[0][0]
        assert subscription.formats == (FORMAT_HTML, FORMAT_TEXT)

    def test_no_selector_by_default(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(
            crawl("https://example.com/", tmp_path / "out.csv", show_progress=False)
        )
        subscription = instance.crawl.call_args[0][0]
        assert subscription.selector is None
        assert subscription.formats == ()


class TestMain:
    def test_calls_crawl_with_url_and_output(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl,
            patch("sys.argv", ["caliper", "https://example.com", str(output)]),
        ):
            main()
        mock_crawl.assert_called_once_with(
            "https://example.com",
            pathlib.Path(str(output)),
            show_progress=True,
            selector=None,
            formats=(),
            html_only=False,
        )

    def test_progress_defaults_to_true(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl,
            patch("sys.argv", ["caliper", "https://example.com", str(output)]),
        ):
            main()
        _, kwargs = mock_crawl.call_args
        assert kwargs["show_progress"] is True

    def test_no_progress_flag(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl,
            patch(
                "sys.argv",
                ["caliper", "--no-progress", "https://example.com", str(output)],
            ),
        ):
            main()
        _, kwargs = mock_crawl.call_args
        assert kwargs["show_progress"] is False

    def test_invalid_selector_raises_systemexit(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch(
                "sys.argv",
                [
                    "caliper",
                    "--select",
                    "[invalid{{",
                    "https://example.com",
                    str(output),
                ],
            ),
        ):
            with pytest.raises(SystemExit, match="Invalid CSS selector"):
                main()

    def test_keyboard_interrupt_raises_systemexit(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch(
                "caliper.crawl.crawl",
                new_callable=AsyncMock,
                side_effect=KeyboardInterrupt,
            ),
            patch("sys.argv", ["caliper", "https://example.com", str(output)]),
        ):
            with pytest.raises(SystemExit):
                main()

    def test_selector_default_is_none(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl,
            patch("sys.argv", ["caliper", "https://example.com", str(output)]),
        ):
            main()
        _, kwargs = mock_crawl.call_args
        assert kwargs["selector"] is None

    def test_selector_arg_passed_through_defaults_to_html_format(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl,
            patch(
                "sys.argv",
                [
                    "caliper",
                    "--select",
                    "article.main",
                    "https://example.com",
                    str(output),
                ],
            ),
        ):
            main()
        _, kwargs = mock_crawl.call_args
        assert kwargs["selector"] == "article.main"
        assert kwargs["formats"] == ("html",)

    def test_text_flag_sets_text_format(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl,
            patch(
                "sys.argv",
                [
                    "caliper",
                    "--select",
                    "p",
                    "--text",
                    "https://example.com",
                    str(output),
                ],
            ),
        ):
            main()
        _, kwargs = mock_crawl.call_args
        assert kwargs["formats"] == ("text",)

    def test_format_text_equivalent_to_text(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl,
            patch(
                "sys.argv",
                [
                    "caliper",
                    "--select",
                    "p",
                    "--format",
                    "text",
                    "https://example.com",
                    str(output),
                ],
            ),
        ):
            main()
        _, kwargs = mock_crawl.call_args
        assert kwargs["formats"] == ("text",)

    def test_format_html_text_yields_both(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl,
            patch(
                "sys.argv",
                [
                    "caliper",
                    "--select",
                    "p",
                    "--format",
                    "html,text",
                    "https://example.com",
                    str(output),
                ],
            ),
        ):
            main()
        _, kwargs = mock_crawl.call_args
        assert kwargs["formats"] == ("html", "text")

    def test_format_invalid_raises_systemexit(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch(
                "sys.argv",
                [
                    "caliper",
                    "--select",
                    "p",
                    "--format",
                    "markdown",
                    "https://example.com",
                    str(output),
                ],
            ),
        ):
            with pytest.raises(SystemExit, match="Unsupported format"):
                main()

    def test_text_and_format_mutually_exclusive(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch(
                "sys.argv",
                [
                    "caliper",
                    "--select",
                    "p",
                    "--text",
                    "--format",
                    "html",
                    "https://example.com",
                    str(output),
                ],
            ),
        ):
            with pytest.raises(SystemExit):
                main()

    def test_formats_empty_when_no_selector(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl,
            patch("sys.argv", ["caliper", "https://example.com", str(output)]),
        ):
            main()
        _, kwargs = mock_crawl.call_args
        assert kwargs["formats"] == ()

    def test_html_only_default_is_false(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl,
            patch("sys.argv", ["caliper", "https://example.com", str(output)]),
        ):
            main()
        _, kwargs = mock_crawl.call_args
        assert kwargs["html_only"] is False

    def test_html_only_flag_passed_through(self, tmp_path):
        output = tmp_path / "out.csv"
        with (
            patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl,
            patch(
                "sys.argv",
                ["caliper", "--html-only", "https://example.com", str(output)],
            ),
        ):
            main()
        _, kwargs = mock_crawl.call_args
        assert kwargs["html_only"] is True

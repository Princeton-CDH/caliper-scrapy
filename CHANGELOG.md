# Change & Version Information

## 0.3

- Crawl is now automatically limited to URLs under the starting URL path when
  given a non-top-level URL, rather than crawling the entire site.
- New `--html-only` option to crawl HTML pages only, skipping other resources
  (CSS, JS, images, etc.).
- New `--select` option takes a CSS selector and adds an extra `content` column
  to the CSV report with the matched HTML extracted from each page.
- New `--format` option (used with `--select`) controls the extracted content
  format(s); accepts a comma-separated list of `html` and `text` and adds one
  column per requested format (`content_html` / `content_text`).
- New `--text` option is a shorthand for `--format text`.
- Plain-text extraction now uses [inscriptis](https://github.com/weblyzard/inscriptis)
  for higher-quality rendering of block elements, lists, and tables.
- Minimum supported Python version is now 3.10; added support for Python 3.13
  and 3.14.
- Added GitHub Actions workflow for unit tests and code coverage reporting.
- Added unit tests for existing functionality.
- Added pre-commit hooks configuration.

## 0.2

Rewritten and implemented with [spider-py](https://github.com/spider-rs/spider-py).
Same functionality as 0.1 version.

## 0.1

Initial version; implemented with [Scrapy](https://www.scrapy.org/)

# caliper

Caliper is a custom webspider for crawling and reporting on website content and urls.
Caliper 0.2+ is implemented with [spider-py](https://github.com/spider-rs/spider-py).

When given a starting url, Caliper will crawl all content on that site within the
same domain and generate a report of the urls found, including HTTP status code,
last modified header, content type, content length, size, and date
when the page was accessed.

## Initial setup and installation:

- **Recommended:** create and activate a python 3.x virtual environment

- Use pip to install required python dependencies:

```sh
pip install -e .
```

## Usage

To run the spider, call it with the URL for the site you want to crawl and the output filename for the CSV report to be generated. Only links within the same domain (local URLs or absolute) will be followed.

```sh
caliper https://startwords.cdh.princeton.edu startwords-datetime-vXX.csv
```

If the starting URL has a non-root path (e.g. `https://example.com/blog/`),
the crawl is automatically restricted to URLs under that path.

#### Options

- `--html-only` — crawl HTML pages only, skipping other resources (CSS, JS, images, etc.).
- `--select CSS_SELECTOR` — extract content matching the given CSS selector
  from each HTML page into an additional column in the CSV report.
- `--format html|text|html,text` — when used with `--select`, control which
  content format(s) to extract. Multiple formats produce one column each
  (`content_html`, `content_text`). Defaults to `html`. Plain-text extraction
  uses [inscriptis](https://github.com/weblyzard/inscriptis).
- `--text` — shorthand for `--format text`.
- `--no-progress` — suppress progress output.

Examples:

```sh
# extract the article HTML
caliper --select "article" https://example.com/blog/ out.csv

# extract plain text only
caliper --select "article" --text https://example.com/blog/ out.csv

# extract both HTML and text into separate columns
caliper --select "article" --format html,text https://example.com/blog/ out.csv
```

### Development Setup

Install development dependencies:

```
pip install -e ".[dev]""
```

If you plan to contribute to this repository, install the configured pre-commit hooks:

```
pre-commit install
```

## License

`caliper` is distributed under the terms of the [Apache 2](LICENSE) license.

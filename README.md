# caliper

Caliper is a custom [Scrapy](https://docs.scrapy.org/en/latest/) webspider for crawling and reporting on website content and urls.

When given a starting url, Caliper will crawl all content on that site within the
same domain and generate a report of the urls found, including the HTTP status code,
last modified header, content type, content length, size, refering url, and a timestamp
of when the page was accessed.

## Initial setup and installation:

- **Recommended:** create and activate a python 3.x virtual environment

- Use pip to install required python dependencies:
```
pip install -r requirements.txt
```


## Usage

To run the spider, call it with scrapy and specify the url for the site you want to crawl.  Only links within the same domain (local urls or absolute) will be followed

Output format is automatically determined by the file extension (e.g. csv, json, and jl; see scrapy documentation for more details).
```
scrapy crawl caliper -a url=https://cdh.princeton.edu -o cdh-datetime-vXX.csv
```
When it finishes, caliper will report on any iframes found on the site (with the url where they were found) and any pages with error codes (with the code and the referring url).


### Development Setup

Install development dependencies:
```
pip install -r requirements/dev.txt
```

If you plan to contribute to this repository, install the configured pre-commit hooks:
```
pre-commit install
```

This will add a pre-commit hook to automatically style your python code with `[black](https://github.com/psf/black) and [isort](https://github.com/pycqa/isort).

Because these styling conventions were instituted after multiple releases of
development on this project, ``git blame`` may not reflect the true author
of a given line. In order to see a more accurate ``git blame`` execute the
following command::
```
git blame <FILE> --ignore-revs-file .git-blame-ignore-revs
```

Or configure your git to always ignore styling revision commits:
```
git config blame.ignoreRevsFile .git-blame-ignore-revs
```


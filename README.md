# caliper-scrapy
scrapy spider for crawling and reporting on website content and urls

## Initial setup and installation:

- **Recommended:** create and activate a python 3.x virtual environment

- Use pip to install required python dependencies:

   pip install -r requirements.txt

## Usage

To run the spider, call it with scrapy and specify the url for the site you want to crawl.  Only links within the same domain (local urls or absolute) will be followed

Output format is automatically determined by the file extension (e.g. csv, json, and jl; see scrapy documentation for more details).

scrapy crawl caliper -a url=https://cdh.princeton.edu -o cdh-datetime-vXX.jl

When it finishes, caliper will report on any iframes found on the site (with the url where they were found) and any pages with error codes (with the code and the referring url).
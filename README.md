# El País Opinion Scraper — BrowserStack Assessment

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Selenium](https://img.shields.io/badge/selenium-4.18-green.svg)](https://www.selenium.dev/)
[![BrowserStack](https://img.shields.io/badge/BrowserStack-Parallel%20Testing-orange)](https://www.browserstack.com/)

A Python + Selenium solution that scrapes the Opinion section of [El País](https://elpais.com), translates article headers from Spanish to English, analyzes word frequency, and validates cross-browser compatibility via BrowserStack across 5 parallel threads.

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/elpais-opinion-scraper.git

# Install dependencies
pip install -r requirements.txt

# Set up credentials
cp .env.example .env
# Edit .env with your API keys

# Run locally
python scraper.py

# Run on BrowserStack (5 parallel browsers)
python browserstack_parallel.py

## Features

- Scrapes the first 5 articles from El País Opinion section
- Verifies the page is served in Spanish
- Prints title and content of each article in Spanish
- Downloads cover images to local machine
- Translates all titles to English via Rapid Translate Multi Traduction API
- Identifies words repeated more than twice across all translated headers
- Runs cross-browser tests in parallel on BrowserStack across 3 desktop + 2 mobile browsers

---

## Project Structure

```
├── scraper.py                  # Local validation — runs on Chrome
├── browserstack_parallel.py    # BrowserStack — 5 parallel browser sessions
├── requirements.txt            # Python dependencies
├── .env                        # Credentials (not committed — see .env.example)
├── .env.example                # Template for required credentials
└── .gitignore
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

```env
rapidapi_key=your_rapidapi_key
browserstack_username=your_browserstack_username
browserstack_access_key=your_browserstack_access_key
```

- **RapidAPI key** — sign up at [rapidapi.com](https://rapidapi.com) and subscribe to [Rapid Translate Multi Traduction](https://rapidapi.com/sibaridev/api/rapid-translate-multi-traduction)
- **BrowserStack credentials** — find at [browserstack.com/accounts/settings](https://www.browserstack.com/accounts/settings) under the Automate section

---

## Usage

### Run locally (Chrome)

Validates the full scraping, translation, and word frequency flow on your machine:

```bash
python scraper.py
```

### Run on BrowserStack (5 parallel sessions)

```bash
python browserstack_parallel.py
```

---

## Browsers Tested on BrowserStack

| # | Browser | OS / Device | Type |
|---|---------|-------------|------|
| 1 | Chrome (latest) | Windows 11 | Desktop |
| 2 | Safari 16 | macOS Ventura | Desktop |
| 3 | Firefox (latest) | Windows 11 | Desktop |
| 4 | Safari | iPhone 14 (iOS 16) | Mobile |
| 5 | Chrome | Samsung Galaxy S23 (Android 13) | Mobile |

All 5 sessions start simultaneously via `ThreadPoolExecutor(max_workers=5)`.

---

## Output

### Local run (`scraper.py`)

```
Opened  : https://elpais.com/
Language: 'es'
Confirmed: Page is in Spanish

Article 1 of 5
Title   (🇪🇸) : Caiga quien caiga
Content (🇪🇸) : La investigación de Interior sobre...
URL          : https://elpais.com/opinion/...
Image saved → article_images/article_1_cover.jpg

...

Translated Headers-
  [1]  🇪🇸  Caiga quien caiga
        🇬🇧  Whoever falls falls

Word Frequency Analysis of Translated Headers
  Titles analyzed : 5
  Total words     : 18
  Unique words    : 17
  Top 5 most frequent words:
    falls                  2 occurrences
    ...
```

### BrowserStack run (`browserstack_parallel.py`)

```
============================================================
  BrowserStack Parallel Cross-Browser Test

  Browsers under test:
    [1] Win11 / Chrome
    [2] macOS Ventura / Safari
    [3] Win11 / Firefox
    [4] iPhone 14 / Safari
    [5] Samsung Galaxy S23 / Chrome

...

============================================================
Parallel Run Summary

  Total time : 113.5s
  Passed     : 5/5
  Failed     : 0/5

  ✅  iPhone 14 / Safari
  ✅  Samsung Galaxy S23 / Chrome
  ✅  Win11 / Chrome
  ✅  Win11 / Firefox
  ✅  macOS Ventura / Safari

Execution Completed!
```

---

## Implementation Notes

**Two-phase scraping in `browserstack_parallel.py`**

To prevent `StaleElementReferenceException` (caused by DOM refresh when navigating away from the listing page), scraping is split into two phases:

- **Phase 1** — Read all 5 article cards in a single pass before any `driver.get()` call. Extracts title, URL, content snippet, and cover image.
- **Phase 2** — Navigate to individual article pages only for entries where the title or content is still missing (common on mobile Safari due to lazy rendering below the fold).

**Safari-specific handling**

- `browser_version` passed via `bstack:options` instead of `options.browser_version` — Safari WebDriver rejects the latter
- 35-second timeout for Safari vs 25 seconds for Chrome/Firefox
- 3 fallback selectors for cookie consent banner (renders differently on Safari)

**Mobile lazy loading**

On mobile devices, articles below the fold are lazy-loaded. The scraper scrolls down 4 viewport heights before collecting article cards to ensure all 5 are present in the DOM.

**Thread-safe printing**

A `threading.Lock()` wraps every `print()` call via `tprint()` to prevent interleaved output from 5 concurrent threads.

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| selenium | 4.18.1 | Browser automation |
| webdriver-manager | 4.0.1 | Auto-manages ChromeDriver |
| requests | 2.31.0 | HTTP calls (translate API, image download) |
| nltk | 3.9.1 | Word tokenization |
| python-dotenv | 1.0.1 | Loads `.env` credentials |

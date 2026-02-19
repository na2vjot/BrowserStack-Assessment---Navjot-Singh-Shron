import os
import re
import time
import threading
import requests
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import nltk
from nltk.tokenize import word_tokenize
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

load_dotenv()

# NLTK — download tokenizer data once on first run
nltk.download("punkt",     quiet=True)
nltk.download("punkt_tab", quiet=True)

# Credentials from .env
rapidapi_key            = os.environ.get("rapidapi_key", "")
browserstack_username   = os.environ.get("browserstack_username", "")
browserstack_access_key = os.environ.get("browserstack_access_key", "")

# BrowserStack remote hub URL
bs_hub_url = f"https://{browserstack_username}:{browserstack_access_key}@hub-cloud.browserstack.com/wd/hub"

# Rapid Translate endpoint
translate_url = "https://rapid-translate-multi-traduction.p.rapidapi.com/t"
rapidapi_host = "rapid-translate-multi-traduction.p.rapidapi.com"

# 5 browser configs — 3 desktop + 2 mobile
BROWSER_CONFIGS = [
    {
        "label":          "Win11 / Chrome",
        "browserName":    "Chrome",
        "browserVersion": "latest",
        "os":             "Windows",
        "osVersion":      "11",
    },
    {
        "label":          "macOS Ventura / Safari",
        "browserName":    "Safari",
        "browserVersion": "16",
        "os":             "OS X",
        "osVersion":      "Ventura",
    },
    {
        "label":          "Win11 / Firefox",
        "browserName":    "Firefox",
        "browserVersion": "latest",
        "os":             "Windows",
        "osVersion":      "11",
    },
    {
        "label":       "iPhone 14 / Safari",
        "deviceName":  "iPhone 14",
        "osVersion":   "16",
        "browserName": "Safari",
        "realMobile":  "true",
    },
    {
        "label":       "Samsung Galaxy S23 / Chrome",
        "deviceName":  "Samsung Galaxy S23",
        "osVersion":   "13.0",
        "browserName": "Chrome",
        "realMobile":  "true",
    },
]

#prevents garbled output from 5 parallel threads
print_lock = threading.Lock()

def tprint(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)


def create_bs_driver(config: dict) -> webdriver.Remote:
    browser     = config.get("browserName", "Chrome").lower()
    label       = config["label"]
    bstack_opts = {
        "sessionName": f"El Pais — {label}",
        "projectName": "El Pais Opinion Scraper",
        "buildName":   "Parallel Run — 5 Browsers",
        "consoleLogs": "info",
        "networkLogs": True,
    }

    # Desktop
    if "deviceName" not in config:
        bstack_opts["os"]        = config["os"]
        bstack_opts["osVersion"] = config["osVersion"]

        if browser == "chrome":
            options = webdriver.ChromeOptions()
            options.add_argument("--lang=es")
            options.add_argument("--accept-lang=es-ES,es;q=0.9")
            options.add_experimental_option("prefs", {"intl.accept_languages": "es,es_ES"})
            options.browser_version = config.get("browserVersion", "latest")
        elif browser == "firefox":
            options = webdriver.FirefoxOptions()
            options.set_preference("intl.accept_languages", "es-ES, es")
            options.browser_version = config.get("browserVersion", "latest")
        elif browser == "safari":
            # Safari rejects options.browser_version — pass via bstack_opts instead
            options = webdriver.SafariOptions()
            bstack_opts["browserVersion"] = config.get("browserVersion", "16")
        else:
            options = webdriver.ChromeOptions()
            options.browser_version = config.get("browserVersion", "latest")

    # Mobile
    else:
        bstack_opts["deviceName"] = config["deviceName"]
        bstack_opts["osVersion"]  = config["osVersion"]
        bstack_opts["realMobile"] = config.get("realMobile", "true")
        options = webdriver.ChromeOptions() if browser == "chrome" else webdriver.SafariOptions()
        if browser == "chrome":
            options.add_argument("--lang=es")

    options.set_capability("bstack:options", bstack_opts)
    return webdriver.Remote(command_executor=bs_hub_url, options=options)


def translate_titles(titles: list[str]) -> list[str]:
    if not rapidapi_key:
        return ["[Translation skipped — set rapidapi_key in .env]"] * len(titles)
    try:
        headers = {
            "content-type":   "application/json",
            "X-RapidAPI-Key":  rapidapi_key,
            "X-RapidAPI-Host": rapidapi_host,
        }
        payload  = {"from": "es", "to": "en", "e": "", "q": titles}
        response = requests.post(translate_url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else [str(data)] * len(titles)
    except requests.exceptions.HTTPError:
        tprint(f"Translation HTTP error {response.status_code}: {response.text[:200]}")
    except Exception as e:
        tprint(f"Translation error: {e}")
    return ["[Translation error]"] * len(titles)


def download_image(url: str, filename: str, folder: str = "article_images") -> None:
    os.makedirs(folder, exist_ok=True)
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()
        ext      = url.split("?")[0].rsplit(".", 1)[-1]
        ext      = ext if ext in ("jpg", "jpeg", "png", "webp", "gif") else "jpg"
        filepath = os.path.join(folder, f"{filename}.{ext}")
        with open(filepath, "wb") as f:
            f.write(response.content)
        tprint(f"Image saved → {filepath}")
    except Exception as e:
        tprint(f"Image download failed: {e}")


def analyze_word_frequency(articles: list[dict], label: str) -> None:
    tprint(f"\n  [{label}] Word Frequency Analysis of Translated Headers")
    tprint(f"  {'-' * 50}")

    all_words = []
    for article in articles:
        title = article.get("title_english", "")
        if not title or title.startswith("["):
            continue
        tokens = word_tokenize(title.lower())
        all_words.extend([
            w for w in tokens
            if re.fullmatch(r"[^\W\d_]+", w) and len(w) > 2
            # and w not in STOP_WORDS  # uncomment to filter stop words
        ])

    if not all_words:
        tprint(f"  [{label}] No translated titles to analyze.")
        return

    word_counts = Counter(all_words)
    repeated    = {w: c for w, c in word_counts.items() if c > 2}

    tprint(f"\n  Titles analyzed : {len(articles)}")
    tprint(f"  Total words     : {len(all_words)}")
    tprint(f"  Unique words    : {len(word_counts)}")

    if repeated:
        tprint("  Words repeated MORE than twice (count > 2):\n")
        for word, count in sorted(repeated.items(), key=lambda x: (-x[1], x[0])):
            tprint(f"    {word:<20} {count:>3} occurrences")
    else:
        tprint("  No word appears more than twice across all 5 titles.")
        tprint("\n  Top 5 most frequent words:\n")
        for word, count in word_counts.most_common(5):
            tprint(f"    {word:<20} {count:>3} occurrences")
    tprint()


def run_test(config: dict) -> dict:
    label         = config["label"]
    driver        = None
    articles_data = []
    is_mobile     = "deviceName" in config
    safe_label    = label.replace(" ", "_").replace("/", "-")

    tprint(f"\n[{label}] Starting session..")

    try:
        driver  = create_bs_driver(config)
        timeout = 35 if "safari" in config.get("browserName", "").lower() else 25
        wait    = WebDriverWait(driver, timeout)

        # Open El País + verify Spanish
        driver.get("https://elpais.com")
        tprint(f"  [{label}] Opened: {driver.current_url}")
        html_lang = driver.find_element(By.TAG_NAME, "html").get_attribute("lang") or ""
        tprint(f"  [{label}] {'Confirmed: Page is in Spanish' if 'es' in html_lang.lower() else 'Warning: Spanish not confirmed'}")

        # Cookie consent — 3 fallback selectors for cross-browser compatibility
        cookie_selectors = [
            (By.XPATH, "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'aceptar')]"),
            (By.XPATH, "//button[@id='didomi-notice-agree-button']"),
            (By.CSS_SELECTOR, "button.didomi-components-button--highlight"),
        ]
        for selector in cookie_selectors:
            try:
                WebDriverWait(driver, 7).until(EC.element_to_be_clickable(selector)).click()
                tprint(f"  [{label}] Cookie consent accepted")
                time.sleep(2)
                break
            except TimeoutException:
                continue
        else:
            tprint(f"  [{label}] No cookie banner detected")

        # Navigate to Opinion section
        try:
            wait.until(EC.element_to_be_clickable(
                (By.XPATH, "/html/body/div[4]/header/div[2]/div[1]/nav/div/a[2]")
            )).click()
        except TimeoutException:
            tprint(f"  [{label}] Nav link not clickable — navigating directly to /opinion/")
            driver.get("https://elpais.com/opinion/")

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "article")))
        tprint(f"  [{label}] Opinion section loaded")

        # Mobile — scroll to trigger lazy loading before collecting cards
        if is_mobile:
            tprint(f"  [{label}] Mobile — scrolling to load all articles...")
            for _ in range(4):
                driver.execute_script("window.scrollBy(0, window.innerHeight);")
                time.sleep(1.5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

        cards = driver.find_elements(By.TAG_NAME, "article")[:5]
        tprint(f"  [{label}] Found {len(cards)} articles. Extracting..")

        # ── Phase 1: Read all cards before any navigation ────────────
        # Extracting everything from the listing page in one pass
        # before calling driver.get() prevents StaleElementReferenceException.
        card_data = []
        for card in cards:
            info = {"title": "N/A", "content": "N/A", "article_url": None, "image_url": None}

            # Title
            for sel in ["h2", "h3", "h2 a", "h3 a"]:
                try:
                    t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                    if t and t.lower() not in ("opinión", "opinion"):
                        info["title"] = t
                        break
                except NoSuchElementException:
                    continue

            # Article URL — prefer URLs with a date slug (individual articles)
            # e.g. /opinion/2025-02-19/article-title.html vs /opinion/editoriales/
            try:
                links = card.find_elements(By.CSS_SELECTOR, "a[href]")
                for link in links:
                    href = link.get_attribute("href") or ""
                    if re.search(r"/\d{4}-\d{2}-\d{2}/", href):
                        info["article_url"] = href
                        break
                if not info["article_url"] and links:
                    info["article_url"] = links[0].get_attribute("href")
            except NoSuchElementException:
                pass

            # Content snippet
            try:
                info["content"] = card.find_element(By.CSS_SELECTOR, "p").text.strip()
            except NoSuchElementException:
                pass

            # Cover image
            try:
                img = card.find_element(By.CSS_SELECTOR, "img")
                for attr in ("src", "data-src", "data-lazy-src", "data-srcset"):
                    val = img.get_attribute(attr)
                    if val and val.startswith("http"):
                        info["image_url"] = val.split(",")[0].split(" ")[0]
                        break
            except NoSuchElementException:
                pass

            card_data.append(info)

        # ── Phase 2: Navigate to article page only if title/content missing ──
        # Desktop browsers usually have complete data from Phase 1.
        # Mobile Safari may need article page for titles below the fold.
        for idx, info in enumerate(card_data, start=1):
            needs_title   = info["title"]   in ("N/A", "")
            needs_content = info["content"] in ("N/A", "")

            if (needs_title or needs_content) and info["article_url"]:
                try:
                    driver.get(info["article_url"])
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "h1, article p"))
                    )
                    if needs_title:
                        for sel in ["article h1", ".a_t", "h1.a_t", "h1"]:
                            try:
                                t = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                                if t and t.lower() not in ("opinión", "opinion"):
                                    info["title"] = t
                                    break
                            except NoSuchElementException:
                                continue
                    if needs_content:
                        paras = driver.find_elements(By.CSS_SELECTOR, "article p, .a_c p")
                        if paras:
                            info["content"] = " ".join(
                                p.text.strip() for p in paras[:4] if p.text.strip()
                            )[:1000]
                    if not info["image_url"]:
                        try:
                            img = driver.find_element(By.CSS_SELECTOR, "article img, figure img")
                            for attr in ("src", "data-src", "data-lazy-src"):
                                val = img.get_attribute(attr)
                                if val and val.startswith("http"):
                                    info["image_url"] = val
                                    break
                        except NoSuchElementException:
                            pass
                except Exception as e:
                    tprint(f"  [{label}] Could not fetch article {idx}: {e}")

            tprint(f"\n  [{label}] Article {idx}")
            tprint(f"    Title   (🇪🇸) : {info['title']}")
            tprint(f"    Content (🇪🇸) : {info['content'][:200]}...")
            tprint(f"    URL           : {info['article_url']}")

            if info["image_url"]:
                download_image(info["image_url"], filename=f"{safe_label}_article_{idx}_cover")
            else:
                tprint(f"  [{label}] No cover image found.")

            articles_data.append(info)

        # Translate all titles in one API call
        tprint(f"\n  [{label}] Translating titles via Rapid Translate Multi Traduction API...")
        english_titles = translate_titles([a["title"] for a in articles_data])
        for i, article in enumerate(articles_data):
            article["title_english"] = english_titles[i] if i < len(english_titles) else "[Error]"

        # Print translated headers
        tprint(f"\n  [{label}] Translated Headers-")
        for i, a in enumerate(articles_data, start=1):
            tprint(f"    [{i}]  🇪🇸  {a['title']}")
            tprint(f"          🇬🇧  {a['title_english']}")

        # Word frequency analysis
        analyze_word_frequency(articles_data, label)

        # Mark session passed on BrowserStack dashboard
        driver.execute_script(
            'browserstack_executor: {"action": "setSessionStatus",'
            '"arguments": {"status":"passed","reason":"All 5 articles scraped successfully"}}'
        )
        tprint(f"\n  [{label}] Session Passed!")
        return {"label": label, "status": "passed", "error": None}

    except Exception as e:
        tprint(f"\n  [{label}] Session FAILED ❌ — {e}")
        if driver:
            try:
                driver.execute_script(
                    f'browserstack_executor: {{"action": "setSessionStatus",'
                    f'"arguments": {{"status":"failed","reason":"{str(e)[:120]}"}}}}'
                )
            except Exception:
                pass
        return {"label": label, "status": "failed", "error": str(e)}

    finally:
        if driver:
            driver.quit()


def run_parallel():
    print("=" * 60)
    print("  BrowserStack Parallel Cross-Browser Test")
    print("\n  Browsers under test:")
    for i, cfg in enumerate(BROWSER_CONFIGS, 1):
        print(f"    [{i}] {cfg['label']}")
    print()

    start_time = time.time()
    results    = []

    # max_workers=5 — all 5 sessions start simultaneously
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(run_test, cfg): cfg["label"] for cfg in BROWSER_CONFIGS}
        for future in as_completed(futures):
            label = futures[future]
            try:
                results.append(future.result())
            except Exception as e:
                tprint(f"  [{label}] Unhandled exception: {e}")
                results.append({"label": label, "status": "failed", "error": str(e)})

    elapsed = time.time() - start_time
    passed  = [r for r in results if r["status"] == "passed"]
    failed  = [r for r in results if r["status"] == "failed"]

    print("\n" + "=" * 60)
    print("Parallel Run Summary")
    print(f"\n  Total time : {elapsed:.1f}s")
    print(f"  Passed     : {len(passed)}/5")
    print(f"  Failed     : {len(failed)}/5\n")
    for r in sorted(results, key=lambda x: x["label"]):
        icon = "✅" if r["status"] == "passed" else "❌"
        err  = f" — {r['error'][:60]}" if r["error"] else ""
        print(f"  {icon}  {r['label']}{err}")
    print("\nExecution Completed!")


if __name__ == "__main__":
    missing = []
    if not browserstack_username:   missing.append("browserstack_username")
    if not browserstack_access_key: missing.append("browserstack_access_key")
    if not rapidapi_key:            missing.append("rapidapi_key")

    if missing:
        print("Missing credentials in .env file:")
        for m in missing: print(f"  {m}=your_value_here")
        print("\nAdd them to your .env file and re-run.")
        exit(1)

    run_parallel()
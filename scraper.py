import os
import re
import time
import requests
from collections import Counter
from dotenv import load_dotenv
import nltk
from nltk.tokenize import word_tokenize
# from nltk.corpus import stopwords
from selenium import webdriver

# Load credentials from .env file
load_dotenv()
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# NLTK — download required datasets once on first run
nltk.download("punkt",     quiet=True)
nltk.download("punkt_tab", quiet=True)
# nltk.download("stopwords", quiet=True)

# STOP_WORDS = set(stopwords.words("english"))   # 179-word built-in list

#configure rapidapi key
rapidapi_key = os.environ.get("rapidapi_key", "your_rapidapi_key")

# Rapid Translate Multi Traduction endpoint + host
translate_url  = "https://rapid-translate-multi-traduction.p.rapidapi.com/t"
rapidapi_host  = "rapid-translate-multi-traduction.p.rapidapi.com"

#translate titles
def translate_titles(titles: list[str]) -> list[str]:
    """ Translates a list of Spanish titles to English in a single API call using Rapid Translate Multi Traduction (RapidAPI). """
    
    if not rapidapi_key:
        print("rapidapi_key not set in .env.")
        return ["[Translation skipped — set rapidapi_key in .env]"] * len(titles)

    try:
        headers = {
            "content-type":   "application/json",
            "X-RapidAPI-Key":  rapidapi_key,
            "X-RapidAPI-Host": rapidapi_host,
        }
        payload = {
            "from": "es",   #from spanish
            "to":   "en",   # to english
            "e":    "",
            "q":    titles, #tranlsate the titles
        }
        response = requests.post(translate_url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            return data
        return [str(data)] * len(titles)

    except requests.exceptions.HTTPError:
        print(f"Translation HTTP error {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"Translation error: {e}")

    return ["[Translation error]"] * len(titles)


#Image Download
def download_image(url: str, filename: str, folder: str = "article_images") -> None:
    os.makedirs(folder, exist_ok=True)
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()
        ext = url.split("?")[0].rsplit(".", 1)[-1]
        ext = ext if ext in ("jpg", "jpeg", "png", "webp", "gif") else "jpg"
        filepath = os.path.join(folder, f"{filename}.{ext}")
        with open(filepath, "wb") as f:
            f.write(response.content)
        print(f"Image saved → {filepath}")
    except Exception as e:
        print(f"Image download failed: {e}")

#Chrome Driver
def create_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--lang=es")
    options.add_argument("--accept-lang=es-ES,es;q=0.9")
    options.add_experimental_option("prefs", {"intl.accept_languages": "es,es_ES"})
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    # options.add_argument("--headless=new")  # uncomment to hide browser window

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

#Scraper
def scrape_opinion():
    driver = create_driver()
    wait = WebDriverWait(driver, 20)
    articles_data = []

    try:
        #Open El País
        driver.get("https://elpais.com")
        print(f"\nOpened  : {driver.current_url}")
        print(f"Title   : {driver.title}")

        #Verify Spanish
        html_lang = driver.find_element(By.TAG_NAME, "html").get_attribute("lang") or ""
        print(f"Language: '{html_lang}'")
        if "es" in html_lang.lower():
            print("Confirmed: Page is in Spanish\n")
        else:
            print("Language not confirmed as Spanish\n")

        #Accept cookie consent
        try:
            accept_btn = WebDriverWait(driver, 7).until(
                EC.element_to_be_clickable((By.XPATH,
                    "//button[contains("
                    "translate(normalize-space(.), "
                    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
                    "'aceptar')]"
                ))
            )
            accept_btn.click()
            print("Cookie consent accepted")
            time.sleep(1.5)
        except TimeoutException:
            print("No cookie banner detected")

        #Navigate to Opinion section
        navigated = False
        try:
            opinion_link = wait.until(
                EC.element_to_be_clickable((By.XPATH,
                    "/html/body/div[4]/header/div[2]/div[1]/nav/div/a[2]"
                ))
            )
            opinion_link.click()
            navigated = True
        except TimeoutException:
            pass

        if not navigated:
            print("Nav link not clickable — navigating directly to /opinion/")
            driver.get("https://elpais.com/opinion/")

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "article")))
        print(f"Opinion section: {driver.current_url}\n")

        #Collect first 5 article cards
        cards = driver.find_elements(By.TAG_NAME, "article")[:5]
        print(f"Found {len(cards)} articles. Extracting..\n")

        #Scrape each article
        for idx, card in enumerate(cards, start=1):
            print("=" * 60)
            print(f"  Article {idx} of {len(cards)}")

            info = {
                "title":         "N/A",
                "title_english": "N/A",
                "content":       "N/A",
                "image_url":     None,
                "article_url":   None,
            }

            #Title (Spanish)
            for sel in ["h2", "h3", "h2 a", "h3 a"]:
                try:
                    t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                    if t:
                        info["title"] = t
                        break
                except NoSuchElementException:
                    continue

            # Article URL 
            try:
                info["article_url"] = card.find_element(
                    By.CSS_SELECTOR, "a[href]"
                ).get_attribute("href")
            except NoSuchElementException:
                pass

            # Content snippet from card 
            try:
                info["content"] = card.find_element(By.CSS_SELECTOR, "p").text.strip()
            except NoSuchElementException:
                pass

            # Fallback- open article tab → grab body paragraphs 
            if (not info["content"] or info["content"] == "N/A") and info["article_url"]:
                try:
                    driver.execute_script("window.open(arguments[0]);", info["article_url"])
                    driver.switch_to.window(driver.window_handles[-1])
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "article p, .a_c p")
                        )
                    )
                    paras = driver.find_elements(By.CSS_SELECTOR, "article p, .a_c p")
                    info["content"] = " ".join(
                        p.text.strip() for p in paras[:4] if p.text.strip()
                    )[:1000]
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                except Exception as e:
                    print(f"Could not fetch article body: {e}")
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])

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

            #Print Spanish article info
            print(f"\nTitle   (🇪🇸) : {info['title']}")
            print(f"Content (🇪🇸) : {info['content'][:400]}{'...' if len(info['content']) > 400 else ''}")
            print(f"URL          : {info['article_url']}")

            # Download image
            if info["image_url"]:
                print(f"Image        : {info['image_url']}")
                download_image(info["image_url"], filename=f"article_{idx}_cover")
            else:
                print("No cover image found.")

            print()
            articles_data.append(info)

    finally:
        driver.quit()
        print("Browser closed.\n")

    # Translate aLL titles 
    print("\nTranslating titles via Rapid Translate Multi Traduction API...")
    spanish_titles = [a["title"] for a in articles_data]
    english_titles = translate_titles(spanish_titles)

    for i, article in enumerate(articles_data):
        article["title_english"] = english_titles[i] if i < len(english_titles) else "[Error]"

    return articles_data

#print output
def print_summary(articles: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("Translated Headers-")
    print("=" * 60)
    for i, a in enumerate(articles, start=1):
        print(f"\n  [{i}]  🇪🇸  {a['title']}")
        print(f"        🇬🇧  {a['title_english']}")
    print()

#Word frequency analyzer
def analyze_word_frequency(articles: list[dict]) -> None:
    
    print("=" * 60)
    print(" Word Frequency Analysis of Translated Headers")
    print("=" * 60)

    #Tokenize
    all_words = []
    for article in articles:
        title = article.get("title_english", "")

        #Skip articles where translation failed or was skipped
        if not title or title.startswith("["):
            continue

        tokens = word_tokenize(title.lower())

        meaningful = [
            w for w in tokens
            if re.fullmatch(r"[^\W\d_]+", w)      #pure alphabetic
            # and w not in STOP_WORDS      #uncomment this line if stop words are not to be included
            and len(w) > 2
        ]
        all_words.extend(meaningful)

    if not all_words:
        print("\nNo translated titles to analyze.")
        print("Make sure rapidapi_key is set and translation succeeded.\n")
        return

    #count word frequencies 
    word_counts = Counter(all_words)

    repeated = {
        word: count
        for word, count in word_counts.items()
        if count > 2
    }
    
    print(f"\n  Titles analyzed : {len(articles)}")
    print(f"  Total words     : {len(all_words)}")
    print(f"  Unique words    : {len(word_counts)}")
    print("\n" + "-" * 60)

    #print results
    if repeated:
        print("Words repeated MORE than twice (count > 2):\n")
        # Sort by frequency desc, then alphabetically for ties
        for word, count in sorted(repeated.items(), key=lambda x: (-x[1], x[0])):
            print(f"    {word:<20} {count:>3} occurrences")
    else:
        print("No word appears more than twice across all 5 titles.")
        print("\n  Top 5 most frequent words (for reference):\n")
        for word, count in word_counts.most_common(5):
            print(f"    {word:<20} {count:>3} occurrences")

    print()


if __name__ == "__main__":
    results = scrape_opinion()
    print_summary(results)
    analyze_word_frequency(results)
    print("Execution Completed!")
    
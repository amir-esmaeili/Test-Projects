import time
import random
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

EXCEL_FILE = "followers.csv"
COLUMN_NAME = "string_list_data/0/value"
OUTPUT_FILE = "output.xlsx"

chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

df = pd.read_csv(EXCEL_FILE)
results = []

for idx, value in enumerate(df[COLUMN_NAME].dropna(), start=1):
    query = f"site:instagram.com {value}"
    url = f"https://www.google.com/search?q={query}"
    driver.get(url)

    # Wait for results to load
    time.sleep(random.uniform(4, 7))

    snippet = "No result found or blocked"
    try:
        possible_selectors = [
            "div.VwiC3b",            
            "div[data-sncf='1']",   
            "span[data-sncf='1']",
            "div.yuRUbf + div"       
        ]

        for sel in possible_selectors:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems:
                snippet = elems[0].text.strip()
                break

    except Exception as e:
        snippet = f"Error: {e}"

    print(f"[{idx}] {value} -> {snippet[:80]}...")
    results.append({"name": value, "meta_description": snippet})
    time.sleep(random.uniform(3, 6))
driver.quit()

pd.DataFrame(results).to_excel(OUTPUT_FILE, index=False)
print(f"\n✅ Done! Results saved to {OUTPUT_FILE}")

import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- 設定 ---
ES_SEARCH_URL = "https://rent.es-square.net/bukken/chintai/search?jusho=13%2B101&jusho=13%2B102&jusho=13%2B103&jusho=13%2B104&jusho=13%2B105&jusho=13%2B106&jusho=13%2B107&jusho=13%2B108&jusho=13%2B109&jusho=13%2B110&jusho=13%2B111&jusho=13%2B112&jusho=13%2B113&jusho=13%2B114&jusho=13%2B115&jusho=13%2B116&jusho=13%2B120&jusho=13%2B203&jusho=13%2B204&jusho=13%2B229&jusho=13%2B211&jusho=13%2B210&search_madori_code2=2&search_madori_code2=1&kokai_radio_state=today&kodawari=separatedBathAndToilet&is_exclude_moshikomi_exist=true&order=saishu_koshin_time.desc&p=1&items_per_page=30"

def create_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080') # 画面を大きくして確実に要素を捉える
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    return webdriver.Chrome(options=options)

def send_discord(message):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if url:
        requests.post(url, json={"content": message})

def login_es(driver):
    try:
        print("🌐 いい生活スクエアへアクセス中...")
        driver.get(ES_SEARCH_URL)
        time.sleep(5)
        
        # ログイン画面へのリダイレクトを待つ
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        
        print("🔑 ログイン情報を入力中...")
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        # ログイン後の物件リスト（MuiPaper）が出るまで最大30秒待つ
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.MuiPaper-root")))
        print("✅ ログイン成功！")
        return True
    except Exception as e:
        print(f"❌ ログイン失敗: {e}")
        driver.save_screenshot("login_failed.png") # 失敗した瞬間の証拠写真
        with open("page_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source) # HTMLも保存
        return False

def check_suumo_competitors(driver, name, floor):
    # (中略 - 前回と同じロジック)
    search_query = f"{name} {floor}"
    suumo_url = f"https://suumo.jp/jj/chintai/ichiran/FR301FC001/?ar=030&bs=040&ta=13&fw={search_query}"
    driver.get(suumo_url)
    time.sleep(3)
    try:
        elements = driver.find_elements(By.XPATH, "//*[contains(text(), '取り扱い店舗数')]")
        if not elements: return 0
        text = elements[0].text
        count = int(''.join(filter(str.isdigit, text)))
        return count
    except:
        return 99

def main():
    driver = create_driver()
    send_discord("🔍 いい生活スクエアの調査を開始します...")
    
    if not login_es(driver):
        send_discord("❌ ログインに失敗しました。GitHubのArtifactsからスクリーンショットを確認してください。")
        driver.quit()
        return

    # 物件取得
    items = driver.find_elements(By.CSS_SELECTOR, "div.MuiPaper-root")
    print(f"📦 取得物件数: {len(items)}")
    
    found_count = 0
    # ここからは前回と同じ...
    for item in items[:20]:
        try:
            name = item.find_element(By.CSS_SELECTOR, "p.MuiTypography-subtitle1").text
            try:
                floor = item.find_element(By.XPATH, ".//div[contains(text(), '階')]").text
            except:
                floor = ""
            
            competitors = check_suumo_competitors(driver, name, floor)
            if competitors <= 1:
                send_discord(f"✨ 【お宝】競合{competitors}件: {name} {floor}")
                found_count += 1
        except:
            continue

    send_discord(f"✅ 調査完了。新規お宝: {found_count}件")
    driver.quit()

if __name__ == "__main__":
    main()

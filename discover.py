import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ES_SEARCH_URL = "https://rent.es-square.net/bukken/chintai/search?jusho=13%2B101&jusho=13%2B102&jusho=13%2B103&jusho=13%2B104&jusho=13%2B105&jusho=13%2B106&jusho=13%2B107&jusho=13%2B108&jusho=13%2B109&jusho=13%2B110&jusho=13%2B111&jusho=13%2B112&jusho=13%2B113&jusho=13%2B114&jusho=13%2B115&jusho=13%2B116&jusho=13%2B120&jusho=13%2B203&jusho=13%2B204&jusho=13%2B229&jusho=13%2B211&jusho=13%2B210&search_madori_code2=2&search_madori_code2=1&kokai_radio_state=today&kodawari=separatedBathAndToilet&is_exclude_moshikomi_exist=true&order=saishu_koshin_time.desc&p=1&items_per_page=30"

def create_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=2560,1440')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    return webdriver.Chrome(options=options)

def send_discord(message):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if url:
        requests.post(url, json={"content": message})

def login_es(driver):
    try:
        driver.get(ES_SEARCH_URL)
        # ユーザー名入力待ち
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        # ログイン後、少し長めに待機してから状況を保存
        print("⏳ ログイン後のページ読み込みを待機中...")
        time.sleep(15)
        
        # 【重要】物件一覧を探す前に、今の画面を「evidence.png」として保存
        driver.save_screenshot("evidence.png")
        
        # 判定
        items = driver.find_elements(By.CSS_SELECTOR, "div.MuiPaper-root")
        if len(items) > 0:
            print(f"✅ 物件を {len(items)} 件検知しました。")
            return True
        else:
            print("❓ 物件リスト（MuiPaper）が見つかりません。")
            return False
            
    except Exception as e:
        print(f"❌ ログインプロセスエラー: {e}")
        driver.save_screenshot("evidence.png")
        return False

def main():
    driver = create_driver()
    send_discord("🔍 検証モード：いい生活スクエアの画面を確認します...")
    
    success = login_es(driver)
    
    if not success:
        send_discord("⚠️ 物件一覧を認識できませんでした。GitHubのArtifactsから「evidence.png」を確認してください。")
    else:
        send_discord("✅ 物件一覧を正常に認識しました。")

    driver.quit()

if __name__ == "__main__":
    main()

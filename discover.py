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
    options.add_argument('--window-size=1280,1024')
    return webdriver.Chrome(options=options)

def send_discord(message):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if url:
        requests.post(url, json={"content": message})

def login_es(driver):
    """既存のmain.pyから移植したログイン処理"""
    try:
        driver.get(ES_SEARCH_URL) # 検索URLを叩くとログインへ飛ばされる前提
        # ユーザー名入力待ち
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        # ログイン後の画面表示を待機
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.MuiPaper-root")))
        print("✅ いい生活ログイン成功")
        return True
    except Exception as e:
        print(f"❌ ログイン失敗: {e}")
        return False

def check_suumo_competitors(driver, name, floor):
    search_query = f"{name} {floor}"
    suumo_url = f"https://suumo.jp/jj/chintai/ichiran/FR301FC001/?ar=030&bs=040&ta=13&fw={search_query}"
    driver.get(suumo_url)
    time.sleep(2)
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
    send_discord("🔍 物出し調査システムを起動しました...") # 動作確認用
    
    if not login_es(driver):
        send_discord("❌ いい生活へのログインに失敗しました。パスワード等を確認してください。")
        driver.quit()
        return

    # 1. いい生活スクエアの検索結果を取得
    driver.get(ES_SEARCH_URL)
    time.sleep(5) # 読み込みを長めに待機
    
    items = driver.find_elements(By.CSS_SELECTOR, "div.MuiPaper-root")
    print(f"取得した物件数: {len(items)}")
    
    if len(items) == 0:
        send_discord("⚠️ 物件が見つかりませんでした。検索URLやセレクタを確認する必要があります。")
        driver.save_screenshot("error_no_items.png") # デバッグ用

    found_count = 0
    for item in items[:20]: # 20件チェック
        try:
            name = item.find_element(By.CSS_SELECTOR, "p.MuiTypography-subtitle1").text
            try:
                floor = item.find_element(By.XPATH, ".//div[contains(text(), '階')]").text
            except:
                floor = ""
                
            competitors = check_suumo_competitors(driver, name, floor)
            
            # テスト用に、10件以内なら全て通知するか、条件を絞るか調整可能
            if competitors <= 1: 
                msg = f"✨ 【お宝候補】競合 {competitors} 件\n物件: {name} {floor}\nリンク: {ES_SEARCH_URL}"
                send_discord(msg)
                found_count += 1
                
        except:
            continue

    send_discord(f"✅ 調査完了。本日の新規お宝物件: {found_count} 件でした。")
    driver.quit()

if __name__ == "__main__":
    main()

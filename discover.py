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
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    return webdriver.Chrome(options=options)

def send_discord(message):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if url:
        requests.post(url, json={"content": message})

def login_es(driver):
    try:
        driver.get(ES_SEARCH_URL)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        # ログイン後、検索結果が出るまで粘り強く待つ（最大30秒）
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.MuiPaper-root")))
        print("✅ ログイン成功")
        return True
    except Exception as e:
        print(f"❌ ログイン失敗または物件なし: {e}")
        driver.save_screenshot("after_login_attempt.png") # 状況確認用
        return False

def check_suumo_competitors(driver, name, floor):
    # 階数から「階」の文字を消して数字だけにする（検索精度向上）
    floor_num = ''.join(filter(str.isdigit, floor))
    search_query = f"{name} {floor_num}"
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
        # ログインはできたが物件がない場合もここに来る可能性があるため、メッセージを修正
        send_discord("⚠️ 物件リストが表示されませんでした（本日分が0件の可能性があります）。")
        driver.quit()
        return

    # 物件リストを再取得
    items = driver.find_elements(By.CSS_SELECTOR, "div.MuiPaper-root")
    found_count = 0
    
    # 実際の中身をチェック
    for item in items:
        try:
            # タイトル（物件名）を取得
            name_el = item.find_element(By.CSS_SELECTOR, "p.MuiTypography-subtitle1")
            name = name_el.text
            if not name: continue
            
            # 階数を取得
            try:
                floor = item.find_element(By.XPATH, ".//div[contains(text(), '階')]").text
            except:
                floor = ""
            
            print(f"🧐 調査対象: {name} {floor}")
            competitors = check_suumo_competitors(driver, name, floor)
            
            if competitors <= 1:
                send_discord(f"✨ 【お宝】競合 {competitors}件\n物件: {name} {floor}\nリンク: {ES_SEARCH_URL}")
                found_count += 1
            
            # 検索しすぎるとSUUMOに弾かれるため少し休む
            time.sleep(1)
            
        except:
            continue

    send_discord(f"✅ 調査完了。新規お宝: {found_count}件")
    driver.quit()

if __name__ == "__main__":
    main()

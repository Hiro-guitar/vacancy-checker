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
    # 画面サイズを最大級に設定
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
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        # ログイン後、物件が表示されるのを「複数の条件」で待つ
        print("⏳ 物件リストの読み込みを待機中...")
        time.sleep(10) # 確実に描画させるための余裕
        
        # 検索結果が0件の場合のメッセージがあるか確認
        if "条件に一致する物件は見つかりませんでした" in driver.page_source:
            print("ℹ️ 本日公開の物件は0件です。")
            return "NO_PROPERTIES"
            
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.MuiPaper-root")))
        return True
    except Exception as e:
        print(f"❌ 読み込み失敗: {e}")
        driver.save_screenshot("after_login_error.png")
        return False

def check_suumo_competitors(driver, name, floor):
    # 階数から数字のみ抽出
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
    
    login_status = login_es(driver)
    
    if login_status == "NO_PROPERTIES":
        send_discord("✅ 調査完了。本日公開の条件に一致する物件は 0 件でした。")
        driver.quit()
        return
    elif not login_status:
        send_discord("⚠️ ログイン後の画面取得に失敗しました。Artifactsを確認してください。")
        driver.quit()
        return

    # 物件パネルを取得
    items = driver.find_elements(By.CSS_SELECTOR, "div.MuiPaper-root")
    found_count = 0
    
    for item in items:
        try:
            # タイトル（物件名）
            name_el = item.find_elements(By.CSS_SELECTOR, "p.MuiTypography-subtitle1")
            if not name_el: continue
            name = name_el[0].text
            
            # 階数
            try:
                floor = item.find_element(By.XPATH, ".//div[contains(text(), '階')]").text
            except:
                floor = ""
            
            print(f"🧐 SUUMO調査中: {name} {floor}")
            competitors = check_suumo_competitors(driver, name, floor)
            
            if competitors <= 1:
                send_discord(f"✨ 【お宝】競合 {competitors}件\n物件: {name} {floor}\nリンク: {ES_SEARCH_URL}")
                found_count += 1
            
            time.sleep(1)
        except:
            continue

    send_discord(f"✅ 調査完了。合計 {found_count} 件のお宝候補を通知しました。")
    driver.quit()

if __name__ == "__main__":
    main()

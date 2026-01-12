import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- 設定 ---
# 昨日いただいた「いい生活」の検索URL（本日公開分）
ES_SEARCH_URL = "https://rent.es-square.net/bukken/chintai/search?jusho=13%2B101&jusho=13%2B102&jusho=13%2B103&jusho=13%2B104&jusho=13%2B105&jusho=13%2B106&jusho=13%2B107&jusho=13%2B108&jusho=13%2B109&jusho=13%2B110&jusho=13%2B111&jusho=13%2B112&jusho=13%2B113&jusho=13%2B114&jusho=13%2B115&jusho=13%2B116&jusho=13%2B120&jusho=13%2B203&jusho=13%2B204&jusho=13%2B229&jusho=13%2B211&jusho=13%2B210&search_madori_code2=2&search_madori_code2=1&kokai_radio_state=today&kodawari=separatedBathAndToilet&is_exclude_moshikomi_exist=true&order=saishu_koshin_time.desc&p=1&items_per_page=30"

def create_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    return webdriver.Chrome(options=options)

def send_discord(message):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if url:
        requests.post(url, json={"content": message})

def check_suumo_competitors(driver, name, floor):
    """SUUMOで物件名と階数を検索し、店舗数を返す"""
    search_query = f"{name} {floor}"
    # SUUMOのキーワード検索URL（関東版）
    suumo_url = f"https://suumo.jp/jj/chintai/ichiran/FR301FC001/?ar=030&bs=040&ta=13&fw={search_query}"
    
    driver.get(suumo_url)
    time.sleep(2) # 読み込み待機
    
    try:
        # 「取り扱い店舗数：○件」のテキストを探す
        elements = driver.find_elements(By.XPATH, "//*[contains(text(), '取り扱い店舗数')]")
        if not elements:
            return 0 # 見つからない＝競合0
        
        # テキストから数字だけ抜き出す（例：「取り扱い店舗数：3件」 -> 3）
        text = elements[0].text
        count = int(''.join(filter(str.isdigit, text)))
        return count
    except:
        return 99 # エラー時は安全のため多めの数字を返す

def main():
    driver = create_driver()
    print("🚀 調査開始: いい生活スクエア")
    
    # 1. いい生活スクエアの検索結果を取得
    driver.get(ES_SEARCH_URL)
    time.sleep(3)
    
    # 物件パネル要素を全取得（拡張機能の解析結果に基づいたクラス名）
    items = driver.find_elements(By.CSS_SELECTOR, "div.MuiPaper-root")
    
    found_count = 0
    for item in items[:10]: # まずは最初の10件でテスト
        try:
            name = item.find_element(By.CSS_SELECTOR, "p.MuiTypography-subtitle1").text
            # 階数情報の取得（要素がない場合もあるのでtry-except）
            try:
                floor = item.find_element(By.XPATH, ".//div[contains(text(), '階')]").text
            except:
                floor = ""
                
            print(f"🔍 調査中: {name} {floor}")
            
            # 2. SUUMO競合調査
            competitors = check_suumo_competitors(driver, name, floor)
            
            # 3. 判定（競合が0または1なら通知）
            if competitors <= 1:
                msg = f"✨ 【お宝発見】競合 {competitors} 件！\n物件名: {name} {floor}\n調査URL: {driver.current_url}"
                send_discord(msg)
                found_count += 1
                
        except Exception as e:
            continue

    print(f"✅ 調査完了。{found_count}件のお宝物件を通知しました。")
    driver.quit()

if __name__ == "__main__":
    main()

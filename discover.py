import os
import time
import requests
import re
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
    options.add_argument('--window-size=2560,1440')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    return webdriver.Chrome(options=options)

def send_discord(message):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if url:
        requests.post(url, json={"content": message})

def normalize(text):
    """拡張機能のnormalize関数を再現"""
    if not text: return ""
    # 全角数字を半角に
    text = text.translate(str.maketrans('０１２３４５６７８９．', '0123456789.'))
    # 空白削除、㎡をmに
    text = re.sub(r'\s+', '', text).replace('㎡', 'm')
    return text.strip()

def check_suumo_highlight_count(driver, name, floor, target_rent, target_area):
    """拡張機能の countHighlighted ロジックを再現"""
    floor_num = "".join(re.findall(r'\d+', floor))
    search_query = f"{name} {floor_num}".strip()
    suumo_url = f"https://suumo.jp/jj/chintai/ichiran/FR301FC001/?ar=030&bs=040&ta=13&fw={search_query}"
    
    driver.get(suumo_url)
    time.sleep(3) # MutationObserverの代わりに待機

    try:
        # ハイライト物件（広告枠）をすべて取得
        highlights = driver.find_elements(By.CSS_SELECTOR, ".property.property--highlight")
        match_count = 0
        
        normalized_target_rent = normalize(target_rent)
        normalized_target_area = normalize(target_area)

        for item in highlights:
            try:
                # 賃料
                rent_text = item.find_element(By.CSS_SELECTOR, ".detailbox-property-point").text
                # 面積 (supタグを無視するためにテキスト取得)
                area_el = item.find_element(By.CSS_SELECTOR, ".detailbox-property--col3 div:nth-child(2)")
                area_text = area_el.text # Seleniumの.textは表示テキストのみ（sup除く）を取得できる
                
                if normalize(rent_text) == normalized_target_rent and normalize(area_text) == normalized_target_area:
                    match_count += 1
            except:
                continue
        return match_count
    except:
        return 99

def main():
    driver = create_driver()
    send_discord("🔍 物出し精密調査（ハイライトカウント）を開始します...")
    
    try:
        # 1. いい生活ログイン
        driver.get(ES_SEARCH_URL)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        time.sleep(15) # フォント読み込み・描画待機

        # 2. 物件カードの取得
        items = driver.find_elements(By.CSS_SELECTOR, "div.MuiPaper-root")
        if not items:
            send_discord("✅ 本日公開の物件は 0 件でした。")
            return

        found_count = 0
        for item in items[:20]: # 効率化のため上位20件
            try:
                # 物件名取得
                name_el = item.find_elements(By.CSS_SELECTOR, "p.MuiTypography-subtitle1")
                if not name_el: continue
                name = name_el[0].text.strip()

                # 賃料・面積・階数の抽出（いい生活の構造に合わせる）
                # divやspanを跨いで情報を探す
                card_text = item.text
                rent_match = re.search(r'(\d+\.?\d*万円)', card_text)
                area_match = re.search(r'(\d+\.?\d*㎡)', card_text)
                floor_match = re.search(r'(\d+階)', card_text)

                if not rent_match or not area_match: continue
                
                rent = rent_match.group(1)
                area = area_match.group(1)
                floor = floor_match.group(1) if floor_match else ""

                # 3. SUUMOハイライトカウント実行
                print(f"🧐 照合中: {name} ({rent}/{area})")
                count = check_suumo_highlight_count(driver, name, floor, rent, area)
                
                # お宝条件：ハイライト物件が1件以下（自社掲載のみ、または未掲載）
                if count <= 1:
                    send_discord(f"✨ 【お宝確定】競合 {count}社\n物件: {name} {floor}\n賃料: {rent} / 面積: {area}\nリンク: {ES_SEARCH_URL}")
                    found_count += 1
                
                time.sleep(2) # SUUMOブロック回避
            except:
                continue

        send_discord(f"✅ 調査完了。本日のお宝候補: {found_count} 件")

    except Exception as e:
        send_discord(f"⚠️ システムエラー: {str(e)}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()

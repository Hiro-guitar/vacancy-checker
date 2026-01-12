import os
import time
import requests
import re
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

def normalize(text):
    if not text: return ""
    text = text.translate(str.maketrans('０１２３４５６７８９．', '0123456789.'))
    text = re.sub(r'\s+', '', text).replace('㎡', 'm')
    return text.strip()

def check_suumo_highlight_count(driver, name, floor, target_rent, target_area):
    floor_num = "".join(re.findall(r'\d+', floor))
    search_query = f"{name} {floor_num}".strip()
    suumo_url = f"https://suumo.jp/jj/chintai/ichiran/FR301FC001/?ar=030&bs=040&ta=13&fw={search_query}"
    
    driver.get(suumo_url)
    time.sleep(5) # 読み込み待ちを長めに設定

    try:
        highlights = driver.find_elements(By.CSS_SELECTOR, ".property.property--highlight")
        match_count = 0
        norm_rent = normalize(target_rent)
        norm_area = normalize(target_area)

        for item in highlights:
            try:
                rent_text = item.find_element(By.CSS_SELECTOR, ".detailbox-property-point").text
                area_text = item.find_element(By.CSS_SELECTOR, ".detailbox-property--col3 div:nth-child(2)").text
                
                if normalize(rent_text) == norm_rent and normalize(area_text) == norm_area:
                    match_count += 1
            except:
                continue
        return match_count
    except:
        return 99

def main():
    driver = create_driver()
    send_discord("🔍 詳細デバッグモードで調査を開始します...")
    
    try:
        driver.get(ES_SEARCH_URL)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        time.sleep(15)
        # 確実に撮影
        driver.save_screenshot("evidence.png")

        items = driver.find_elements(By.CSS_SELECTOR, "div.MuiPaper-root")
        if not items:
            send_discord("⚠️ 物件カードが見つかりません。")
            return

        found_count = 0
        for i, item in enumerate(items[:10]): # デバッグのためまずは10件
            try:
                card_text = item.text.replace("\n", " ")
                name_el = item.find_elements(By.CSS_SELECTOR, "p.MuiTypography-subtitle1")
                if not name_el: continue
                name = name_el[0].text.strip()

                # 正規表現を微調整
                rent_match = re.search(r'(\d+\.?\d*)万円', card_text)
                area_match = re.search(r'(\d+\.?\d*)㎡', card_text)
                floor_match = re.search(r'(\d+)階', card_text)

                if not rent_match or not area_match:
                    print(f"⏩ データ抽出失敗: {name}")
                    continue
                
                rent = rent_match.group(0) # "5.5万円"
                area = area_match.group(0) # "20.5㎡"
                floor = floor_match.group(0) if floor_match else ""

                print(f"🧐 照合中[{i+1}]: {name} {floor} ({rent}/{area})")
                count = check_suumo_highlight_count(driver, name, floor, rent, area)
                
                if count <= 1:
                    send_discord(f"✨ 【候補】{name} {floor}\n賃料:{rent} 面積:{area}\nSUUMO一致数: {count}件")
                    found_count += 1
                
                time.sleep(2)
            except Exception as e:
                print(f"エラー: {e}")
                continue

        send_discord(f"✅ 調査終了。発見数: {found_count}")

    except Exception as e:
        send_discord(f"🚨 システムエラー: {e}")
    finally:
        driver.save_screenshot("evidence.png")
        driver.quit()

if __name__ == "__main__":
    main()

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
    if not text: return ""
    text = text.translate(str.maketrans('０１２３４５６７８９．', '0123456789.'))
    text = re.sub(r'\s+', '', text).replace('㎡', 'm')
    return text.strip()

def check_suumo_highlight_count(driver, name, floor, target_rent, target_area):
    """SUUMOで指定の賃料・面積の掲載社数をカウント"""
    # 階数から数値のみ抽出
    floor_num = "".join(re.findall(r'\d+', floor))
    search_query = f"{name} {floor_num}".strip()
    suumo_url = f"https://suumo.jp/jj/chintai/ichiran/FR301FC001/?ar=030&bs=040&ta=13&fw={search_query}"
    
    driver.execute_script("window.open('');") # 新しいタブを開く
    driver.switch_to.window(driver.window_handles[-1])
    driver.get(suumo_url)
    time.sleep(4)

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
            except: continue
        
        driver.close() # タブを閉じる
        driver.switch_to.window(driver.window_handles[0]) # 元に戻す
        return match_count
    except:
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return 99

def main():
    driver = create_driver()
    send_discord("🔍 精密モーダル解析モードを起動しました...")
    
    try:
        # 1. ログイン
        driver.get(ES_SEARCH_URL)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        time.sleep(12) # 読み込み待機

        # 2. 物件リスト取得 (拡張機能の bukkenListItem に準拠)
        items = driver.find_elements(By.CSS_SELECTOR, 'div[data-testclass="bukkenListItem"]')
        if not items:
            send_discord("⚠️ 物件リストが見つかりません。")
            return

        found_count = 0
        for i, item in enumerate(items[:10]): # まずは上位10件
            try:
                # 一覧から物件名と賃料を取得（拡張機能の抽出ロジック参考）
                name = item.querySelector("h2").text.strip() if hasattr(item, "querySelector") else item.find_element(By.TAG_NAME, "h2").text.strip()
                
                # 物件をクリックしてモーダルを開く
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                time.sleep(1)
                item.click()
                time.sleep(3) # モーダル表示待ち

                # 3. モーダル内から面積と階数を抽出
                modal = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.MuiBox-root.css-ne16qb')))
                modal_text = modal.text
                
                # 面積 (〇〇.〇〇㎡)
                area_match = re.search(r'(\d+\.?\d*)㎡', modal_text)
                area = area_match.group(0) if area_match else ""
                
                # 階数 (〇階)
                floor_match = re.search(r'(\d+)階', modal_text)
                floor = floor_match.group(0) if floor_match else ""

                # 賃料は一覧の兄弟要素から取得（拡張機能の css-smu62q を参考）
                # ここでは簡易的にカード内テキストから抽出
                rent_match = re.search(r'(\d+,?\d+)円', item.text)
                if rent_match:
                    raw_rent = rent_match.group(1).replace(',', '')
                    rent = f"{int(raw_rent)//10000}万" # "123000" -> "12.3万" (拡張機能形式)
                else:
                    rent = ""

                print(f"🧐 解析中: {name} ({rent}/{area})")
                
                # 4. SUUMO照合
                count = check_suumo_highlight_count(driver, name, floor, rent, area)
                
                if count <= 1:
                    send_discord(f"✨ 【お宝確定】競合 {count}社\n物件: {name} {floor}\n賃料: {rent} / 面積: {area}\nリンク: {ES_SEARCH_URL}")
                    found_count += 1

                # モーダルを閉じる
                close_btn = driver.find_element(By.CSS_SELECTOR, 'svg[data-testid="CloseIcon"]')
                close_btn.click()
                time.sleep(1)

            except Exception as e:
                print(f"物件スキップ: {e}")
                continue

        send_discord(f"✅ 調査完了。発見数: {found_count}")

    except Exception as e:
        send_discord(f"🚨 システムエラー: {e}")
    finally:
        driver.save_screenshot("evidence.png")
        driver.quit()

if __name__ == "__main__":
    main()

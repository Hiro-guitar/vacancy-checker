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
    # 階数から数値のみ抽出（102号室なら2階と判定されないよう、建物全体の階建て情報を優先したいが、まずは名前＋階で検索）
    floor_num = "".join(re.findall(r'\d+', floor))
    search_query = f"{name} {floor_num}".strip()
    suumo_url = f"https://suumo.jp/jj/chintai/ichiran/FR301FC001/?ar=030&bs=040&ta=13&fw={search_query}"
    
    driver.execute_script("window.open('');")
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
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return match_count
    except:
        if len(driver.window_handles) > 1: driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return 99

def main():
    driver = create_driver()
    send_discord("🔍 物件名のタグ情報を特定しました。精密調査を再開します...")
    
    try:
        driver.get(ES_SEARCH_URL)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        time.sleep(15)

        # 教えていただいたタグで物件名を一括取得
        name_elements = driver.find_elements(By.CSS_SELECTOR, 'p.MuiTypography-root.MuiTypography-body1.css-1bkh2wx')
        
        if not name_elements:
            send_discord("⚠️ 指定の物件名タグが見つかりません。レイアウトが変更された可能性があります。")
            return

        found_count = 0
        checked_count = 0
        
        for name_el in name_elements[:15]:
            try:
                name = name_el.text.strip()
                if not name: continue

                # 物件をクリックして詳細を開く（名前の要素自体をクリック）
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", name_el)
                time.sleep(1)
                name_el.click()
                time.sleep(4) # モーダル表示待ち

                # モーダルから詳細情報を取得
                modal_text = driver.find_element(By.CSS_SELECTOR, 'div.MuiBox-root.css-ne16qb').text
                
                # 面積・階数・賃料の抽出（拡張機能のロジックに準拠）
                area_match = re.search(r'(\d+\.?\d*)㎡', modal_text)
                area = area_match.group(0) if area_match else ""
                
                floor_match = re.search(r'(\d+)階', modal_text)
                floor = floor_match.group(0) if floor_match else ""

                # 賃料：一覧の親要素を遡って、そこに含まれる金額テキストから取得
                parent_card = name_el.find_element(By.XPATH, "./ancestor::div[contains(@data-testclass, 'bukkenListItem')]")
                rent_candidates = re.findall(r'(\d{1,3}(?:,\d{3})+)', parent_card.text)
                rent = ""
                if rent_candidates:
                    raw_rent = rent_candidates[0].replace(',', '')
                    rent = f"{int(raw_rent)//10000}万"

                print(f"🧐 照合中: {name} ({rent}/{area})")
                
                if rent and area:
                    count = check_suumo_highlight_count(driver, name, floor, rent, area)
                    if count <= 1:
                        send_discord(f"✨ 【お宝候補】競合 {count}社\n物件: {name} {floor}\n条件: {rent} / {area}\nリンク: {ES_SEARCH_URL}")
                        found_count += 1
                
                checked_count += 1

                # モーダルを閉じる
                driver.find_element(By.CSS_SELECTOR, 'svg[data-testid="CloseIcon"]').click()
                time.sleep(1)

            except Exception as e:
                print(f"物件スキップ: {e}")
                continue

        send_discord(f"✅ 調査完了。{checked_count}件中、{found_count}件のお宝が見つかりました。")

    except Exception as e:
        send_discord(f"🚨 エラー: {e}")
    finally:
        driver.save_screenshot("evidence.png")
        driver.quit()

if __name__ == "__main__":
    main()

import os
import time
import re
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

def create_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=2560,1440')
    return webdriver.Chrome(options=options)

def send_discord(message):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if url:
        try:
            requests.post(url, json={"content": message}, timeout=10)
        except Exception as e:
            print(f"Discord送信失敗: {e}")

def clean_num_strict(text):
    if not text: return 0.0
    text = text.replace(',', '').translate(str.maketrans('０１２３４５６７８９．', '0123456789.'))
    nums = re.findall(r'\d+\.?\d*', text)
    if not nums: return 0.0
    return float(nums[0])

def check_suumo(driver, info):
    search_query = f"{info['name']} {info['floor']}".strip()
    suumo_url = f"https://suumo.jp/jj/chintai/ichiran/FR301FC001/?ar=030&bs=040&ta=13&fw={search_query}"
    
    main_window = driver.current_window_handle
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[-1])
    driver.get(suumo_url)
    time.sleep(4)

    match_count = 0
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, ".property.property--highlight")
        for card in cards:
            try:
                s_rent = clean_num_strict(card.find_element(By.CSS_SELECTOR, ".detailbox-property-point").text)
                s_area = clean_num_strict(card.find_element(By.CSS_SELECTOR, ".detailbox-property--col3 div:nth-child(2)").text)
                
                # 万単位で完全一致比較
                es_rent_man = info['rent_raw'] / 10000.0
                if s_rent == es_rent_man and s_area == info['area']:
                    match_count += 1
            except: continue
    except: pass
    
    driver.close()
    driver.switch_to.window(main_window)
    return match_count

def main():
    driver = create_driver()
    send_discord("🔍 調査を開始します")
    
    last_modal_address = ""
    
    try:
        driver.get("https://rent.es-square.net/bukken/chintai/search?jusho=13%2B101&jusho=13%2B102&jusho=13%2B103&jusho=13%2B104&jusho=13%2B105&jusho=13%2B106&jusho=13%2B107&jusho=13%2B108&jusho=13%2B109&jusho=13%2B110&jusho=13%2B111&jusho=13%2B112&jusho=13%2B113&jusho=13%2B114&jusho=13%2B115&jusho=13%2B116&jusho=13%2B120&jusho=13%2B203&jusho=13%2B204&jusho=13%2B229&jusho=13%2B211&jusho=13%2B210&search_madori_code2=2&search_madori_code2=1&kokai_radio_state=today&kodawari=separatedBathAndToilet&is_exclude_moshikomi_exist=true&order=saishu_koshin_time.desc&p=1&items_per_page=30")
        
        # ログイン
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        time.sleep(15) 
        
        # 物件リストの取得
        items_xpath = '//div[@data-testclass="bukkenListItem"]'
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, items_xpath)))
        items = driver.find_elements(By.XPATH, items_xpath)
        print(f"発見物件数: {len(items)}")
        
        found_count = 0
        for i in range(len(items)):
            try:
                # 物件要素のリロード
                current_items = driver.find_elements(By.XPATH, items_xpath)
                item = current_items[i]
                
                # 物件名を取得
                name = item.find_element(By.CSS_SELECTOR, 'p.css-1bkh2wx').text.strip()
                rent_raw = 0.0
                
                # --- 【重要】Chrome拡張の「モーダル外から賃料取得」を完全再現 ---
                # 1. ページ内の全ての「.css-1t7sidb」を取得
                list_boxes = driver.find_elements(By.CSS_SELECTOR, '.MuiBox-root.css-1t7sidb')
                for box in list_boxes:
                    try:
                        # 2. ボックス内の名前が、現在処理中の物件名と一致するか確認
                        name_el = box.find_element(By.CSS_SELECTOR, 'p.MuiTypography-root.MuiTypography-body1.css-1bkh2wx')
                        if name_el.text.strip() == name:
                            # 3. nextElementSibling (隣の兄弟要素) を取得
                            rent_box = box.find_element(By.XPATH, './following-sibling::div[contains(@class, "css-57ym5z")]')
                            # 4. その中の span.css-smu62q をすべて取得し、カンマを含むものを探す
                            rent_spans = rent_box.find_elements(By.CSS_SELECTOR, 'span.css-smu62q')
                            for s in rent_spans:
                                # JSの textContent を使って不可視文字も取得
                                val = s.get_attribute("textContent")
                                if "," in val:
                                    rent_raw = clean_num_strict(val)
                                    break
                            if rent_raw > 0: break # 見つかったらループを抜ける
                    except: continue

                # クリックしてモーダルを開く
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", item)
                
                # モーダル待機
                modal = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.MuiBox-root.css-ne16qb')))
                
                # 内容の書き換えを待機
                area_val = 0.0
                floor = ""
                for _ in range(50):
                    try:
                        address_el = modal.find_element(By.CSS_SELECTOR, "div.MuiBox-root.css-1x36n8t")
                        if address_el.text.strip() != last_modal_address:
                            last_modal_address = address_el.text.strip()
                            area_match = re.search(r'(\d+(\.\d+)?㎡)', modal.text)
                            area_val = clean_num_strict(area_match.group(1)) if area_match else 0.0
                            floor_match = re.search(r'地上(\d+)階', modal.text)
                            floor = floor_match.group(0) if floor_match else ""
                            break
                    except: pass
                    time.sleep(0.2)

                info = {"name": name, "rent_raw": rent_raw, "area": area_val, "floor": floor}
                print(f"🧐 [{i+1}] 照合中: {name} ({rent_raw}円 / {area_val}㎡)")

                # 完全一致照合
                count = check_suumo(driver, info)
                if count <= 1:
                    rent_man = rent_raw / 10000.0
                    send_discord(f"✨ 【お宝候補】他社掲載 {count}件\n物件: {name} {floor}\n条件: {rent_man}万 / {area_val}㎡")
                    found_count += 1

                # 閉じる
                driver.execute_script("""
                    var closeBtn = document.querySelector('.MuiBox-root.css-1xhj18k svg[data-testid="CloseIcon"]');
                    if (closeBtn) closeBtn.closest('button').click();
                """)
                time.sleep(1.2)

            except Exception as e:
                print(f"物件[{i}] スキップ: {e}")
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(1)

        send_discord(f"✅ 調査完了。{found_count}件見つかりました。")

    except Exception as e:
        print(f"エラー: {e}")
        send_discord(f"🚨 システム停止: {e}") # エラー時もDiscordに通知
    finally:
        # 終了前に必ずスクショを保存
        print("エビデンスを保存します...")
        driver.save_screenshot("evidence.png")
        driver.quit()

if __name__ == "__main__":
    main()

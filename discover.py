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

def clean_num(text):
    if not text: return 0.0
    text = text.replace(',', '').translate(str.maketrans('０１２３４５６７８９．', '0123456789.'))
    nums = re.findall(r'\d+\.?\d*', text)
    if not nums: return 0.0
    val = float(nums[0])
    return val / 10000.0 if val >= 1000 else val

def check_suumo(driver, info):
    search_query = f"{info['name']} {info['floor']}".strip()
    suumo_url = f"https://suumo.jp/jj/chintai/ichiran/FR301FC001/?ar=030&bs=040&ta=13&fw={search_query}"
    main_window = driver.current_window_handle
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[-1])
    driver.get(suumo_url)
    time.sleep(5)
    match_count = 0
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, ".property.property--highlight")
        for card in cards:
            try:
                s_rent = clean_num(card.find_element(By.CSS_SELECTOR, ".detailbox-property-point").text)
                s_area = clean_num(card.find_element(By.CSS_SELECTOR, ".detailbox-property--col3 div:nth-child(2)").text)
                if abs(s_rent - info['rent']) < 0.01 and abs(s_area - info['area']) < 0.01:
                    match_count += 1
            except: continue
    except: pass
    driver.close()
    driver.switch_to.window(main_window)
    return match_count

def main():
    driver = create_driver()
    send_discord("🔍 調査を開始します...")
    
    last_modal_address = ""
    last_modal_area = ""
    
    try:
        driver.get("https://rent.es-square.net/bukken/chintai/search?jusho=13%2B101&jusho=13%2B102&jusho=13%2B103&jusho=13%2B104&jusho=13%2B105&jusho=13%2B106&jusho=13%2B107&jusho=13%2B108&jusho=13%2B109&jusho=13%2B110&jusho=13%2B111&jusho=13%2B112&jusho=13%2B113&jusho=13%2B114&jusho=13%2B115&jusho=13%2B116&jusho=13%2B120&jusho=13%2B203&jusho=13%2B204&jusho=13%2B229&jusho=13%2B211&jusho=13%2B210&search_madori_code2=2&search_madori_code2=1&kokai_radio_state=today&kodawari=separatedBathAndToilet&is_exclude_moshikomi_exist=true&order=saishu_koshin_time.desc&p=1&items_per_page=30")
        
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        time.sleep(15) 
        
        items_xpath = '//div[@data-testclass="bukkenListItem"]'
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, items_xpath)))
        items = driver.find_elements(By.XPATH, items_xpath)
        print(f"発見物件数: {len(items)}")
        
        found_count = 0
        for i in range(min(len(items), 15)):
            try:
                current_items = driver.find_elements(By.XPATH, items_xpath)
                item = current_items[i]
                
                # 物件名取得
                name = item.find_element(By.CSS_SELECTOR, 'p.css-1bkh2wx').text.strip()
                
                # 1. 【賃料取得】モーダル外から取得
                # クラス名 smu62q を持ち、かつ不透明度が0でない（表示されている）spanからカンマ付きの数字を抜く
                rent_val = 0.0
                try:
                    # 拡張機能のロジックを忠実に再現
                    # 兄弟要素 css-57ym5z の中の css-smu62q を探す。
                    # opacity: 0 の要素が混じっているため、テキストが空でないものを特定
                    rent_spans = item.find_elements(By.XPATH, 'following-sibling::div[contains(@class, "css-57ym5z")]//span[contains(@class, "css-smu62q")]')
                    for s in rent_spans:
                        t = s.text.strip()
                        if "," in t:
                            rent_val = clean_num(t)
                            break
                except:
                    print(f"  ⚠️ {name} の賃料抽出に失敗")

                # 2. クリック
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", item)
                
                # 3. モーダル書き換え待機
                modal = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.MuiBox-root.css-ne16qb')))
                
                address_text = ""
                area_text = ""
                for _ in range(50):
                    try:
                        address_el = modal.find_element(By.CSS_SELECTOR, "div.MuiBox-root.css-1x36n8t")
                        address_text = address_el.text.strip()
                        area_match = re.search(r'(\d+(\.\d+)?㎡)', modal.text)
                        area_text = area_match.group(0) if area_match else ""
                        if address_text and area_text and (address_text != last_modal_address or area_text != last_modal_area):
                            last_modal_address = address_text
                            last_modal_area = area_text
                            break
                    except: pass
                    time.sleep(0.2)

                # 4. 情報抽出
                area_val = clean_num(area_text)
                floor = re.search(r'地上(\d+)階', modal.text).group(0) if re.search(r'地上(\d+)階', modal.text) else ""

                info = {"name": name, "rent": rent_val, "area": area_val, "floor": floor}
                print(f"🧐 [{i+1}] 照合中: {name} ({rent_val}万/{area_val}㎡)")

                count = check_suumo(driver, info)
                if count <= 1:
                    send_discord(f"✨ 【お宝候補】競合 {count}社\n物件: {name} {floor}\n条件: {rent_val}万 / {area_val}㎡")
                    found_count += 1

                # 5. 閉じる
                driver.execute_script("""
                    var modalClose = document.querySelector('.MuiBox-root.css-1xhj18k svg[data-testid="CloseIcon"]');
                    if (modalClose) modalClose.closest('button').click();
                """)
                time.sleep(1.2)

            except Exception as e:
                print(f"物件[{i}] スキップ: {e}")
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(1)
                continue

        send_discord(f"✅ 調査完了。{found_count}件見つかりました。")

    except Exception as e:
        print(f"致命的なエラー: {e}")
    finally:
        driver.save_screenshot("evidence.png")
        driver.quit()

if __name__ == "__main__":
    main()

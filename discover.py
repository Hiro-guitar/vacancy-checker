import os
import time
import re
import requests
import urllib.parse
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

def normalize_text(text):
    """拡張機能のnormalize関数を再現"""
    if not text: return ""
    text = text.translate(str.maketrans('０１２３４５６７８９．', '0123456789.'))
    text = re.sub(r'\s+', '', text)
    text = text.replace('㎡', 'm').replace(',', '')
    return text.strip()

def check_suumo(driver, info, index):
    """最強のURL形式でSUUMOを検索し、判定とスクショ保存を行う"""
    search_word = f"{info['address']} {info['built']} {info['floors']} {info['area']} {info['rent']}"
    search_word = search_word.replace('㎡', 'm')
    
    encoded_word = urllib.parse.quote(search_word)
    suumo_url = f"https://suumo.jp/jj/chintai/ichiran/FR301FC011/?ar=030&bs=040&kskbn=01&fw={encoded_word}"
    
    main_window = driver.current_window_handle
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[-1])
    
    print(f"🔗 [{index}] SUUMO調査: {search_word}")
    driver.get(suumo_url)
    time.sleep(3)

    # --- スクショ保存処理 ---
    # 物件名からファイル名に使えない記号を除去
    safe_name = re.sub(r'[\\/:*?"<>|]', '', info['name'])
    filename = f"suumo_{index}_{safe_name}.png"
    driver.save_screenshot(filename)
    print(f"📸 スクショ保存完了: {filename}")
    # -----------------------

    match_count = 0
    try:
        items = driver.find_elements(By.CSS_SELECTOR, ".property.property--highlight")
        target_rent_val = normalize_text(info['rent']).replace('万', '')
        target_area_norm = normalize_text(info['area'])

        for item in items:
            try:
                rent_text = normalize_text(item.find_element(By.CSS_SELECTOR, ".detailbox-property-point").text).replace('万円', '')
                area_el = item.find_element(By.CSS_SELECTOR, ".detailbox-property--col3 div:nth-child(2)")
                area_text = driver.execute_script("""
                    let el = arguments[0].cloneNode(true);
                    el.querySelectorAll('sup').forEach(s => s.remove());
                    return el.textContent;
                """, area_el)
                area_text = normalize_text(area_text)

                if rent_text == target_rent_val and area_text == target_area_norm:
                    match_count += 1
            except: continue
    except: pass
    
    driver.close()
    driver.switch_to.window(main_window)
    return match_count

def main():
    driver = create_driver()
    send_discord("🔍 調査を開始します (最強URL検索版)")
    
    last_modal_address = ""
    last_modal_area = ""

    try:
        # todayを外したURLでアクセス
        driver.get("https://rent.es-square.net/bukken/chintai/search?jusho=13%2B101&jusho=13%2B102&jusho=13%2B103&jusho=13%2B104&jusho=13%2B105&jusho=13%2B106&jusho=13%2B107&jusho=13%2B108&jusho=13%2B109&jusho=13%2B110&jusho=13%2B111&jusho=13%2B112&jusho=13%2B113&jusho=13%2B114&jusho=13%2B115&jusho=13%2B116&jusho=13%2B120&jusho=13%2B203&jusho=13%2B204&jusho=13%2B229&jusho=13%2B211&jusho=13%2B210&search_madori_code2=2&search_madori_code2=1&kodawari=separatedBathAndToilet&is_exclude_moshikomi_exist=true&order=saishu_koshin_time.desc&p=1&items_per_page=30")
        
        # ログイン処理
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(10)

        # 全件読み込みスクロール
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")

        items_xpath = '//div[@data-testclass="bukkenListItem"]'
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, items_xpath)))
        items = driver.find_elements(By.XPATH, items_xpath)
        
        found_count = 0
        for i in range(len(items)):
            try:
                current_items = driver.find_elements(By.XPATH, items_xpath)
                item = current_items[i]
                name = item.find_element(By.CSS_SELECTOR, 'h2').text.strip()
                
                # モーダルを開く
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", item)
                
                modal = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.MuiBox-root.css-ne16qb')))
                
                # 情報抽出（住所・築年月・階建て・面積）
                info = {}
                for _ in range(30):
                    addr_el = modal.find_element(By.CSS_SELECTOR, "div.MuiBox-root.css-1x36n8t")
                    area_match = re.search(r'(\d+(\.\d+)?㎡)', modal.text)
                    if addr_el.text.strip() != last_modal_address or (area_match and area_match.group(1) != last_modal_area):
                        info['address'] = addr_el.text.strip()
                        info['area'] = area_match.group(1) if area_match else ""
                        last_modal_address = info['address']
                        last_modal_area = info['area']
                        break
                    time.sleep(0.3)

                # 築年月取得 (例: 2004/01 -> 2004年1月)
                built_text = ""
                try:
                    built_div = driver.execute_script("""
                        return Array.from(document.querySelectorAll('div.MuiGrid-root'))
                            .find(div => div.querySelector('b')?.innerText.trim() === '築年月')
                            .nextElementSibling.innerText.trim();
                    """)
                    m = re.match(r'(\d{4})/(\d{1,2})', built_div)
                    built_text = f"{m.group(1)}年{int(m.group(2))}月" if m else built_div
                except: built_text = ""
                info['built'] = built_text

                # 階建て取得 (例: 4階建)
                floor_match = re.search(r'地上(\d+)階', modal.text)
                info['floors'] = f"{floor_match.group(1)}階建" if floor_match else ""

                # 賃料取得 (123000 -> 12.3万)
                rent_display = ""
                list_boxes = driver.find_elements(By.CSS_SELECTOR, '.MuiBox-root.css-1t7sidb')
                for box in list_boxes:
                    if box.find_element(By.CSS_SELECTOR, 'p.MuiTypography-root.MuiTypography-body1.css-1bkh2wx').text.strip() == name:
                        rent_box = box.find_element(By.XPATH, './following-sibling::div[contains(@class, "css-57ym5z")]')
                        rent_val = driver.execute_script("return Array.from(arguments[0].querySelectorAll('span')).find(s => s.textContent.includes(',')).textContent;", rent_box)
                        rent_display = f"{int(rent_val.replace(',', '')) / 10000:g}万"
                        break
                info['rent'] = rent_display
                info['name'] = name

                # SUUMO照合実行
                count = check_suumo(driver, info, i + 1)
                
                if count == 0:
                    send_discord(f"✨ 【完全新着候補】他社 0件\n物件: {name} ({info['floors']})\n条件: {info['rent']} / {info['area']}\n築年: {info['built']}")
                    found_count += 1

                # モーダルを閉じる
                close_btn = driver.find_element(By.CSS_SELECTOR, '.MuiBox-root.css-1xhj18k svg[data-testid="CloseIcon"]')
                driver.execute_script("arguments[0].closest('button').click();", close_btn)
                time.sleep(1)

            except Exception as e:
                print(f"物件スキップ: {e}")
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(1)

        send_discord(f"✅ 調査完了。{found_count}件のお宝候補が見つかりました。")

    except Exception as e:
        send_discord(f"🚨 システム停止: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()

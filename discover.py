import os
import time
import re
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys  # エスケープキー用に追加

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
    return val / 10000.0 if val > 1000 else val

def check_suumo(driver, info):
    """SUUMO照合ロジック"""
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
    print("--- 調査開始 ---")
    
    try:
        # 1. ログイン
        driver.get("https://rent.es-square.net/bukken/chintai/search?jusho=13%2B101&jusho=13%2B102&jusho=13%2B103&jusho=13%2B104&jusho=13%2B105&jusho=13%2B106&jusho=13%2B107&jusho=13%2B108&jusho=13%2B109&jusho=13%2B110&jusho=13%2B111&jusho=13%2B112&jusho=13%2B113&jusho=13%2B114&jusho=13%2B115&jusho=13%2B116&jusho=13%2B120&jusho=13%2B203&jusho=13%2B204&jusho=13%2B229&jusho=13%2B211&jusho=13%2B210&search_madori_code2=2&search_madori_code2=1&kokai_radio_state=today&kodawari=separatedBathAndToilet&is_exclude_moshikomi_exist=true&order=saishu_koshin_time.desc&p=1&items_per_page=30")
        
        print("ログイン実行中...")
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        time.sleep(15) 
        
        # 2. 物件リスト取得
        items = driver.find_elements(By.CSS_SELECTOR, 'div[data-testclass="bukkenListItem"]')
        print(f"発見物件数: {len(items)}")
        
        if not items:
            send_discord("⚠️ 物件が見つかりませんでした（リスト空）")
            return

        found_count = 0
        for i in range(min(len(items), 15)):
            try:
                # 毎回リストを最新状態で取得
                current_items = driver.find_elements(By.CSS_SELECTOR, 'div[data-testclass="bukkenListItem"]')
                item = current_items[i]
                
                name = item.find_element(By.CSS_SELECTOR, 'p.css-1bkh2wx').text.strip()
                rent_val = clean_num(item.text.split("円")[0].split("\n")[-1])

                # 物件をクリックしてモーダルを開く
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                time.sleep(1)
                item.click()
                
                # モーダル要素を特定
                modal = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.MuiBox-root.css-ne16qb')))
                
                area_match = re.search(r'(\d+\.?\d*)㎡', modal.text)
                area_val = float(area_match.group(1)) if area_match else 0.0
                floor_match = re.search(r'地上(\d+)階', modal.text)
                floor = floor_match.group(0) if floor_match else ""

                info = {"name": name, "rent": rent_val, "area": area_val, "floor": floor}
                print(f"🧐 [{i+1}] 照合中: {name} ({rent_val}万/{area_val}㎡)")

                # SUUMO照合
                count = check_suumo(driver, info)
                if count <= 1:
                    send_discord(f"✨ 【お宝候補】競合 {count}社\n物件: {name} {floor}\n条件: {rent_val}万 / {area_val}㎡")
                    found_count += 1

                # --- 修正の要：モーダルを確実に閉じる ---
                print("物件詳細モーダルを閉じます...")
                # ページ全体ではなく、modal要素の中からCloseIconを探す（これで市区町村チップの誤爆を防ぐ）
                try:
                    close_svg = modal.find_element(By.CSS_SELECTOR, 'svg[data-testid="CloseIcon"]')
                    # SVGの親であるButton要素をJSでクリック
                    driver.execute_script("arguments[0].closest('button').click();", close_svg)
                except:
                    # 失敗時のバックアップ：エスケープキーで閉じる
                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)

                # モーダルが消えるのを待つ
                WebDriverWait(driver, 10).until_not(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.MuiBox-root.css-ne16qb')))
                time.sleep(1)

            except Exception as e:
                print(f"物件[{i}] スキップ原因: {e}")
                # 万が一変なモーダルが開いていたらエスケープキーで閉じる
                try: driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                except: pass
                continue

        send_discord(f"✅ 調査完了。{found_count}件のお宝が見つかりました。")

    except Exception as e:
        print(f"致命的なエラー: {e}")
        send_discord(f"🚨 システム停止: {e}")
    finally:
        driver.save_screenshot("evidence.png")
        driver.quit()

if __name__ == "__main__":
    main()

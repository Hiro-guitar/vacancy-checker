import os
import time
import re
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def create_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=2560,1440')
    return webdriver.Chrome(options=options)

def send_discord(message):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if url: requests.post(url, json={"content": message})

def clean_num(text):
    """'12.5万円' や '125,000' から '12.5' という数値だけを抽出する"""
    if not text: return 0.0
    text = text.replace(',', '').translate(str.maketrans('０１２３４５６７８９．', '0123456789.'))
    match = re.search(r'\d+\.?\d*', text)
    if not match: return 0.0
    val = float(match.group())
    return val / 10000.0 if val > 1000 else val

def check_suumo(driver, info):
    """数値ベースでSUUMOと照合（誤差0.01以内なら一致とみなす）"""
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
            s_rent = clean_num(card.find_element(By.CSS_SELECTOR, ".detailbox-property-point").text)
            s_area = clean_num(card.find_element(By.CSS_SELECTOR, ".detailbox-property--col3 div:nth-child(2)").text)
            
            # 数値での精密比較
            if abs(s_rent - info['rent']) < 0.01 and abs(s_area - info['area']) < 0.01:
                match_count += 1
    except: pass
    
    driver.close()
    driver.switch_to.window(main_window)
    return match_count

def main():
    driver = create_driver()
    try:
        # ログイン・ページ遷移（省略）
        driver.get("https://rent.es-square.net/bukken/chintai/search?...") 
        # ... (ログイン処理は以前のものを流用) ...
        
        time.sleep(10)

        for i in range(15):
            try:
                # 物件要素の再取得
                items = driver.find_elements(By.CSS_SELECTOR, 'div[data-testclass="bukkenListItem"]')
                if i >= len(items): break
                item = items[i]

                # 1. 一覧から賃料を取得 (拡張機能のロジック)
                rent_text = item.text.split("円")[0].split("\n")[-1] # 簡易取得
                rent_val = clean_num(rent_text)

                # 2. クリックしてモーダルを開く
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                time.sleep(1)
                item.click()

                # 3. モーダルから詳細情報を取得
                modal = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div.MuiBox-root.css-ne16qb'))
                )
                
                name = modal.querySelector("div.css-vpfv1m").text # 拡張機能のセレクタ
                area_match = re.search(r'(\d+\.?\d*)㎡', modal.text)
                area_val = float(area_match.group(1)) if area_match else 0.0
                
                # 地上◯階 の取得
                floor_match = re.search(r'地上(\d+)階', modal.text)
                floor = floor_match.group(0) if floor_match else ""

                info = {"name": name, "rent": rent_val, "area": area_val, "floor": floor}
                print(f"🧐 調査中: {name} ({rent_val}万/{area_val}㎡)")

                # 4. SUUMO照合
                count = check_suumo(driver, info)
                if count <= 1:
                    send_discord(f"✨ 【お宝】競合{count}社: {name}\n{rent_val}万 / {area_val}㎡")

                # 5. 【重要】モーダルを確実に閉じる (拡張機能のセレクタを適用)
                # 拡張機能の .css-1xhj18k を使って閉じるボタンを特定
                close_btn = driver.find_element(By.CSS_SELECTOR, '.MuiBox-root.css-1xhj18k svg[data-testid="CloseIcon"]')
                driver.execute_script("arguments[0].closest('button').click();", close_btn)
                
                # モーダルが消えるのを待つ（これがないと次がクリックできない）
                WebDriverWait(driver, 10).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div.MuiBox-root.css-ne16qb'))
                )
                time.sleep(1)

            except Exception as e:
                print(f"物件{i+1}スキップ: {e}")
                # 強制的にモーダルを閉じる試行
                driver.execute_script("""
                    var close = document.querySelector('.MuiBox-root.css-1xhj18k svg[data-testid="CloseIcon"]');
                    if(close) close.closest('button').click();
                """)
                continue

    finally:
        driver.quit()

if __name__ == "__main__":
    main()

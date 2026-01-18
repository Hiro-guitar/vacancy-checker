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

def clean_num_strict(text):
    if not text: return 0.0
    text = text.replace(',', '').translate(str.maketrans('０１２３４５６７８９．', '0123456789.'))
    nums = re.findall(r'\d+\.?\d*', text)
    if not nums: return 0.0
    return float(nums[0])

def normalize_text(text):
    if not text: return ""
    # 全角数字・記号を半角に変換
    text = text.translate(str.maketrans('０１２３４５６７８９．', '0123456789.'))
    # 空白削除、㎡をmに、カンマ削除
    text = re.sub(r'\s+', '', text)
    text = text.replace('㎡', 'm').replace(',', '')
    return text.strip()

def extract_kanji_address(text):
    """
    住所から「〇〇丁目」までを抽出し、数字を半角にする
    例：東京都新宿区西新宿３丁目5-15 -> 東京都新宿区西新宿3
    """
    if not text: return ""
    # 全角数字を半角にする
    text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
    # 「◯丁目」までを抽出する正規表現
    match = re.search(r'(.+?\d+)丁目', text)
    if match:
        return match.group(1) # 「西新宿3」の部分だけ返す
    return text # 丁目がない場合はそのまま

def check_suumo(driver, info, index):
    # 検索語句を組み立て (住所 築年月 階建て 面積 賃料)
    # 例: "東京都練馬区... 1998年4月 4階建 26m 9万"
    search_word = f"{info['address']} {info['built']} {info['floors']} {info['area']} {info['rent']}"
    search_word = search_word.replace('㎡', 'm')
    
    encoded_word = urllib.parse.quote(search_word)
    # 高精度な一覧表示用エンドポイントを使用
    suumo_url = f"https://suumo.jp/jj/chintai/ichiran/FR301FC011/?ar=030&bs=040&kskbn=01&fw={encoded_word}"
    
    main_window = driver.current_window_handle
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[-1])
    driver.get(suumo_url)
    time.sleep(3) # 読み込み待機

    # 個別スクショ保存（物件名を含める）
    safe_name = re.sub(r'[\\/:*?"<>|]', '', info['name'])
    driver.save_screenshot(f"suumo_{index}_{safe_name}.png")

    match_count = 0
    try:
        # 拡張機能と同じく「広告物件」のみをターゲットにする
        cards = driver.find_elements(By.CSS_SELECTOR, ".property.property--highlight")
        target_rent = normalize_text(info['rent']).replace('万', '')
        target_area = normalize_text(info['area']).replace('m', '')

        for card in cards:
            try:
                # 賃料の取得
                s_rent = normalize_text(card.find_element(By.CSS_SELECTOR, ".detailbox-property-point").text).replace('万円', '')
                # 面積の取得 (supタグを除去して「20.50m2」を「20.50m」にする)
                area_el = card.find_element(By.CSS_SELECTOR, ".detailbox-property--col3 div:nth-child(2)")
                s_area = driver.execute_script("""
                    let el = arguments[0].cloneNode(true);
                    el.querySelectorAll('sup').forEach(s => s.remove());
                    return el.textContent;
                """, area_el)
                s_area = normalize_text(s_area).replace('m', '')

                if s_rent == target_rent and s_area == target_area:
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
        driver.get("https://rent.es-square.net/bukken/chintai/search?jusho=13%2B101&jusho=13%2B102&jusho=13%2B103&jusho=13%2B104&jusho=13%2B105&jusho=13%2B106&jusho=13%2B107&jusho=13%2B108&jusho=13%2B109&jusho=13%2B110&jusho=13%2B111&jusho=13%2B112&jusho=13%2B113&jusho=13%2B114&jusho=13%2B115&jusho=13%2B116&jusho=13%2B120&jusho=13%2B203&jusho=13%2B204&jusho=13%2B229&jusho=13%2B211&jusho=13%2B210&search_madori_code2=2&search_madori_code2=1&kodawari=separatedBathAndToilet&is_exclude_moshikomi_exist=true&order=one_network_keisai_kaishi_time.desc&p=1&items_per_page=30")
        
        # ログイン
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        # ログイン後の待機
        time.sleep(15) 
        driver.save_screenshot("debug_1_after_login.png") # 【スクショ1】ログイン直後
        
        # --- 追加：30件全てを表示させるための強制スクロール処理 ---
        print("📥 物件リストを最後まで読み込んでいます...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3) 
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        
        driver.save_screenshot("debug_2_after_scroll.png") # 【スクショ2】スクロール後
        
        # 読み込み終わったら、要素取得のために一番上に戻す
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        # 3. トータル件数のログ出力
        try:
            total_text = driver.find_element(By.CSS_SELECTOR, '.MuiTypography-root.MuiTypography-body1.css-12s8z8r').text
            print(f"📊 ページ表示状況: {total_text}")
        except:
            print("⚠️ 件数表示が見つかりませんでした")

        items_xpath = '//div[@data-testclass="bukkenListItem"]'
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, items_xpath)))
        items = driver.find_elements(By.XPATH, items_xpath)
        print(f"発見物件数: {len(items)}")
        
        driver.save_screenshot("debug_3_ready_to_loop.png") # 【スクショ3】ループ開始直前
        
        found_count = 0
        for i in range(len(items)):
            try:
                current_items = driver.find_elements(By.XPATH, items_xpath)
                item = current_items[i]
                
                name = item.find_element(By.CSS_SELECTOR, 'p.css-1bkh2wx').text.strip()
                rent_raw = 0.0
                
                list_boxes = driver.find_elements(By.CSS_SELECTOR, '.MuiBox-root.css-1t7sidb')
                for box in list_boxes:
                    try:
                        name_el = box.find_element(By.CSS_SELECTOR, 'p.MuiTypography-root.MuiTypography-body1.css-1bkh2wx')
                        if name_el.text.strip() == name:
                            rent_box = box.find_element(By.XPATH, './following-sibling::div[contains(@class, "css-57ym5z")]')
                            rent_spans = rent_box.find_elements(By.CSS_SELECTOR, 'span.css-smu62q')
                            for s in rent_spans:
                                val = s.get_attribute("textContent")
                                if "," in val:
                                    rent_raw = clean_num_strict(val)
                                    break
                            if rent_raw > 0: break 
                    except: continue

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", item)
                
                # 1. モーダル表示待機
                modal = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.MuiBox-root.css-ne16qb')))
                
                # --- 物件詳細URLをこの時点のブラウザのURLから取得 ---
                bukken_url = driver.current_url
                
                # --- 判定フラグをこのスコープで完全に初期化 ---
                current_ad_status = None # "OK", "CHECK_TOOLTIP", "NG" のいずれかを入れる
                ad_tag_el = None

                # 広告タグが表示されるまで少し待機（最大3秒）
                time.sleep(1) 
                
                # モーダル内(modal.)のタグだけを厳密に取得
                tags = modal.find_elements(By.CSS_SELECTOR, ".eds-tag__label")
                
                for tag in tags:
                    txt = tag.text.strip()
                    if txt == "広告可":
                        current_ad_status = "OK"
                        break
                    elif txt == "広告可※":
                        current_ad_status = "CHECK_TOOLTIP"
                        ad_tag_el = tag
                        break
                
                # 判定: OKでもCHECK_TOOLTIPでもなければ、即座に「NG」としてスキップ
                if current_ad_status is None:
                    print(f"⏭️ スキップ (広告不可・タグなし): {name}")
                    driver.execute_script("document.querySelector('.MuiBox-root.css-1xhj18k button').click();")
                    time.sleep(1)
                    continue

                # 2. 広告可※ の場合のツールチップ深掘り
                if current_ad_status == "CHECK_TOOLTIP":
                    from selenium.webdriver.common.action_chains import ActionChains
                    # 確実に要素へスクロールしてからホバー
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", ad_tag_el)
                    ActionChains(driver).move_to_element(ad_tag_el).perform()
                    time.sleep(0.8)

                    try:
                        # 画面全体から今出ているツールチップを探す
                        tooltip = driver.find_element(By.CSS_SELECTOR, ".MuiTooltip-popper")
                        if "SUUMO賃貸" not in tooltip.text:
                            print(f"⏭️ スキップ (広告可※ですがSUUMO不可): {name}")
                            driver.execute_script("document.querySelector('.MuiBox-root.css-1xhj18k button').click();")
                            time.sleep(1)
                            continue
                    except:
                        print(f"⚠️ ツールチップが読み取れなかったためスキップ: {name}")
                        driver.execute_script("document.querySelector('.MuiBox-root.css-1xhj18k button').click();")
                        time.sleep(1)
                        continue
                
                # --- ここを通過した物件だけが「本物の調査対象」 ---
                print(f"✅ 調査対象(広告許可済): {name}")

                # 【追加】物件詳細モーダルのスクショを保存
                # ファイル名に使用できない記号を除去
                safe_name = re.sub(r'[\\/:*?"<>|]', '', name)
                driver.save_screenshot(f"es_modal_{i+1}_{safe_name}.png")

                # 1. 住所・面積・階数を取得（情報の更新を厳密に待機）
                # --- Chrome拡張互換：住所と面積の同期待ちロジック ---
                address_val = ""
                area_val_str = ""
                floor_val_str = ""

                # ループの外で定義した lastModalAddress, lastModalArea を更新していく
                # ※ main() の冒頭で lastModalAddress = ""; lastModalArea = "" を定義しておいてください
                
                print(f"⏳ 同期待機中: {name}")

                for _ in range(50):  # 100ms * 50 = 最大5秒待機
                    try:
                        # 1. 住所の取得
                        addr_el = modal.find_element(By.CSS_SELECTOR, "div.MuiBox-root.css-1x36n8t")
                        current_address = addr_el.text.strip()
                        
                        # 2. 面積の取得
                        area_match = re.search(r'(\d+(\.\d+)?㎡)', modal.text)
                        current_area = area_match.group(1) if area_match else ""

                        # 【重要】Chrome拡張と同じ判定ロジック
                        # 「住所があり」「面積があり」「(住所か面積のどちらかが前回と違う)」場合にループを抜ける
                        # ※同じマンションの別部屋対策として、物件名(name)のチェックも加えるとより鉄壁です
                        if current_address and current_area:
                            if (current_address != lastModalAddress) or (current_area != lastModalArea):
                                address_val = extract_kanji_address(current_address)
                                area_val_str = current_area
                                
                                # 更新成功：前回の値を今回の値で上書き
                                lastModalAddress = current_address
                                lastModalArea = current_area
                                
                                # 階数の取得
                                floor_match = re.search(r'地上(\d+)階', modal.text)
                                floor_val_str = f"{floor_match.group(1)}階建" if floor_match else ""
                                break
                    except:
                        pass
                    time.sleep(0.1) # 100ms待機
                
                # 同期後に物件詳細スクショを撮る（拡張機能の挙動に近いタイミング）
                safe_name = re.sub(r'[\\/:*?"<>|]', '', name)
                driver.save_screenshot(f"es_modal_{i+1}_{safe_name}.png")

                # 2. 「築年月」を取得 (例: 2004/01 → 2004年1月)
                built_val = ""
                try:
                    built_raw = driver.execute_script("""
                        return Array.from(document.querySelectorAll('div.MuiGrid-root'))
                            .find(div => div.querySelector('b')?.innerText.trim() === '築年月')
                            .nextElementSibling.innerText.trim();
                    """)
                    m = re.match(r'(\d{4})/(\d{1,2})', built_raw)
                    built_val = f"{m.group(1)}年{int(m.group(2))}月" if m else built_raw
                except: pass

                # 3. 賃料を「9万」のような万円表記に変換
                rent_man_str = f"{rent_raw / 10000:g}万"

                # 4. SUUMOに渡すための情報セット(info)
                info = {
                    "name": name,
                    "address": address_val, # ← 丁目までの住所が入る
                    "built": built_val,
                    "floors": floor_val_str,
                    "area": area_val_str,
                    "rent": rent_man_str
                }

                print(f"🧐 [{i+1}] 照合中: {name} ({address_val} / {rent_man_str} / {built_val})")

                # 5. SUUMOチェック実行
                count = check_suumo(driver, info, i + 1)

                # --- 追加: タブを閉じて戻ってきた後の安定化処理 ---
                time.sleep(1) # ブラウザのコンテキストが復帰するのを待つ
                driver.switch_to.window(driver.window_handles[0]) # 念のため再度メインウィンドウを指定

                if count <= 1:
                    rent_man = rent_raw / 10000.0
                    # メッセージの最後に \n\n を入れることで、次のメッセージとの間に隙間を作ります
                    # また、各項目の頭に絵文字を追加し、物件名を太字にするなどの装飾も可能です
                    message = (
                        f"━━━━━━━━━━━━━━━\n" # 区切り線
                        f"✨ **【お宝候補】他社掲載 {count}件**\n\n"
                        f"🏠 **物件名**: {name}\n"
                        f"🏢 **階数**: {floor_val_str}\n"
                        f"📍 **場所**: {info['address']}\n"
                        f"💰 **条件**: {rent_man}万 / {area_val_str} / {built_val}\n\n"
                        f"🔗 **詳細URL**\n{bukken_url}\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"\n" # ← これが次のメッセージとの間の「ゆとり」になります
                    )
                    send_discord(message)
                    found_count += 1

                # モーダルを閉じる
                driver.execute_script("""
                    var closeBtn = document.querySelector('.MuiBox-root.css-1xhj18k svg[data-testid="CloseIcon"]');
                    if (closeBtn) closeBtn.closest('button').click();
                """)
                time.sleep(1.2)

            except Exception as e:
                print(f"物件[{i}] スキップ: {e}")
                # エラー時も一応ESCキーでモーダルを閉じる試行
                try:
                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                except: pass
                time.sleep(1)

        send_discord(f"✅ 調査完了。{found_count}件見つかりました。")

    except Exception as e:
        print(f"エラー: {e}")
        send_discord(f"🚨 システム停止: {e}")
    finally:
        print("最終エビデンスを保存します...")
        driver.save_screenshot("evidence.png")
        driver.quit()

if __name__ == "__main__":
    main()

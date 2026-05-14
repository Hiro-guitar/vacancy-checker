import os
import json
import base64
import time
import datetime
import gspread
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from oauth2client.service_account import ServiceAccountCredentials
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from selenium.common.exceptions import TimeoutException

def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ('http', 'https') and result.netloc != ""
    except:
        return False

def create_driver():
    options = Options()
    options.add_argument('--headless=new')  # ✅ Headlessモードを明示
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1280,1024')
    return webdriver.Chrome(options=options)

# === 初期準備 ===
os.makedirs("screenshots", exist_ok=True)

gspread_raw = os.environ["GSPREAD_JSON"]
json_str = gspread_raw if gspread_raw.strip().startswith('{') else base64.b64decode(gspread_raw).decode('utf-8')
cred = ServiceAccountCredentials.from_json_keyfile_dict(
    json.loads(json_str),
    ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
)
client = gspread.authorize(cred)
sheet = client.open_by_key(os.environ['SPREADSHEET_ID']).worksheet("シート1")

URL_COL = 13
STATUS_COL = 9
ENDED_COL = 11
all_rows = sheet.get_all_values()[1:]

# === 共通処理 ===
def process_rows(driver, login_func, url_keyword, checker_func):
    print(f"🔍 {url_keyword} の処理を開始します")
    logged_in = login_func(driver)
    if not logged_in:
        print(f"❌ {url_keyword} のログインに失敗したためスキップします")
        return

    for row_num, row in enumerate(all_rows, start=2):
        url = row[URL_COL - 1].strip()
        if url_keyword not in url or not is_valid_url(url):
            continue

        now_jst = datetime.datetime.now(ZoneInfo("Asia/Tokyo"))
        current_status = row[STATUS_COL - 1].strip()
        current_date = row[ENDED_COL - 1].strip()
        has_application = False

        try:
            has_application = checker_func(driver, url, row_num)

            if has_application:
                sheet.update_cell(row_num, STATUS_COL, "")
                if current_status != "":
                    sheet.update_cell(row_num, ENDED_COL, now_jst.strftime("%Y-%m-%d %H:%M"))
                else:
                    print(f"🔁 Row {row_num} → すでに申込あり、日付維持")
            else:
                sheet.update_cell(row_num, STATUS_COL, "募集中")
                if current_date != "":
                    sheet.update_cell(row_num, ENDED_COL, "")

        except Exception as e:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            screenshot_path = f"screenshots/row_{row_num}_error_{timestamp}.png"
            html_path = f"screenshots/row_{row_num}_error_{timestamp}.html"
            try:
                driver.save_screenshot(screenshot_path)
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
            except Exception as ee:
                print(f"⚠ Row {row_num} スクショ保存失敗: {ee}")
            print(f"❌ Row {row_num} エラー: {e}")
            print(f"→ スクショ: {screenshot_path}")

# === 各ログイン関数・チェック関数 ===

def login_es(driver):
    for row in all_rows:
        url = row[URL_COL - 1].strip()
        if "es-square.net" not in url:
            continue
        driver.get(url)
        try:
            # ユーザー名入力待ち
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "username")))
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "password")))

            driver.find_element(By.ID, "username").send_keys(os.environ["ES_EMAIL"])
            driver.find_element(By.ID, "password").send_keys(os.environ["ES_PASSWORD"])

            # 「続ける」ボタンをクリック
            driver.find_element(By.XPATH, "//button[@type='submit']").click()

            # ログイン後の画面に「物件概要」が出るまで待機
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), '物件')]")),
            )

            print("✅ ESログイン成功")
            return True

        except Exception as e:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            screenshot_path = f"screenshots/es_login_error_{timestamp}.png"
            driver.save_screenshot(screenshot_path)
            print(f"❌ ESログイン失敗: {e}")
            print(f"📸 スクショ: {screenshot_path}")
            return False
    return False

from selenium.common.exceptions import TimeoutException

def check_es(driver, url, row_num):
    driver.get(url)

    try:
        # 申込あり or 404 エラーの要素が現れるまで最大20秒待機
        WebDriverWait(driver, 20).until(
            lambda d: d.find_elements(By.XPATH, "//span[contains(@class, 'eds-tag__label') and normalize-space(text())='申込あり']") 
                      or d.find_elements(By.XPATH, "//div[contains(text(), 'エラーコード：404')]")
        )
    except TimeoutException:
        print(f"⚠ Row {row_num} ES → 要素が見つからずタイムアウト。募集中と判定")
    
    # 申込ありの要素を取得
    applied = driver.find_elements(By.XPATH, "//span[contains(@class, 'eds-tag__label') and normalize-space(text())='申込あり']")
    # 404エラーの要素を取得
    error404 = driver.find_elements(By.XPATH, "//div[contains(text(), 'エラーコード：404')]")
    
    # スクリーンショットも残しておくとデバッグしやすい
    screenshot_path = f"screenshots/es_row_{row_num}.png"
    driver.save_screenshot(screenshot_path)
    print(f"📸 Row {row_num} スクリーンショット: {screenshot_path}")

    if applied or error404:
        return True  # 申込済み
    else:
        return False  # 募集中

def login_itandi(driver):
    for row in all_rows:
        url = row[URL_COL - 1].strip()
        if "itandibb.com" not in url:
            continue

        driver.get(url)

        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "email")))
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "password")))

            email_input = driver.find_element(By.ID, "email")
            password_input = driver.find_element(By.ID, "password")

            email_input.clear()
            email_input.send_keys(os.environ["ITANDI_EMAIL"])
            password_input.clear()
            password_input.send_keys(os.environ["ITANDI_PASSWORD"])

            login_btn = driver.find_element(By.CSS_SELECTOR, 'input.filled-button[type="submit"]')
            login_btn.click()

            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'ログアウト') or contains(text(), '物件')]"))
            )

            print("✅ ITANDIログイン成功")
            return True

        except Exception as e:
            # 👇 スクリーンショット保存をここで実施
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            screenshot_path = f"screenshots/itandi_login_error_{timestamp}.png"
            html_path = f"screenshots/itandi_login_error_{timestamp}.html"
            try:
                driver.save_screenshot(screenshot_path)
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
                print(f"📸 ITANDI スクリーンショット: {screenshot_path}")
                print(f"📝 ITANDI HTML: {html_path}")
            except Exception as ee:
                print(f"⚠ スクリーンショット保存失敗: {ee}")

            print(f"❌ ITANDIログイン失敗: {e}")
            return False

    return False

def check_itandi(driver, url, row_num):
    driver.get(url)
    time.sleep(2)
    elems = driver.find_elements(By.XPATH, "//div[contains(@class, 'Block Left')]")
    has_open = any("募集中" in elem.text for elem in elems)
    screenshot_path = f"screenshots/itandi_row_{row_num}.png"
    driver.save_screenshot(screenshot_path)
    print(f"📸 ITANDI Row {row_num} スクリーンショット: {screenshot_path}")
    return not has_open

def login_ielove(driver):
    for row in all_rows:
        url = row[URL_COL - 1].strip()
        if "bb.ielove.jp" not in url:
            continue
        try:
            driver.get("https://bb.ielove.jp/ielovebb/login/login/")
            # フォーム本体を待つ。 input の name/id は毎回ハッシュ化されて変わるため
            # 直接指定せず form scope + type で取得する (Chrome 拡張と同じ戦略)。
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "form#loginForm"))
            )
            id_input = driver.find_element(
                By.CSS_SELECTOR, "form#loginForm input[type='text']"
            )
            pw_input = driver.find_element(
                By.CSS_SELECTOR, "form#loginForm input[type='password']"
            )
            id_input.send_keys(os.environ["IELOVE_ID"])
            pw_input.send_keys(os.environ["IELOVE_PASSWORD"])
            # 送信ボタン (id="loginButton" は安定、ハッシュ化されていない)
            try:
                submit_btn = driver.find_element(By.ID, "loginButton")
            except Exception:
                submit_btn = driver.find_element(
                    By.CSS_SELECTOR, "form#loginForm input[type='submit'], form#loginForm button[type='submit']"
                )
            submit_btn.click()
            # ログイン後判定: URL が /login/ から離脱したかを確認
            # (旧実装は div.savedSearch__title を待っていたがこれも UI 更新で壊れやすい)
            WebDriverWait(driver, 20).until(
                lambda d: "/login/" not in d.current_url
            )
            print("✅ IELBBログイン成功")
            return True
        except Exception as e:
            # 例外メッセージが空の場合(TimeoutException など)も型名で判別できるよう型名も出力
            err_msg = str(e).strip() or type(e).__name__
            print(f"❌ IELBBログイン失敗: {err_msg}")
            return False
    return False

def check_ielove(driver, url, row_num):
    driver.get(url)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.mar-top-12.detail-info.leasing-detail-info"))
        )
    except Exception:
        print(f"⚠ Row {row_num} IELBB → 要素の表示待ちタイムアウト")
    time.sleep(1)
    app_elems = driver.find_elements(By.CSS_SELECTOR, "span.exists_application_for_confirm")
    rent_elems = driver.find_elements(By.CSS_SELECTOR, "span.for-rent")
    screenshot_path = f"screenshots/ielove_row_{row_num}.png"
    driver.save_screenshot(screenshot_path)
    print(f"📸 IELBB Row {row_num} スクリーンショット: {screenshot_path}")
    if app_elems:
        return True
    elif rent_elems:
        return False
    else:
        print(f"⚠ Row {row_num} IELBB → 判定不能")
        return True

# === 順番に実行 ===
for target in [
    ("es-square.net", login_es, check_es),
    ("itandibb.com", login_itandi, check_itandi),
    ("bb.ielove.jp", login_ielove, check_ielove)
]:
    driver = create_driver()
    process_rows(driver, target[1], target[0], target[2])
    driver.quit()

print("✅ 全処理完了")

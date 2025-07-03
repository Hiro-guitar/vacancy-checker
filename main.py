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

def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ('http', 'https') and result.netloc != ""
    except:
        return False

# === Google Sheets 認証 ===
json_str = base64.b64decode(os.environ['GSPREAD_JSON']).decode('utf-8')
cred = ServiceAccountCredentials.from_json_keyfile_dict(
    json.loads(json_str),
    ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
)
client = gspread.authorize(cred)
sheet = client.open_by_key(os.environ['SPREADSHEET_ID']).worksheet("シート1")

# === 対象列インデックス ===
URL_COL = 13   # M列
STATUS_COL = 9 # I列
ENDED_COL = 11 # K列

# === スクリーンショット保存先フォルダ ===
os.makedirs("screenshots", exist_ok=True)

# === Chrome起動 ===
options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-blink-features=AutomationControlled')
options.add_argument('--window-size=1280,1024')  # PCレイアウトを保つため
driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(30)

# === 最初のログイン対象URLを取得 ===
first_url = None
all_rows = sheet.get_all_values()[1:]  # ヘッダーを除外
for row in all_rows:
    url = row[URL_COL - 1].strip()
    if is_valid_url(url) and ("es-square.net" in url or "itandibb.com" in url):
        first_url = url
        break

if not first_url:
    print("対象物件URLが見つかりませんでした。")
    driver.quit()
    exit()

print(f"🔗 最初のアクセスURL: {first_url}")

# === ログイン処理 ===
try:
    if "es-square.net" in first_url:
        driver.get(first_url)
        time.sleep(2)

        login_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'いい生活アカウントでログイン')]"))
        )
        login_btn.click()

        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.NAME, "username")))
        driver.find_element(By.NAME, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.NAME, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()

        WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located(
                (By.XPATH, "//*[contains(text(), '物件概要') or contains(text(), 'エラーコード：404')]")
            )
        )

        print("✅ es-square ログイン成功")

    elif "itandibb.com" in first_url:
        def debug_save(step):
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            driver.save_screenshot(f'screenshots/itandi_debug_{step}_{ts}.png')
            with open(f'screenshots/itandi_debug_{step}_{ts}.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            print(f"📸 {step} - URL: {driver.current_url}")

        # Step 1: ログインページへアクセス
        driver.get("https://itandi-accounts.com/login?client_id=itandi_bb&redirect_uri=https%3A%2F%2Fitandibb.com%2Fitandi_accounts_callback&response_type=code")
        debug_save("01_login_page")

        # Step 2: ログインフォーム入力
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "email")))
        driver.find_element(By.ID, "email").send_keys(os.environ["ITANDI_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ITANDI_PASSWORD"])
        driver.find_element(By.XPATH, "//input[@type='submit' and @value='ログイン']").click()
        time.sleep(2)
        debug_save("02_after_login_submit")

        # Step 3: トップページへのリンクをクリック
        WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'トップページへ')]"))
        ).click()
        time.sleep(2)
        debug_save("03_after_click_top")

        # Step 4: itandiBBの管理画面へ遷移
        WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'itandibb.com/login')]"))
        ).click()
        WebDriverWait(driver, 15).until(EC.url_contains("/top"))
        debug_save("04_final_top")

        print("✅ ITANDI ログイン成功")

except Exception as e:
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    screenshot_path = f"screenshots/login_failed_{timestamp}.png"
    html_path = f"screenshots/login_failed_{timestamp}.html"
    try:
        driver.save_screenshot(screenshot_path)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print(f"❌ ログイン処理全体で失敗: {e}")
        print(f"→ スクリーンショット: {screenshot_path}")
        print(f"→ HTML保存済み: {html_path}")
    except Exception as ee:
        print(f"⚠ ログイン失敗時のスクショ保存も失敗: {ee}")
    driver.quit()
    exit()

# === 各物件URLをチェックしてステータス反映 ===
for row_num, row in enumerate(all_rows, start=2):
    url = row[URL_COL - 1].strip()
    if not is_valid_url(url):
        print(f"スキップ: Row {row_num} に不正なURLが含まれています: {url}")
        continue

    if "es-square.net" not in url and "itandibb.com" not in url:
        print(f"スキップ: Row {row_num} は対象外のURL → {url}")
        continue

    print(f"📄 チェック中: Row {row_num} → {url}")
    now_jst = datetime.datetime.now(ZoneInfo("Asia/Tokyo"))
    has_application = False

    try:
        driver.get(url)
        time.sleep(2)

        if "es-square.net" in url:
            application_elems = driver.find_elements(
                By.XPATH,
                "//span[contains(@class, 'MuiChip-label') and normalize-space()='申込あり']"
            )
            if application_elems:
                has_application = True
            else:
                error_elems = driver.find_elements(
                    By.XPATH,
                    "//div[contains(@class,'ErrorAnnounce-module_eds-error-announce__note') and contains(normalize-space(), 'エラーコード：404')]"
                )
                if error_elems:
                    has_application = True

        elif "itandibb.com" in url:
            status_elems = driver.find_elements(
                By.XPATH,
                "//div[contains(@class, 'Block Left')]"
            )
            has_open = any("募集中" in elem.text for elem in status_elems)
            has_application = not has_open

            # === 募集状況ページのスクリーンショット保存 ===
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            screenshot_path = f"screenshots/itandi_row_{row_num}_{timestamp}.png"
            try:
                driver.save_screenshot(screenshot_path)
                print(f"📸 スクリーンショット保存済み: {screenshot_path}")
            except Exception as ee:
                print(f"⚠ Row {row_num} → スクリーンショット保存失敗: {ee}")

        # === スプレッドシートに反映 ===
        if has_application:
            sheet.update_cell(row_num, STATUS_COL, "")
            sheet.update_cell(row_num, ENDED_COL, now_jst.strftime("%Y-%m-%d %H:%M"))
        else:
            sheet.update_cell(row_num, STATUS_COL, "募集中")
            if row[ENDED_COL - 1].strip():
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
            print(f"⚠ Row {row_num} → スクショ保存失敗: {ee}")
        print(f"❌ Error: Row {row_num}: {e}")
        print(f"→ スクリーンショット: {screenshot_path}")
        print(f"→ HTML保存済み: {html_path}")
        sheet.update_cell(row_num, STATUS_COL, "取得失敗")

driver.quit()

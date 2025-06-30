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

# === Chrome起動（1回でログイン維持） ===
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
driver = webdriver.Chrome(options=options)

try:
    # === 任意の物件URLでログインページにアクセス ===
    first_url = None
    all_rows = sheet.get_all_values()[1:]
    for row in all_rows:
        url = row[URL_COL - 1]
        if url and "https://rent.es-square.net/bukken/chintai/search/detail/" in url:
            first_url = url
            break

    if not first_url:
        print("対象物件URLが見つかりませんでした。")
        driver.quit()
        exit()

    driver.get(first_url)
    time.sleep(2)

    # === ログイン処理 ===
    login_btn = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'いい生活アカウントでログイン')]"))
    )
    login_btn.click()

    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.NAME, "username")))
    driver.find_element(By.NAME, "username").send_keys(os.environ["ES_EMAIL"])
    driver.find_element(By.NAME, "password").send_keys(os.environ["ES_PASSWORD"])
    driver.find_element(By.XPATH, "//button[@type='submit']").click()

    # === ログイン完了の判定 ===
    WebDriverWait(driver, 30).until(
        EC.visibility_of_element_located(
            (By.XPATH, "//*[contains(text(), '物件概要') or contains(text(), 'エラーコード：404')]")
        )
    )
    print("✅ ログイン成功")

except Exception as e:
    screenshot_path = "screenshots/login_failed.png"
    driver.save_screenshot(screenshot_path)
    print(f"❌ ログイン失敗: {e}")
    print(f"→ スクリーンショット保存済み: {screenshot_path}")
    driver.quit()
    exit()

# === 各物件を処理 ===
for row_num, row in enumerate(all_rows, start=2):
    url = row[URL_COL - 1]
    if not url or "https://rent.es-square.net/bukken/chintai/search/detail/" not in url:
        continue

    try:
        driver.get(url)
        time.sleep(2)

        has_application = False

        # 申込あり判定
        application_elems = driver.find_elements(
            By.XPATH,
            "//span[contains(@class, 'MuiChip-label') and normalize-space()='申込あり']"
        )
        if application_elems:
            has_application = True
        else:
            # エラー404判定
            error_elems = driver.find_elements(
                By.XPATH,
                "//div[contains(@class,'ErrorAnnounce-module_eds-error-announce__note') and contains(normalize-space(), 'エラーコード：404')]"
            )
            if error_elems:
                has_application = True

        # 結果をスプレッドシートに反映
        if has_application:
            sheet.update_cell(row_num, STATUS_COL, "")
            sheet.update_cell(row_num, ENDED_COL, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        else:
            sheet.update_cell(row_num, STATUS_COL, "募集中")
            sheet.update_cell(row_num, ENDED_COL, "")

    except Exception as e:
        screenshot_path = f"screenshots/row_{row_num}_error_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        driver.save_screenshot(screenshot_path)
        print(f"Error:  Row {row_num}: {e}")
        print(f"→ エラー時スクリーンショット保存済み: {screenshot_path}")
        sheet.update_cell(row_num, STATUS_COL, "取得失敗")

driver.quit()

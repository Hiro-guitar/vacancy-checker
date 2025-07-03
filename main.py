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

# === Chrome起動 ===
options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-blink-features=AutomationControlled')
driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(30)

# === 最初のログイン対象URLを取得 ===
first_url = None
all_rows = sheet.get_all_values()[1:]  # ヘッダーを除外
for row in all_rows:
    url = row[URL_COL - 1].strip()
    if url and "es-square.net" in url:
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

        print("✅ ログイン成功")

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

# === URLリストを事前にフィルタ（es-square.net のみ）===
target_rows = []
for i, row in enumerate(all_rows):
    url = row[URL_COL - 1].strip()
    if url and "es-square.net" in url:
        target_rows.append((i + 2, row))  # 2行目以降の行番号とデータ

# === 各物件URLをチェックしてステータス反映 ===
for row_num, row in target_rows:
    url = row[URL_COL - 1].strip()
    print(f"📄 チェック中: Row {row_num} → {url}")

    try:
        driver.get(url)
        time.sleep(2)
        has_application = False
        now_jst = datetime.datetime.now(ZoneInfo("Asia/Tokyo"))

        # === 募集状況確認（es-square.net）===
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

        # === シート更新 ===
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

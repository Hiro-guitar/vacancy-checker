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
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
driver = webdriver.Chrome(options=options)

# === 最初のログイン対象URLを取得 ===
first_url = None
all_rows = sheet.get_all_values()[1:]
for row in all_rows:
    url = row[URL_COL - 1]
    if url and ("es-square.net" in url or "itandibb.com" in url):
        first_url = url
        break

if not first_url:
    print("対象物件URLが見つかりませんでした。")
    driver.quit()
    exit()

# === ログイン処理 ===
try:
    driver.get(first_url)
    time.sleep(2)

    if "es-square.net" in first_url:
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

    elif "itandibb.com" in first_url:
        driver.get("https://itandibb.com/login")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "email")))

        driver.find_element(By.ID, "email").send_keys(os.environ["ITANDI_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ITANDI_PASSWORD"])
        driver.find_element(By.XPATH, "//input[@type='submit' and @value='ログイン']").click()

        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located(
                (By.XPATH, "//a[contains(@href, '/rent_rooms')]")
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
    if not url or not ("es-square.net" in url or "itandibb.com" in url):
        continue

    try:
        driver.get(url)
        time.sleep(2)
        has_application = False
        now_jst = datetime.datetime.now(ZoneInfo("Asia/Tokyo"))

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
            error_elems = driver.find_elements(
                By.XPATH,
                "//h3[contains(text(), '404 Page not found')]"
            )
            if error_elems:
                has_application = True
            else:
                badge_elem = driver.find_element(
                    By.XPATH,
                    "//span[contains(@class, 'MuiBadge-badge') and contains(@class, 'MuiBadge-colorPrimary')]"
                )
                badge_value = badge_elem.text.strip()
                if badge_value != "0":
                    has_application = True

        # 結果をスプレッドシートに反映
        if has_application:
            sheet.update_cell(row_num, STATUS_COL, "")
            if not row[ENDED_COL - 1].strip():
                sheet.update_cell(row_num, ENDED_COL, now_jst.strftime("%Y-%m-%d %H:%M"))
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

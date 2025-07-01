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
options.add_argument('--disable-blink-features=AutomationControlled')  # bot検知回避
driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(30)

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

    elif "itandibb.com" in first_url:
        driver.get("https://itandibb.com/login")

        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.ID, "email"))
        )
        driver.find_element(By.ID, "email").send_keys(os.environ["ITANDI_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["ITANDI_PASSWORD"])
        driver.find_element(By.XPATH, "//input[@type='submit' and @value='ログイン']").click()

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(), 'お気に入り') or contains(text(), '物件登録')]")
            )
        )

        print("✅ ログイン後URL:", driver.current_url)
        print("✅ ページタイトル:", driver.title)

        time.sleep(5)

        print("▶️ ログイン直後に物件ページへアクセステストします")
        driver.get(first_url)
        time.sleep(3)

        if "login" in driver.current_url or "ログイン" in driver.title:
            print("❌ ログイン後も物件ページでログイン画面にリダイレクトされました")
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            driver.save_screenshot(f"screenshots/login_redirect_{timestamp}.png")
            with open(f"screenshots/login_redirect_{timestamp}.html", "w", encoding='utf-8') as f:
                f.write(driver.page_source)
            driver.quit()
            exit()
        else:
            print("✅ ログインセッションが維持され、物件ページにアクセスできました")

except Exception as e:
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    screenshot_path = f"screenshots/login_failed_{timestamp}.png"
    html_path = f"screenshots/login_failed_{timestamp}.html"

    try:
        driver.save_screenshot(screenshot_path)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print(f"❌ ログイン失敗: {e}")
        print(f"→ スクリーンショット: {screenshot_path}")
        print(f"→ HTML保存済み: {html_path}")
    except Exception as ee:
        print(f"❌ ログイン失敗（スクショ取得も失敗）: {e}")
        print(f"⚠ HTML保存/スクショに失敗: {ee}")

    driver.quit()
    exit()

# === 各物件URLをチェックしてステータス反映 ===
for row_num, row in enumerate(all_rows, start=2):
    url = row[URL_COL - 1]
    if not url or not ("es-square.net" in url or "itandibb.com" in url):
        continue

    print(f"📄 チェック中: Row {row_num} → {url}")

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
                try:
                    badge_elems = driver.find_elements(
                        By.XPATH,
                        "//span[contains(@class, 'MuiBadge-badge') and contains(@class, 'MuiBadge-colorPrimary')]"
                    )
                    for badge in badge_elems:
                        value = badge.text.strip()
                        if value.isdigit() and int(value) > 0:
                            has_application = True
                            print(f"📌 申込バッジ発見: {value}")
                            break
                except Exception as e:
                    print(f"⚠️ Badge 要素の確認中にエラー: {e}")

        if has_application:
            sheet.update_cell(row_num, STATUS_COL, "")
            if not row[ENDED_COL - 1].strip():
                sheet.update_cell(row_num, ENDED_COL, now_jst.strftime("%Y-%m-%d %H:%M"))
        else:
            sheet.update_cell(row_num, STATUS_COL, "募集中")
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

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
gspread_raw = os.environ["GSPREAD_JSON"]
if gspread_raw.strip().startswith('{'):
    json_str = gspread_raw
else:
    json_str = base64.b64decode(gspread_raw).decode('utf-8')

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
#options.add_argument('--headless=new')  # 必要なら有効化
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-blink-features=AutomationControlled')
options.add_argument('--window-size=1280,1024')
driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(30)

# === 最初のログイン対象URLを取得 ===
first_url = None
all_rows = sheet.get_all_values()[1:]  # ヘッダー除く
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
            screenshot_path = f'screenshots/itandi_debug_{step}_{ts}.png'
            html_path = f'screenshots/itandi_debug_{step}_{ts}.html'
            try:
                driver.save_screenshot(screenshot_path)
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
                print(f"📸 {step} - URL: {driver.current_url}")
            except Exception as ee:
                print(f"⚠ {step} - スクショ保存失敗: {ee}")

        print(f"🔐 STEP 1: {first_url} にアクセス")
        driver.get(first_url)
        debug_save("01_first_url_page")

        print("🔐 STEP 2: メール・パスワード入力（visible要素に限定）")
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="email"]'))
        )

        # JavaScriptでvisibleな要素に値を入力
        driver.execute_script("""
        const emailInput = Array.from(document.querySelectorAll('input[name="email"]')).find(el => el.offsetParent !== null);
        const passwordInput = Array.from(document.querySelectorAll('input[name="password"]')).find(el => el.offsetParent !== null);

        if (emailInput && passwordInput) {
            emailInput.focus();
            emailInput.value = arguments[0];
            emailInput.dispatchEvent(new Event('input', { bubbles: true }));

            passwordInput.focus();
            passwordInput.value = arguments[1];
            passwordInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
        """, os.environ["ITANDI_EMAIL"], os.environ["ITANDI_PASSWORD"])

        time.sleep(1)

        print("🔐 STEP 3: ログインボタンクリック")
        login_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[type="submit"][value="ログイン"]'))
        )
        login_btn.click()
        time.sleep(3)
        debug_save("02_after_login_submit")

        print("🔐 STEP 4: ログイン成功判定")
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@class, 'DetailTitleLabel')]//span[text()='設備・詳細']")
                )
            )
            print("✅ ITANDI ログイン成功")
        except:
            print("❌ ログイン成功判定に失敗しました")


except Exception as e:
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    screenshot_path = f"screenshots/login_failed_{timestamp}.png"
    html_path = f"screenshots/login_failed_{timestamp}.html"
    try:
        driver.save_screenshot(screenshot_path)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print(f"❌ ログイン失敗: {e}")
        print(f"→ スクショ: {screenshot_path}")
        print(f"→ HTML: {html_path}")
    except Exception as ee:
        print(f"⚠ ログイン時のスクショ保存も失敗: {ee}")
    driver.quit()
    exit()

# === 各物件URLのステータス確認 ===
for row_num, row in enumerate(all_rows, start=2):
    url = row[URL_COL - 1].strip()
    if not is_valid_url(url):
        print(f"スキップ: Row {row_num} → 不正なURL: {url}")
        continue
    if "es-square.net" not in url and "itandibb.com" not in url:
        print(f"スキップ: Row {row_num} → 対象外URL: {url}")
        continue

    print(f"📄 チェック中: Row {row_num} → {url}")
    now_jst = datetime.datetime.now(ZoneInfo("Asia/Tokyo"))
    has_application = False

    try:
        driver.get(url)
        time.sleep(2)

        if "es-square.net" in url:
            application_elems = driver.find_elements(
                By.XPATH, "//span[contains(@class, 'MuiChip-label') and normalize-space()='申込あり']"
            )
            if application_elems:
                has_application = True
            else:
                error_elems = driver.find_elements(
                    By.XPATH, "//div[contains(@class,'ErrorAnnounce') and contains(text(), 'エラーコード：404')]"
                )
                if error_elems:
                    has_application = True

        elif "itandibb.com" in url:
            status_elems = driver.find_elements(By.XPATH, "//div[contains(@class, 'Block Left')]")
            has_open = any("募集中" in elem.text for elem in status_elems)
            has_application = not has_open

            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            screenshot_path = f"screenshots/itandi_row_{row_num}_{timestamp}.png"
            driver.save_screenshot(screenshot_path)
            print(f"📸 Row {row_num} スクリーンショット保存: {screenshot_path}")

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
        print(f"❌ Row {row_num} → エラー: {e}")
        print(f"→ スクショ: {screenshot_path}")
        print(f"→ HTML: {html_path}")
        sheet.update_cell(row_num, STATUS_COL, "取得失敗")

driver.quit()

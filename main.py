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

def create_driver():
    options = Options()
    options.add_argument('--headless=new')  # 必要に応じて
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1280,1024')
    return webdriver.Chrome(options=options)

# === スクリーンショット保存先フォルダ ===
os.makedirs("screenshots", exist_ok=True)

# === Google Sheets 認証 ===
gspread_raw = os.environ["GSPREAD_JSON"]
json_str = gspread_raw if gspread_raw.strip().startswith('{') else base64.b64decode(gspread_raw).decode('utf-8')

cred = ServiceAccountCredentials.from_json_keyfile_dict(
    json.loads(json_str),
    ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
)
client = gspread.authorize(cred)
sheet = client.open_by_key(os.environ['SPREADSHEET_ID']).worksheet("シート1")

URL_COL = 13   # M列
STATUS_COL = 9 # I列
ENDED_COL = 11 # K列

all_rows = sheet.get_all_values()[1:]

# === ドライバの初期化 ===
es_driver = create_driver()
itandi_driver = create_driver()

# === ログイン処理 ===
def login_es(driver):
    print("🔐 ESログイン処理")
    for row in all_rows:
        url = row[URL_COL - 1].strip()
        if "es-square.net" in url:
            driver.get(url)
            try:
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'いい生活アカウントでログイン')]"))).click()
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "username")))
                driver.find_element(By.NAME, "username").send_keys(os.environ["ES_EMAIL"])
                driver.find_element(By.NAME, "password").send_keys(os.environ["ES_PASSWORD"])
                driver.find_element(By.XPATH, "//button[@type='submit']").click()
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), '物件概要')]")))
                print("✅ ESログイン成功")
                return True
            except Exception as e:
                print(f"❌ ESログイン失敗: {e}")
                return False
    return False

def login_itandi(driver):
    print("🔐 ITANDIログイン処理")
    for row in all_rows:
        url = row[URL_COL - 1].strip()
        if "itandibb.com" in url:
            driver.get(url)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="email"]'))
                )
                driver.execute_script("""
                const emailInput = Array.from(document.querySelectorAll('input[name="email"]')).find(el => el.offsetParent !== null);
                const passwordInput = Array.from(document.querySelectorAll('input[name="password"]')).find(el => el.offsetParent !== null);
                function triggerInputEvents(element, value) {
                    const lastValue = element.value;
                    element.focus();
                    element.value = value;
                    const inputEvent = new Event('input', { bubbles: true });
                    const changeEvent = new Event('change', { bubbles: true });
                    const tracker = element._valueTracker;
                    if (tracker) tracker.setValue(lastValue);
                    element.dispatchEvent(inputEvent);
                    element.dispatchEvent(changeEvent);
                }
                if (emailInput && passwordInput) {
                    triggerInputEvents(emailInput, arguments[0]);
                    triggerInputEvents(passwordInput, arguments[1]);
                }
                """, os.environ["ITANDI_EMAIL"], os.environ["ITANDI_PASSWORD"])
                itandi_login_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[type="submit"][value="ログイン"]'))
                )
                itandi_login_btn.click()
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'DetailTitleLabel')]//span[text()='設備・詳細']"))
                )
                print("✅ ITANDIログイン成功")
                return True
            except Exception as e:
                print(f"❌ ITANDIログイン失敗: {e}")
                return False
    return False

es_logged_in = login_es(es_driver)
itandi_logged_in = login_itandi(itandi_driver)

# === 各物件URLのステータス確認 ===
for row_num, row in enumerate(all_rows, start=2):
    url = row[URL_COL - 1].strip()
    if not is_valid_url(url):
        print(f"⚠ Row {row_num} → 無効なURL: {url}")
        continue

    # ✅ itandi / es-square 以外は無視
    if not ("es-square.net" in url or "itandibb.com" in url):
        print(f"⏭️ Row {row_num} → 対象外URLスキップ: {url}")
        continue

    now_jst = datetime.datetime.now(ZoneInfo("Asia/Tokyo"))
    has_application = False

    try:
        if "es-square.net" in url and es_logged_in:
            es_driver.get(url)
            time.sleep(2)
            application_elems = es_driver.find_elements(
                By.XPATH, "//span[contains(@class, 'MuiChip-label') and normalize-space()='申込あり']"
            )
            if application_elems:
                has_application = True
            else:
                error_elems = es_driver.find_elements(
                    By.XPATH, "//div[contains(@class,'ErrorAnnounce') and contains(text(), 'エラーコード：404')]"
                )
                if error_elems:
                    has_application = True

        elif "itandibb.com" in url and itandi_logged_in:
            itandi_driver.get(url)
            time.sleep(2)
            status_elems = itandi_driver.find_elements(By.XPATH, "//div[contains(@class, 'Block Left')]")
            has_open = any("募集中" in elem.text for elem in status_elems)
            has_application = not has_open

            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            screenshot_path = f"screenshots/itandi_row_{row_num}_{timestamp}.png"
            itandi_driver.save_screenshot(screenshot_path)
            print(f"📸 Row {row_num} スクリーンショット保存: {screenshot_path}")

        if has_application:
            sheet.update_cell(row_num, STATUS_COL, "")
            #current_date = sheet.cell(row_num, ENDED_COL).value
        #if not current_date or current_date.strip() == "":
            # K列が空なら更新する
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
            driver = es_driver if "es-square.net" in url else itandi_driver
            driver.save_screenshot(screenshot_path)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
        except Exception as ee:
            print(f"⚠ Row {row_num} スクショ保存失敗: {ee}")
        print(f"❌ Row {row_num} エラー: {e}")
        print(f"→ スクショ: {screenshot_path}")

# === 終了処理 ===
es_driver.quit()
itandi_driver.quit()
print("✅ 全処理完了")

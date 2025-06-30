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

# === Google Sheets 認証 ===
json_str = base64.b64decode(os.environ['GSPREAD_JSON']).decode('utf-8')
cred = ServiceAccountCredentials.from_json_keyfile_dict(
    json.loads(json_str),
    ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
)
client = gspread.authorize(cred)
sheet = client.open_by_key(os.environ['SPREADSHEET_ID']).worksheet("シート1")

# === 対象列インデックス ===
URL_COL = 13   # M列（1始まり）
STATUS_COL = 9 # I列
ENDED_COL = 11 # K列

# === スプレッドシートからデータ取得 ===
data = sheet.get_all_values()
for row_num, row in enumerate(data[1:], start=2):
    url = row[URL_COL - 1]
    if not url:
        continue

    # いい生活スクエアの物件URLでなければスキップ
    if "https://rent.es-square.net/bukken/chintai/search/detail/" not in url:
        continue

    # === Chromeヘッドレス起動 ===
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        time.sleep(2)

        login_btn = driver.find_element(By.XPATH, "//button[contains(., 'いい生活アカウントでログイン')]")
        login_btn.click()
        time.sleep(2)

        driver.find_element(By.NAME, "username").send_keys(os.environ["ES_EMAIL"])
        driver.find_element(By.NAME, "password").send_keys(os.environ["ES_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(5)

        html = driver.page_source

        if "申込あり" in html:
            # 申込あり → I列を空白にし、K列に終了日時を入れる
            sheet.update_cell(row_num, STATUS_COL, "")
            sheet.update_cell(row_num, ENDED_COL, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        else:
            # 申込なし → 募集中、終了日は空白に
            sheet.update_cell(row_num, STATUS_COL, "募集中")
            sheet.update_cell(row_num, ENDED_COL, "")

    except Exception as e:
        print(f"[Error] Row {row_num}: {e}")
        sheet.update_cell(row_num, STATUS_COL, "取得失敗")
    finally:
        driver.quit()

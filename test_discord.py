import os
import requests

def send_discord_message(message):
    # GitHub SecretsからURLを読み込む
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    
    if not webhook_url:
        print("❌ エラー: DISCORD_WEBHOOK_URL が設定されていません。")
        return

    data = {"content": message}
    response = requests.post(webhook_url, json=data)
    
    if response.status_code == 204:
        print("✅ Discordへの送信に成功しました！サーバーを確認してください。")
    else:
        print(f"❌ 送信失敗: ステータスコード {response.status_code}")

if __name__ == "__main__":
    send_discord_message("🤖 物出し自動化システム：Discord通知テスト成功です！")

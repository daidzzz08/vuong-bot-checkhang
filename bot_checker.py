import os
import logging
import requests
from typing import Dict, Any, List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_URL = "https://api.shopgmail9999.com/api/BuyGmail/GetListGmailProduct?apikey=a2665bb2cd0a47a09704cd270d37108f"
TARGET_IDS = {4, 148}

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def fetch_product_data() -> Optional[List[Dict[str, Any]]]:
    """Fetch and parse data from the target API."""
    try:
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("success"):
            return data.get("listproduct", [])
        logging.error("API trả về success=False.")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Lỗi mạng khi gọi API: {e}")
        return None
    except ValueError as e:
        logging.error(f"Lỗi phân tích JSON: {e}")
        return None

def send_telegram_message(message: str) -> None:
    """Send alert message to Telegram Bot with Inline Keyboard."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Thiếu TELEGRAM_TOKEN hoặc TELEGRAM_CHAT_ID.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # Cấu hình Payload chứa Nút bấm (Inline Keyboard)
    payload: Dict[str, Any] = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "🛒 Truy cập Shop ngay", "url": "https://shopgmail9999.com/"}
                ]
            ]
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("Đã gửi thông báo Telegram thành công kèm nút bấm.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Lỗi gửi tin nhắn Telegram: {e}")

def main() -> None:
    logging.info("Bắt đầu tiến trình kiểm tra sản phẩm...")
    products = fetch_product_data()
    
    if not products:
        return

    available_items: List[str] = []
    
    for item in products:
        item_id = item.get("id")
        if item_id in TARGET_IDS:
            quantity = item.get("quantity", 0)
            name = item.get("name", "Unknown")
            logging.info(f"Check ID {item_id}: Số lượng = {quantity}")
            
            if quantity > 0:
                price = item.get("price", 0)
                available_items.append(
                    f"✅ *{name}*\n- ID: `{item_id}`\n- Giá: {price} VND\n- Số lượng: *{quantity}*"
                )

    if available_items:
        message = "🔥 *HÀNG ĐÃ VỀ!* 🔥\n\n" + "\n\n".join(available_items)
        send_telegram_message(message)

if __name__ == "__main__":
    main()
import os
import sys
import logging
import httpx
from typing import Dict, Any, List, Optional
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configurations
API_URL = "https://api.shopgmail9999.com/api/BuyGmail/GetListGmailProduct?apikey=a2665bb2cd0a47a09704cd270d37108f"
TARGET_IDS = {4, 148}
MAX_RUN_TIME = 2 * 3600 + 50 * 60  # 2 hours 50 minutes in seconds

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


async def fetch_product_data() -> Optional[List[Dict[str, Any]]]:
    """
    Fetch and parse data from the target API asynchronously.

    Returns:
        Optional[List[Dict[str, Any]]]: A list of product dictionaries if successful, None otherwise.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(API_URL)
            response.raise_for_status()
            data = response.json()

            if data.get("success"):
                return data.get("listproduct", [])
            else:
                logger.error("API trả về success=False. Cần kiểm tra lại API Key hoặc Endpoint.")
                return None

    except httpx.RequestError as e:
        logger.error(f"Lỗi mạng/kết nối khi gọi API: {e}")
        return None
    except ValueError as e:
        logger.error(f"Lỗi phân tích cú pháp JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Lỗi không xác định khi gọi API: {e}")
        return None


async def send_telegram_alert(context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    """Helper function to safely send messages with error handling."""
    if not TELEGRAM_CHAT_ID:
        return
    try:
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        logger.info("Đã gửi thông báo Telegram thành công.")
    except Exception as e:
        logger.error(f"Lỗi gửi tin nhắn Telegram: {e}")


async def check_api_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Background job to check API periodically.
    Implements state management to prevent spam.
    """
    logger.info("Đang thực thi chu kỳ kiểm tra API...")
    products = await fetch_product_data()

    if not products:
        logger.warning("Không lấy được dữ liệu sản phẩm. Bỏ qua chu kỳ này.")
        return

    # Khởi tạo bộ nhớ tạm để lưu trạng thái nếu chưa có
    if "item_states" not in context.bot_data:
        context.bot_data["item_states"] = {}
        
    item_states: Dict[int, int] = context.bot_data["item_states"]

    in_stock_alerts: List[str] = []
    out_of_stock_alerts: List[str] = []

    for item in products:
        item_id = int(item.get("id", 0))
        if item_id in TARGET_IDS:
            current_qty = int(item.get("quantity", 0))
            name = item.get("name", "Unknown")
            price = item.get("price", 0)

            # Lấy trạng thái cũ (mặc định coi như ban đầu là 0)
            prev_qty = item_states.get(item_id, 0)

            # Logic phát hiện thay đổi (State Transition)
            if current_qty > 0 and prev_qty == 0:
                # Trạng thái: Vừa có hàng
                in_stock_alerts.append(
                    f"✅ *{name}*\n- ID: `{item_id}`\n- Giá: {price} VND\n- Số lượng: *{current_qty}*"
                )
            elif current_qty == 0 and prev_qty > 0:
                # Trạng thái: Vừa hết hàng
                out_of_stock_alerts.append(
                    f"❌ *{name}*\n- ID: `{item_id}`\n- Trạng thái: *Đã hết hàng*"
                )

            # Cập nhật trạng thái mới nhất vào bộ nhớ
            item_states[item_id] = current_qty

    # Gửi tin nhắn gom nhóm nếu có sự thay đổi
    if in_stock_alerts:
        msg = "🔥 *HÀNG ĐÃ VỀ!* 🔥\n\n" + "\n\n".join(in_stock_alerts)
        await send_telegram_alert(context, msg)

    if out_of_stock_alerts:
        msg = "⚠️ *THÔNG BÁO HẾT HÀNG* ⚠️\n\n" + "\n\n".join(out_of_stock_alerts)
        await send_telegram_alert(context, msg)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /start command."""
    try:
        await update.message.reply_text(
            "👋 Bot đang chạy (Anti-Spam Mode).\n"
            "Chỉ thông báo khi hàng TỪ KHÔNG -> CÓ và TỪ CÓ -> KHÔNG."
        )
    except Exception as e:
        logger.error(f"Lỗi trong start_command: {e}")


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /check command to manually trigger API check and see current state."""
    try:
        await update.message.reply_text("⏳ Đang kiểm tra API thủ công...")
        products = await fetch_product_data()
        
        if not products:
            await update.message.reply_text("❌ Lỗi kết nối API. Vui lòng xem log server.")
            return

        status_msgs = []
        for item in products:
            if item.get("id") in TARGET_IDS:
                status_msgs.append(
                    f"- {item.get('name')}: *{item.get('quantity')} cái*"
                )
                
        reply_text = "📊 *Trạng thái hiện tại:*\n" + "\n".join(status_msgs)
        await update.message.reply_text(reply_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Lỗi trong check_command: {e}")


async def shutdown_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job triggered after MAX_RUN_TIME to safely terminate the polling.
    """
    logger.info("Đã đạt giới hạn thời gian chạy. Tiến hành Graceful Shutdown...")
    if context.application:
        context.application.stop_running()


def main() -> None:
    """Main function to initialize and run the bot."""
    if not TELEGRAM_TOKEN:
        logger.critical("Thiếu TELEGRAM_TOKEN trong biến môi trường. Đang thoát.")
        sys.exit(1)

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("check", check_command))

    job_queue = application.job_queue
    if not job_queue:
        logger.critical("Không tìm thấy JobQueue. Cần chạy: pip install 'python-telegram-bot[job-queue]'")
        sys.exit(1)

    job_queue.run_repeating(check_api_job, interval=60, first=10)
    job_queue.run_once(shutdown_job, when=MAX_RUN_TIME)

    logger.info("Khởi động Telegram Bot (Anti-Spam Mode)...")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Bot được tắt thủ công (KeyboardInterrupt).")
    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng trong quá trình polling: {e}")
    finally:
        logger.info("Tiến trình đã kết thúc an toàn.")


if __name__ == "__main__":
    main()
"""알림 전송 모듈 — 텔레그램 / 이메일 (SMTP)"""
import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import httpx
import db

logger = logging.getLogger(__name__)


def get_config() -> dict:
    return {
        "telegram_token": db.get_setting("notify_telegram_token") or "",
        "telegram_chat_id": db.get_setting("notify_telegram_chat_id") or "",
        "email_host": db.get_setting("notify_email_host") or "",
        "email_port": int(db.get_setting("notify_email_port") or 587),
        "email_user": db.get_setting("notify_email_user") or "",
        "email_pass": db.get_setting("notify_email_pass") or "",
        "email_to": db.get_setting("notify_email_to") or "",
    }


async def send_telegram(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        })
        resp.raise_for_status()


def send_email(host: str, port: int, user: str, password: str, to: str, subject: str, body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.login(user, password)
        server.sendmail(user, to, msg.as_string())


async def notify(board_name: str, output: str, link: str = None):
    """설정된 채널로 알림 전송."""
    cfg = get_config()
    text = f"*[claude-local]* {board_name}\n\n{output[:3000]}"
    if link:
        text = f"{text}\n🔗 http://localhost:8100{link}"

    sent = False

    if cfg["telegram_token"] and cfg["telegram_chat_id"]:
        try:
            await send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], text)
            logger.info("[notifier] 텔레그램 전송 완료")
            sent = True
        except Exception as e:
            logger.error("[notifier] 텔레그램 실패: %s", e)

    if cfg["email_host"] and cfg["email_user"] and cfg["email_to"]:
        try:
            send_email(
                cfg["email_host"], cfg["email_port"],
                cfg["email_user"], cfg["email_pass"],
                cfg["email_to"],
                subject=f"[claude-local] {board_name}",
                body=output,
            )
            logger.info("[notifier] 이메일 전송 완료")
            sent = True
        except Exception as e:
            logger.error("[notifier] 이메일 실패: %s", e)

    return sent


async def test_telegram(token: str, chat_id: str) -> bool:
    try:
        await send_telegram(token, chat_id, "✅ claude-local 텔레그램 연결 테스트 성공!")
        return True
    except Exception as e:
        logger.error("[notifier] 텔레그램 테스트 실패: %s", e)
        return False

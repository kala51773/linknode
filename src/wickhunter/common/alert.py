import os
import aiohttp
import logging
from typing import Any

from wickhunter.common.logger import setup_logger

logger = setup_logger("wickhunter.alert")

class AlertSender:
    """Webhook-based emergency responder."""

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url or os.getenv("WICKHUNTER_WEBHOOK_URL")

    async def send_emergency_alert(self, title: str, description: str, fields: dict[str, Any] | None = None) -> bool:
        if not self.webhook_url:
            logger.warning(f"No webhook configured. Alert suppressed: [{title}] {description}")
            return False

        payload = {
            "content": f"🚨 **{title}**\n{description}\n"
        }
        
        if fields:
            payload["content"] += "\n".join(f"- **{k}**: {v}" for k, v in fields.items())
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    resp.raise_for_status()
                    logger.info(f"Fired an emergency alert: {title}")
                    return True
        except Exception as e:
            logger.error(f"Failed to post to webhook {self.webhook_url}: {e}")
            return False
            
        return False

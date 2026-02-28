import os
import re
from typing import Any

from twilio.rest import Client


E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def is_valid_e164(phone: str) -> bool:
    return bool(E164_RE.match(phone))


def send_sms(to_phone: str, message: str) -> dict[str, Any]:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_phone = os.getenv("TWILIO_FROM_PHONE", "").strip()
    messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID", "").strip()

    if not account_sid or not auth_token:
        return {
            "sent": False,
            "error": "SMS provider not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.",
        }
    if not messaging_service_sid and not from_phone:
        return {
            "sent": False,
            "error": "Set either TWILIO_MESSAGING_SERVICE_SID or TWILIO_FROM_PHONE.",
        }
    if from_phone and not is_valid_e164(from_phone):
        return {
            "sent": False,
            "error": "TWILIO_FROM_PHONE must be in E.164 format, e.g. +19803712808.",
        }

    try:
        client = Client(account_sid, auth_token)
        kwargs: dict[str, Any] = {"to": to_phone, "body": message}
        if messaging_service_sid:
            kwargs["messaging_service_sid"] = messaging_service_sid
        else:
            kwargs["from_"] = from_phone
        msg = client.messages.create(**kwargs)
        return {"sent": True, "sid": msg.sid}
    except Exception as exc:
        return {"sent": False, "error": str(exc)}

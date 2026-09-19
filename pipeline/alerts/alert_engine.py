"""Alert thresholds, routing, duplicate suppression, and pluggable email delivery."""

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)
ROUTING_PATH = Path(__file__).with_name("routing.json")


def should_alert(classification, confidence, priority, frp_spike=False):
    threshold = float(os.environ.get("ALERT_CONFIDENCE_THRESHOLD", "0.75"))
    return bool(frp_spike) or (classification == "industrial_fire" and priority == "high" and float(confidence) >= threshold)


def should_alert_for_risk(risk_score):
    return float(risk_score) >= float(os.environ.get("ALERT_RISK_THRESHOLD", "80"))


def resolve_route(data):
    routing = json.loads(ROUTING_PATH.read_text())
    for route in routing["routes"]:
        if route["classification"] == data.get("classification", "risk_warning") and route["priority"] == data.get("priority", "high"):
            return route["authority"], os.environ.get(route["contact_env_var"], "")
    return routing["default_fallback_authority"], os.environ.get("ALERT_EMAIL_TO_MONITORING_DESK", "")


def _record(supabase_client, payload):
    if not supabase_client:
        return
    try:
        supabase_client.table("alerts").insert(payload).execute()
    except Exception:
        logger.exception("Could not record alert status")


def _in_cooldown(supabase_client, location_id, alert_type):
    if not supabase_client:
        return False
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=int(os.environ.get("ALERT_COOLDOWN_HOURS", "24")))).isoformat()
        result = supabase_client.table("alerts").select("id").eq("location_id", location_id).eq("alert_type", alert_type).gte("sent_at", cutoff).limit(1).execute()
        return bool(result.data)
    except Exception:
        logger.exception("Could not check alert cooldown; allowing delivery")
        return False


def send_alert(hotspot_or_risk_data, routed_to=None, supabase_client=None):
    """Route and deliver an alert, recording dry runs and cooldown suppressions."""
    data = dict(hotspot_or_risk_data)
    alert_type = data.get("classification", "risk_warning")
    if data.get("location_id"):
        location_id = str(data["location_id"])
    else:
        location_id = f"{float(data.get('lat', 0)):.3f},{float(data.get('lon', 0)):.3f}"
    authority, recipient = resolve_route(data)
    routed_to = routed_to or authority
    base = {"hotspot_id": data.get("id"), "location_id": location_id, "alert_type": alert_type, "routed_to": routed_to, "sent_at": datetime.now(timezone.utc).isoformat()}
    if _in_cooldown(supabase_client, location_id, alert_type):
        logger.info("Alert skipped for %s: cooldown active", location_id)
        _record(supabase_client, {**base, "status": "skipped_cooldown"})
        return "skipped_cooldown"
    provider, api_key, sender = (os.environ.get("ALERT_EMAIL_PROVIDER", ""), os.environ.get("ALERT_EMAIL_API_KEY", ""), os.environ.get("ALERT_EMAIL_FROM", ""))
    if not (provider and api_key and sender and recipient):
        logger.warning("[DRY RUN] alert to %s (%s): %s", routed_to, recipient or "no email configured", data)
        _record(supabase_client, {**base, "status": "dry_run"})
        return "dry_run"
    try:
        if provider.lower() != "smtp":
            raise ValueError("Only the SMTP provider is currently configured; use dry-run or SMTP")
        message = EmailMessage()
        message["Subject"] = f"Thermoscope alert: {alert_type}"
        message["From"], message["To"] = sender, recipient
        message.set_content(json.dumps(data, indent=2, default=str))
        with smtplib.SMTP(os.environ["ALERT_SMTP_HOST"], int(os.environ.get("ALERT_SMTP_PORT", "587"))) as smtp:
            smtp.starttls()
            smtp.login(sender, api_key)
            smtp.send_message(message)
        _record(supabase_client, {**base, "status": "sent"})
        return "sent"
    except Exception:
        logger.exception("Alert delivery failed")
        _record(supabase_client, {**base, "status": "failed"})
        return "failed"

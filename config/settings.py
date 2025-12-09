from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class BillingApiSettings:
    credential_id: str
    credential_secret: str


@dataclass
class MongoSettings:
    uri: str
    db_name: str


@dataclass
class ObjectStorageSettings:
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str


@dataclass
class AlertSettings:
    slack_webhook_url: Optional[str] = None


@dataclass
class Settings:
    billing_api: BillingApiSettings
    mongo: MongoSettings
    object_storage: ObjectStorageSettings
    alert: AlertSettings


def load_settings(path: str | Path) -> Settings:
    """
    Load configuration from a YAML file and return a Settings object.
    """
    cfg_path = Path(path)
    with cfg_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    billing = raw.get("billingApi", {})
    mongo = raw.get("mongo", {})
    obj = raw.get("objectStorage", {})
    alert = raw.get("alert", {})

    return Settings(
        billing_api=BillingApiSettings(
            credential_id=billing.get("credentialId", ""),
            credential_secret=billing.get("credentialSecret", ""),
        ),
        mongo=MongoSettings(
            uri=mongo.get("uri", ""),
            db_name=mongo.get("dbName", "billing"),
        ),
        object_storage=ObjectStorageSettings(
            endpoint=obj.get("endpoint", ""),
            bucket=obj.get("bucket", ""),
            access_key=obj.get("accessKey", ""),
            secret_key=obj.get("secretKey", ""),
        ),
        alert=AlertSettings(
            slack_webhook_url=alert.get("slackWebhookUrl"),
        ),
    )



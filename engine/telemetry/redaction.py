from __future__ import annotations

SECRET_KEYS = {"authorization", "api_key", "apikey", "token", "access_token", "secret"}


def redact_secrets(value, secret_values: tuple[str, ...] = ()):
    # 递归复制容器并替换敏感键和值，避免修改调用方持有的数据。
    secrets = tuple(secret for secret in secret_values if secret)
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).lower() in SECRET_KEYS
            else redact_secrets(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item, secrets) for item in value)
    if isinstance(value, str):
        result = value
        for secret in secrets:
            result = result.replace(secret, "[REDACTED]")
        return result
    return value

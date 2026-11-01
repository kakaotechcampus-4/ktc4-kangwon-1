"""Resend REST API로 메일을 보냅니다. SDK 없이 httpx만 씁니다."""

from __future__ import annotations

from html import escape

import httpx

from app.config import MailSettings

RESEND_URL = "https://api.resend.com/emails"

VERIFY_SUBJECT = "[채움] 이메일 주소를 확인해 주세요"
RESET_SUBJECT = "[채움] 비밀번호 재설정 안내"


class MailError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


def _body(title: str, lead: str, action: str, link: str, note: str) -> str:
    # 메일 클라이언트는 외부 CSS를 못 읽어 인라인 스타일만 씁니다.
    safe = escape(link, quote=True)
    return (
        '<div style="font-family:system-ui,-apple-system,sans-serif;'
        'line-height:1.6;color:#111827;max-width:560px">'
        f'<h1 style="font-size:20px;margin:0 0 16px">{escape(title)}</h1>'
        f'<p style="margin:0 0 20px;color:#4B5563">{escape(lead)}</p>'
        f'<p style="margin:0 0 24px"><a href="{safe}" '
        'style="display:inline-block;background:#004F54;color:#fff;text-decoration:none;'
        f'padding:12px 24px;border-radius:8px">{escape(action)}</a></p>'
        f'<p style="margin:0 0 8px;color:#6B7280;font-size:13px">{escape(note)}</p>'
        '<p style="margin:0;color:#9CA3AF;font-size:12px;word-break:break-all">'
        f"버튼이 눌리지 않으면 이 주소를 붙여 넣으세요: {safe}</p></div>"
    )


def verification_mail(link: str) -> tuple[str, str]:
    return VERIFY_SUBJECT, _body(
        "이메일 주소를 확인해 주세요",
        "아래 버튼을 누르면 가입이 끝나고 공실 분석을 시작할 수 있습니다.",
        "이메일 확인하기",
        link,
        "이 링크는 24시간 뒤 만료됩니다. 본인이 가입한 적이 없다면 이 메일을 무시하세요.",
    )


def reset_mail(link: str) -> tuple[str, str]:
    return RESET_SUBJECT, _body(
        "비밀번호를 재설정하세요",
        "아래 버튼을 누르면 새 비밀번호를 정할 수 있습니다.",
        "비밀번호 재설정하기",
        link,
        "이 링크는 30분 뒤 만료됩니다. 본인이 요청하지 않았다면 이 메일을 무시하세요. "
        "비밀번호는 그대로 유지됩니다.",
    )


async def send_mail(
    to: str,
    subject: str,
    html: str,
    settings: MailSettings,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """실패하면 MailError를 올립니다. 가입 자체를 되돌리지는 않습니다."""
    if not (settings.api_key or "").strip() or not (settings.sender or "").strip():
        raise MailError("MAIL_CONFIG_ERROR", "RESEND_API_KEY와 MAIL_FROM을 확인하세요.")
    if client is None:
        async with httpx.AsyncClient(timeout=settings.timeout) as owned:
            return await send_mail(to, subject, html, settings, client=owned)
    try:
        response = await client.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {settings.api_key.strip()}"},  # type: ignore[union-attr]
            json={"from": settings.sender, "to": [to], "subject": subject, "html": html},
            timeout=settings.timeout,
        )
    except httpx.HTTPError as exc:
        raise MailError("MAIL_UNAVAILABLE", "메일 서비스에 연결하지 못했습니다.") from exc
    if response.status_code >= 400:
        # 본문에 수신자 주소가 섞여 들어가지 않게 상태 코드만 남깁니다.
        raise MailError(
            "MAIL_REJECTED", f"메일 서비스가 거절했습니다(HTTP {response.status_code})."
        )

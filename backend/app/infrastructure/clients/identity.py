from app.infrastructure.clients import kakao_oauth, mailer


class KakaoResendIdentity:
    @staticmethod
    def authorize_url(settings, *, state):
        return kakao_oauth.authorize_url(settings, state=state)

    @staticmethod
    async def exchange_token(code, settings, *, client=None):
        return await kakao_oauth.exchange_token(code, settings, client=client)

    @staticmethod
    async def fetch_profile(access_token, settings, *, client=None):
        return await kakao_oauth.fetch_profile(access_token, settings, client=client)

    @staticmethod
    def verification_mail(link):
        return mailer.verification_mail(link)

    @staticmethod
    def reset_mail(link):
        return mailer.reset_mail(link)

    @staticmethod
    async def send_mail(to, subject, html, settings, *, client=None):
        return await mailer.send_mail(to, subject, html, settings, client=client)

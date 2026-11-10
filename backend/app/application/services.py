from pathlib import Path

from app.application import auth as auth_cases
from app.application import requests


class RequestService:
    def __init__(self, db_path, *, recording_dir=None, measurement=False):
        self._db_path = db_path
        self._recording_dir = recording_dir
        self._measurement = measurement

    def create(self, request_id, address, *, radius_m, user_id):
        return requests.create(
            request_id, address, radius_m=radius_m, user_id=user_id, db_path=self._db_path
        )

    def visible_to(self, request_id, user):
        return requests.visible_to(request_id, user, db_path=self._db_path)

    def detail(self, request_id):
        return requests.detail(request_id, db_path=self._db_path)

    def facts(self, request_id):
        return requests.facts(request_id, db_path=self._db_path)

    def answer_gate(self, request_id):
        return requests.answer_gate(request_id, db_path=self._db_path)

    def events(self, request_id, *, after):
        return requests.events(request_id, after=after, db_path=self._db_path)

    def mine(self, user_id, *, limit, offset):
        return requests.mine(user_id, limit=limit, offset=offset, db_path=self._db_path)

    def run_options(self, request_id):
        directory = self._recording_dir
        return {
            "db_path": self._db_path,
            "recording_path": Path(directory) / f"{request_id}-model-calls.json"
            if directory
            else None,
            "measurement": self._measurement,
        }


class AuthService:
    def __init__(self, db_path):
        self._db_path = db_path

    async def session_user(self, token):
        return await auth_cases.session_user(token, db_path=self._db_path)

    async def signup(self, email, password, agree_terms, *, mail, auth):
        return await auth_cases.signup(
            email, password, agree_terms, db_path=self._db_path, mail=mail, auth=auth
        )

    async def login_after_signup(self, user_id):
        return await auth_cases.login_after_signup(user_id, db_path=self._db_path)

    async def login(self, email, password):
        return await auth_cases.login(email, password, db_path=self._db_path)

    async def logout(self, token):
        return await auth_cases.logout(token, db_path=self._db_path)

    async def withdraw(self, user_id):
        return await auth_cases.withdraw(user_id, db_path=self._db_path)

    async def verify_email(self, token):
        return await auth_cases.verify_email(token, db_path=self._db_path)

    async def resend_verification(self, user, *, mail, auth):
        return await auth_cases.resend_verification(
            user, db_path=self._db_path, mail=mail, auth=auth
        )

    async def forgot_password(self, email, *, mail, auth):
        return await auth_cases.forgot_password(email, db_path=self._db_path, mail=mail, auth=auth)

    async def reset_password(self, token, new_password):
        return await auth_cases.reset_password(token, new_password, db_path=self._db_path)

    async def start_kakao_login(self, next_path):
        return await auth_cases.start_kakao_login(next_path, db_path=self._db_path)

    async def kakao_callback(self, code, state, *, kakao):
        return await auth_cases.kakao_callback(code, state, db_path=self._db_path, kakao=kakao)


class Services:
    def __init__(self, db_path, *, recording_dir=None, measurement=False):
        self.requests = RequestService(
            db_path, recording_dir=recording_dir, measurement=measurement
        )
        self.auth = AuthService(db_path)

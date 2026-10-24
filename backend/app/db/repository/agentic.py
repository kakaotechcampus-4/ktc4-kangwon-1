"""판단 루프의 실행 상태·질문·도구 기록·평가·리포트를 읽고 씁니다."""


def begin_immediate(db):
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")

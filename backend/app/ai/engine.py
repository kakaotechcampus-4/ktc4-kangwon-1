from app.ai.budget import RuntimeBudget
from app.ai.runtime import DecisionLoop


class AgenticDecisions:
    @staticmethod
    def budget(*, measurement):
        return RuntimeBudget(measurement=measurement)

    @staticmethod
    async def create(scope, site, **options):
        return await DecisionLoop.create(scope, site, **options)

    @staticmethod
    async def validate_resume(scope, answers):
        return await DecisionLoop.validate_resume(scope, answers)

    @staticmethod
    async def resume(scope, site, answers, **options):
        return await DecisionLoop.resume(scope, site, answers, **options)

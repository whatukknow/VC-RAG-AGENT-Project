"""공용 예외."""


class BudgetExceeded(Exception):
    """API 비용 한도에 도달했다. 개별 질문 오류가 아니라 실행 전체를 멈춰야 하므로 삼키면 안 된다."""

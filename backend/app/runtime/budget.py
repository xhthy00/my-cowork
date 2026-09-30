"""Step/token budget guard for graph execution."""


class BudgetExhausted(Exception):
    """Raised when a task exceeds its step or token budget."""


class Budget:
    """Track and enforce per-task step/token limits."""

    def __init__(self, max_steps: int, max_total_tokens: int):
        self.max_steps = max_steps
        self.max_total_tokens = max_total_tokens
        self.steps = 0
        self.tokens = 0

    def consume_step(self) -> None:
        next_steps = self.steps + 1
        if next_steps > self.max_steps:
            raise BudgetExhausted(
                f"Step budget exhausted: {next_steps} > {self.max_steps}"
            )
        self.steps = next_steps

    def consume_tokens(self, n: int) -> None:
        total = self.tokens + n
        if total > self.max_total_tokens:
            raise BudgetExhausted(
                f"Token budget exhausted: {total} > {self.max_total_tokens}"
            )
        self.tokens = total

    @property
    def exhausted(self) -> bool:
        return self.steps >= self.max_steps or self.tokens >= self.max_total_tokens

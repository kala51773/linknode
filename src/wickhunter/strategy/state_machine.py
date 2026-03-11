from dataclasses import dataclass, field
from enum import Enum


class StrategyState(str, Enum):
    DISCOVER = "DISCOVER"
    ARM = "ARM"
    QUOTE = "QUOTE"
    FILL_B = "FILL_B"
    HEDGE_A = "HEDGE_A"
    MANAGE = "MANAGE"
    EXIT = "EXIT"
    RESET = "RESET"


TRANSITIONS: dict[StrategyState, set[StrategyState]] = {
    StrategyState.DISCOVER: {StrategyState.ARM},
    StrategyState.ARM: {StrategyState.QUOTE, StrategyState.DISCOVER},
    StrategyState.QUOTE: {StrategyState.FILL_B, StrategyState.RESET},
    StrategyState.FILL_B: {StrategyState.HEDGE_A},
    StrategyState.HEDGE_A: {StrategyState.MANAGE, StrategyState.EXIT},
    StrategyState.MANAGE: {StrategyState.EXIT},
    StrategyState.EXIT: {StrategyState.RESET},
    StrategyState.RESET: {StrategyState.DISCOVER},
}


@dataclass(slots=True)
class EngineState:
    current: StrategyState = StrategyState.DISCOVER
    history: list[StrategyState] = field(default_factory=lambda: [StrategyState.DISCOVER])

    def transition(self, nxt: StrategyState) -> None:
        allowed = TRANSITIONS.get(self.current, set())
        if nxt not in allowed:
            raise ValueError(f"invalid transition: {self.current} -> {nxt}")
        self.current = nxt
        self.history.append(nxt)

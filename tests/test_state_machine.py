import unittest

from wickhunter.strategy.state_machine import EngineState, StrategyState


class TestStateMachine(unittest.TestCase):
    def test_happy_path(self) -> None:
        state = EngineState()
        flow = [
            StrategyState.ARM,
            StrategyState.QUOTE,
            StrategyState.FILL_B,
            StrategyState.HEDGE_A,
            StrategyState.MANAGE,
            StrategyState.EXIT,
            StrategyState.RESET,
            StrategyState.DISCOVER,
        ]

        for nxt in flow:
            state.transition(nxt)

        self.assertEqual(state.current, StrategyState.DISCOVER)
        self.assertEqual(state.history[0], StrategyState.DISCOVER)

    def test_invalid_transition(self) -> None:
        state = EngineState()
        with self.assertRaises(ValueError):
            state.transition(StrategyState.HEDGE_A)


if __name__ == "__main__":
    unittest.main()

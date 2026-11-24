from itertools import product
from unittest import TestCase
from .puzzles import PUZZLES, hint, parse_moves, route_lesson, simulate


def winning_moves(board):
    possibilities = [range(c["states"]) for c in board["cells"] if c["states"] > 1]
    return [s for s in product(*possibilities) if simulate(board, s)["success"]]


class RouteRulesTests(TestCase):
    def test_every_authored_map_and_orientation(self):
        import json
        for key in PUZZLES:
            rounds = set()
            boards = set()
            for rotation in range(40):
                items = route_lesson(key, rotation)["items"]
                rounds.add(json.dumps([item["board"] for item in items], sort_keys=True))
                for item in items:
                    board = item["board"]
                    boards.add(json.dumps(board, sort_keys=True))
                    with self.subTest(key=key, level=board["name"], rotation=rotation):
                        wins = winning_moves(board)
                        self.assertTrue(wins)
                        initial = (0,) * len(wins[0])
                        self.assertFalse(simulate(board, initial)["success"])
                        self.assertIsNotNone(hint(board, initial))
                        self.assertIsNone(hint(board, wins[0]))
                        self.assertEqual(simulate(board, wins[0]), simulate(board, wins[0]))

            self.assertEqual(len(rounds), 40)
            self.assertEqual(len(boards), 200)

    def test_branch_rules_and_switch_rules(self):
        water = route_lesson("water-works-v1")["items"]
        self.assertEqual(simulate(water[0]["board"], (0,))["reason"], "closed")
        leak = water[3]["board"]
        self.assertEqual(simulate(leak, (1, 0))["reason"], "gap")
        self.assertTrue(simulate(leak, (1, 1))["success"])
        self.assertFalse(simulate(water[4]["board"], (0, 3))["success"])
        train = route_lesson("train-tracks-v1")["items"]
        self.assertEqual(simulate(train[3]["board"], (0, 0))["reason"], "passenger")
        self.assertGreater(len(winning_moves(train[4]["board"])), 1)
        self.assertEqual(simulate(train[0]["board"], (0,))["trace"], [4, 5])

    def test_workshop_rules(self):
        cases = [
            ("gates-switches-v1", 3, (1, 0), "gates"),
            ("gates-switches-v1", 3, (0, 1), "gates"),
            ("bridges-v1", 1, (1,), "bridge"),
            ("bridges-v1", 1, (2,), ""),
            ("gears-motion-v1", 3, (0, 1), "spin"),
            ("gears-motion-v1", 3, (1, 1), ""),
            ("delivery-routes-v1", 3, (0, 0, 1, 0), "pickup"),
            ("delivery-routes-v1", 3, (0, 1, 3, 3), "loop"),
        ]
        for key, stage, moves, reason in cases:
            board = route_lesson(key)["items"][stage]["board"]
            with self.subTest(key=key, moves=moves):
                self.assertEqual(simulate(board, moves)["reason"], reason)

    def test_invalid_boards_cannot_be_submitted(self):
        board = route_lesson("train-tracks-v1")["items"][0]["board"]
        for bad in ("", "yes", "2", "-1", "01", "１"):
            self.assertIsNone(parse_moves(board, bad))

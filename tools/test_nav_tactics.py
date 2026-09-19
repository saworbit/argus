import unittest

try:
    from argus_nav_tactics import compute_tactics
except ModuleNotFoundError:
    from tools.argus_nav_tactics import compute_tactics


class NavTacticsTests(unittest.TestCase):
    def test_counts_other_visible_nodes(self):
        nodes = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
        visible = [
            [True, True, False],
            [True, True, True],
            [False, True, True],
        ]
        exposure, _ = compute_tactics(nodes, [[1], [0, 2], [1]], visible)
        self.assertEqual(exposure, [1, 2, 1])

    def test_cover_uses_shortest_hidden_walk_and_first_hop(self):
        nodes = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 3, 0)]
        adjacency = [[1, 3], [2], [], [2]]
        visible = [
            [True, True, False, True],
            [True, True, False, True],
            [False, False, True, False],
            [True, True, False, True],
        ]
        _, cover = compute_tactics(nodes, adjacency, visible)
        self.assertEqual(cover[0], [2, 1])

    def test_unreachable_hidden_node_has_no_cover_hop(self):
        nodes = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
        visible = [
            [True, True, False],
            [True, True, True],
            [False, True, True],
        ]
        _, cover = compute_tactics(nodes, [[1], [], []], visible)
        self.assertEqual(cover[0], [-1, -1])


if __name__ == "__main__":
    unittest.main()

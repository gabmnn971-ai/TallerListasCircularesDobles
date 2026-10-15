import unittest
from unittest.mock import patch

from main import ParticipantCircle, RouletteSession


class ParticipantCircleTests(unittest.TestCase):
    def test_ring_links_in_both_directions_and_wraps(self):
        circle = ParticipantCircle()
        participants = [circle.add(name) for name in ("A", "B", "C")]

        self.assertIs(participants[0].previous, participants[2])
        self.assertIs(participants[2].next, participants[0])
        forward, forward_path = circle.advance(participants[0], 4, 1)
        backward, backward_path = circle.advance(participants[0], 1, -1)
        self.assertIs(forward, participants[1])
        self.assertEqual(forward_path, [participants[1].participant_id, participants[2].participant_id,
                                        participants[0].participant_id, participants[1].participant_id])
        self.assertIs(backward, participants[2])
        self.assertEqual(backward_path, [participants[2].participant_id])

    def test_removing_head_keeps_circle_bidirectional(self):
        circle = ParticipantCircle()
        participants = [circle.add(name) for name in ("A", "B", "C")]
        circle.remove(participants[0])

        self.assertEqual([person.name for person in circle], ["B", "C"])
        self.assertIs(participants[1].previous, participants[2])
        self.assertIs(participants[2].next, participants[1])


class RouletteSessionTests(unittest.TestCase):
    def setUp(self):
        self.session = RouletteSession()
        self.session.reset(["Ada", "Grace", "Linus"])

    def test_random_spin_reports_a_valid_traversal_and_eliminates_target(self):
        with patch.object(self.session.rng, "choice", return_value=1), patch.object(
            self.session.rng, "randint", return_value=2
        ):
            result = self.session.spin("eliminate", "random")

        self.assertEqual(result["steps"], 2)
        self.assertEqual(result["direction"], "clockwise")
        self.assertEqual(result["participant_name"], "Linus")
        self.assertEqual(len(result["path"]), 2)
        self.assertEqual([p["name"] for p in result["state"]["participants"]], ["Ada", "Grace"])
        self.assertTrue(result["state"]["participants"][0]["is_current"])

    def test_winner_finishes_round_and_prevents_another_spin(self):
        with patch.object(self.session.rng, "randint", return_value=1):
            result = self.session.spin("winner", "clockwise")

        self.assertEqual(result["participant_name"], "Grace")
        self.assertEqual(result["state"]["status"], "finished")
        with self.assertRaisesRegex(ValueError, "Reset the round"):
            self.session.spin("winner", "clockwise")

    def test_checkpoint_restores_ring_cursor_and_history(self):
        checkpoint = self.session.create_checkpoint("Before the final round")
        with patch.object(self.session.rng, "randint", return_value=1):
            self.session.spin("eliminate", "clockwise")
        self.session.restore_checkpoint(checkpoint["id"])

        self.assertEqual([p["name"] for p in self.session.state()["participants"]], ["Ada", "Grace", "Linus"])
        self.assertEqual(self.session.state()["current_id"], self.session.circle.head.participant_id)
        self.assertEqual(self.session.state()["round_count"], 0)
        self.assertEqual(self.session.state()["history"][0]["title"], "Checkpoint restored")

    def test_invalid_and_duplicate_participants_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "already in the circle"):
            self.session.add_participant("  ada ")
        with self.assertRaisesRegex(ValueError, "1 to 32"):
            self.session.add_participant("   ")


if __name__ == "__main__":
    unittest.main()

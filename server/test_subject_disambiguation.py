"""Run from server/: python -m unittest test_subject_disambiguation -v.

Covers the multi-person 'found' rules (safety.check_found), bbox->ground projection (geometry),
and that the extended SearchStep survives the strict structured-output validation path.
"""
import math
import unittest
from types import SimpleNamespace as NS

import ai_backends
import geometry
import safety
from models import DroneState, MissionPlan, PersonCandidate, SearchStep


def cand(posture="prone", conf=0.9, moving=False, bbox=(300, 200, 480, 260)):
    return PersonCandidate(bbox=list(bbox), posture=posture, is_moving=moving, subject_confidence=conf, reason="test")


def found(candidates, chosen=0, confidence=0.9):
    return SearchStep(action="found", confidence=confidence, observation="test",
                      candidates=candidates, chosen_index=chosen)


class FoundRuleTests(unittest.TestCase):
    def setUp(self):
        self.home = (25.7617, -80.1918)
        self.drone = NS(latitude=self.home[0], longitude=self.home[1], battery_pct=80)

    def check(self, step):
        return safety.check_step(step, self.drone, *self.home, 0)

    def test_single_prone_person_is_accepted(self):
        self.assertTrue(self.check(found([cand()])).ok)

    def test_prone_subject_beats_upright_bystanders(self):
        step = found([cand("upright", 0.1, True, (100, 80, 140, 200)), cand(), cand("upright", 0.2)], chosen=1)
        self.assertTrue(self.check(step).ok)

    def test_found_needs_candidates_and_a_valid_choice(self):
        self.assertFalse(self.check(found([])).ok)
        self.assertFalse(self.check(found([cand()], chosen=None)).ok)
        self.assertFalse(self.check(found([cand()], chosen=3)).ok)

    def test_ambiguous_candidates_keep_searching(self):
        two_down = found([cand(conf=0.85), cand(conf=0.8, bbox=(50, 50, 200, 110))])
        v = self.check(two_down)
        self.assertFalse(v.ok)
        self.assertIn("ambiguous", v.reason)
        # once the gap is clear, the same scene is accepted
        self.assertTrue(self.check(found([cand(conf=0.9), cand(conf=0.4, bbox=(50, 50, 200, 110))])).ok)

    def test_chosen_must_be_down_and_top_rated(self):
        self.assertFalse(self.check(found([cand("upright")])).ok)
        self.assertFalse(self.check(found([cand(conf=0.5), cand(conf=0.9, bbox=(1, 1, 2, 2))], chosen=0)).ok)

    def test_low_confidence_found_rejected_regardless_of_candidates(self):
        self.assertFalse(self.check(found([cand()], confidence=0.79)).ok)
        nan_step = NS(action="found", confidence=math.nan, candidates=[cand()], chosen_index=0)
        self.assertFalse(self.check(nan_step).ok)

    def test_bad_bbox_rejected(self):
        bad = SearchStep(action="found", confidence=0.9, observation="x", chosen_index=0,
                         candidates=[PersonCandidate(bbox=[1, 2, 3], posture="prone", is_moving=False,
                                                     subject_confidence=0.9, reason="r")])
        self.assertFalse(self.check(bad).ok)

    def test_other_actions_unaffected(self):
        self.assertTrue(self.check(SearchStep(action="yaw", yaw_deg=45, observation="x")).ok)


class GeometryTests(unittest.TestCase):
    W, H = 640, 360

    def test_straight_down_centre_pixel_is_under_the_aircraft(self):
        hit = geometry.bbox_ground_point([310, 170, 330, 180], self.W, self.H, altitude_m=10,
                                         heading_deg=0, gimbal_pitch_deg=-90)
        self.assertIsNotNone(hit)
        north, east, rng = hit
        self.assertAlmostEqual(north, 0, places=6)
        self.assertAlmostEqual(east, 0, places=6)

    def test_45_degree_centre_pixel_lands_altitude_ahead(self):
        # box whose bottom edge is on the optical axis (v = 0.5)
        hit = geometry.bbox_ground_point([310, 160, 330, 180], self.W, self.H, altitude_m=10,
                                         heading_deg=0, gimbal_pitch_deg=-45)
        north, east, rng = hit
        self.assertAlmostEqual(north, 10, places=6)
        self.assertAlmostEqual(east, 0, places=6)

    def test_heading_rotates_the_offset(self):
        hit = geometry.bbox_ground_point([310, 160, 330, 180], self.W, self.H, altitude_m=10,
                                         heading_deg=90, gimbal_pitch_deg=-45)
        north, east, rng = hit
        self.assertAlmostEqual(north, 0, places=6)
        self.assertAlmostEqual(east, 10, places=6)

    def test_right_of_frame_is_right_of_track(self):
        hit = geometry.bbox_ground_point([600, 160, 640, 180], self.W, self.H, altitude_m=10,
                                         heading_deg=0, gimbal_pitch_deg=-45)
        self.assertGreater(hit[1], 0)
        self.assertGreater(hit[0], 0)

    def test_horizon_rays_return_none(self):
        # camera nearly level, box at the top of the frame: ray goes up/out, no ground hit
        self.assertIsNone(geometry.bbox_ground_point([300, 0, 340, 10], self.W, self.H, altitude_m=10,
                                                     heading_deg=0, gimbal_pitch_deg=-5))
        self.assertIsNone(geometry.bbox_ground_point([1, 2, 3], self.W, self.H, altitude_m=10,
                                                     heading_deg=0, gimbal_pitch_deg=-60))
        self.assertIsNone(geometry.bbox_ground_point([1, 2, 3, 4], self.W, self.H, altitude_m=0,
                                                     heading_deg=0, gimbal_pitch_deg=-60))

    def test_locate_reports_distance_from_report_not_aircraft(self):
        lat, lng = 25.7617, -80.1918
        # aircraft hovering 6 m north of the report, camera 45° down looking south: subject 10 m south of aircraft
        hit = geometry.locate([310, 160, 330, 180], self.W, self.H, drone_lat=lat + 6 / 111_320.0, drone_lng=lng,
                              altitude_m=10, heading_deg=180, gimbal_pitch_deg=-45, report_lat=lat, report_lng=lng)
        self.assertAlmostEqual(hit.north_m, -10, places=1)
        self.assertAlmostEqual(hit.distance_from_report_m, 4.0, places=0)

    def test_frame_size_reads_jpeg_and_rejects_garbage(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (64, 32)).save(buf, "JPEG")
        self.assertEqual(geometry.frame_size(buf.getvalue()), (64, 32))
        self.assertIsNone(geometry.frame_size(b"not a jpeg"))


class SchemaTests(unittest.TestCase):
    def test_strict_schema_includes_candidates(self):
        schema = ai_backends.strict_schema(SearchStep)
        self.assertIn("candidates", schema["properties"])
        self.assertIn("chosen_index", schema["required"])
        cand_schema = schema["$defs"]["PersonCandidate"]
        self.assertFalse(cand_schema["additionalProperties"])
        self.assertEqual(set(cand_schema["required"]), {"bbox", "posture", "is_moving", "subject_confidence", "reason"})

    def test_validate_decision_accepts_multi_person_payload(self):
        payload = {"action": "found", "yaw_deg": None, "gimbal_pitch_deg": None, "move_bearing_deg": None,
                   "move_distance_m": None, "confidence": 0.86, "observation": "two people, one prone",
                   "candidates": [
                       {"bbox": [300, 205, 475, 255], "posture": "prone", "is_moving": False,
                        "subject_confidence": 0.9, "reason": "lying flat near centre"},
                       {"bbox": [130, 70, 160, 200], "posture": "upright", "is_moving": True,
                        "subject_confidence": 0.05, "reason": "standing, walking away"}],
                   "chosen_index": 0}
        step = ai_backends.validate_decision(payload, SearchStep)
        self.assertEqual(len(step.candidates), 2)
        self.assertEqual(step.chosen_index, 0)

    def test_validate_decision_rejects_non_finite_nested_numbers(self):
        payload = {"action": "found", "confidence": 0.9, "observation": "x", "chosen_index": 0,
                   "candidates": [{"bbox": [1, 2, 3, 4], "posture": "prone", "is_moving": False,
                                   "subject_confidence": float("nan"), "reason": "r"}]}
        with self.assertRaises(ai_backends.AIError):
            ai_backends.validate_decision(payload, SearchStep)

    def test_legacy_payload_without_candidates_still_parses(self):
        step = ai_backends.validate_decision({"action": "yaw", "yaw_deg": 45.0, "confidence": 0.1, "observation": "grass"}, SearchStep)
        self.assertEqual(step.candidates, [])
        self.assertIsNone(step.chosen_index)


class AppHelperTests(unittest.TestCase):
    def test_describe_and_summarize(self):
        import app
        drone = DroneState(latitude=25.7617, longitude=-80.1918, altitude_m=10, heading_deg=0, gimbal_pitch_deg=-60)
        plan = MissionPlan(target_lat=25.7617, target_lng=-80.1918, search_radius_m=8, altitude_m=10, rationale="t")
        step = found([cand(), cand("upright", 0.1, True, (100, 80, 140, 200))])
        cs = app.describe_candidates(step, (640, 360), drone, plan)
        self.assertEqual(len(cs), 2)
        self.assertTrue(cs[0]["chosen"] and not cs[1]["chosen"])
        self.assertIsNotNone(cs[0]["est_distance_from_report_m"])
        text = app.summarize_candidates(cs, 0)
        self.assertIn("2 people in frame, subject=#1", text)
        self.assertIn("#1* prone still", text)
        self.assertEqual(app.summarize_candidates([], None), "0 people in frame")


if __name__ == "__main__":
    unittest.main()

"""Run from server/: python -m unittest test_safety -v."""
import math
import unittest
from types import SimpleNamespace as NS
import safety


class IPhoneSafetyTests(unittest.TestCase):
    def setUp(self):
        self.home = (25.7617, -80.1918)
        self.drone = NS(latitude=self.home[0], longitude=self.home[1], battery_pct=80)
        self.plan = NS(target_lat=self.home[0], target_lng=self.home[1], altitude_m=10,
                       search_radius_m=10, gimbal_pitch_deg=-60)

    def test_nearby_plan_and_altitude_bounds(self):
        self.assertTrue(safety.check_mission(self.plan, *self.home, self.drone).ok)
        for altitude in (1.0, 1.2, 30.0):
            self.plan.altitude_m = altitude
            self.assertTrue(safety.check_mission(self.plan, *self.home, self.drone).ok)
        for altitude in (.99, 30.1, math.nan, math.inf):
            self.plan.altitude_m = altitude
            self.assertFalse(safety.check_mission(self.plan, *self.home, self.drone).ok)

    def test_entire_search_area_must_fit(self):
        self.plan.target_lat, self.plan.target_lng = safety.offset_latlng(*self.home, 0, 30)
        self.assertFalse(safety.check_mission(self.plan, *self.home, self.drone).ok)
        self.plan.search_radius_m = 5
        self.assertTrue(safety.check_mission(self.plan, *self.home, self.drone).ok)

    def test_five_metre_moves_and_invalid_numbers(self):
        step = NS(action='move', move_bearing_deg=90, move_distance_m=5)
        self.assertTrue(safety.check_step(step, self.drone, *self.home, 0).ok)
        for distance in (5.01, 15, -1, math.nan, math.inf):
            step.move_distance_m = distance
            self.assertFalse(safety.check_step(step, self.drone, *self.home, 0).ok)
        step.move_distance_m = 5
        for bearing in (-1, 360, math.nan):
            step.move_bearing_deg = bearing
            self.assertFalse(safety.check_step(step, self.drone, *self.home, 0).ok)

    def test_move_cannot_exit_fence(self):
        self.drone.latitude, self.drone.longitude = safety.offset_latlng(*self.home, 0, 33)
        step = NS(action='move', move_bearing_deg=0, move_distance_m=5)
        self.assertFalse(safety.check_step(step, self.drone, *self.home, 0).ok)
        step.move_bearing_deg = 180
        self.assertTrue(safety.check_step(step, self.drone, *self.home, 0).ok)

    def test_battery_and_step_limit(self):
        step = NS(action='yaw', yaw_deg=45)
        for battery in (29, math.nan):
            self.drone.battery_pct = battery
            self.assertFalse(safety.check_mission(self.plan, *self.home, self.drone).ok)
            self.assertFalse(safety.check_step(step, self.drone, *self.home, 0).ok)
        self.drone.battery_pct = 30
        self.assertTrue(safety.check_step(step, self.drone, *self.home, 11).ok)
        self.assertFalse(safety.check_step(step, self.drone, *self.home, 12).ok)

    def test_camera_angles_and_invalid_coordinates(self):
        for step in (NS(action='yaw', yaw_deg=181), NS(action='yaw', yaw_deg=math.nan),
                     NS(action='gimbal', gimbal_pitch_deg=1), NS(action='gimbal', gimbal_pitch_deg=math.nan)):
            self.assertFalse(safety.check_step(step, self.drone, *self.home, 0).ok)
        self.plan.target_lat = math.nan
        self.assertFalse(safety.check_mission(self.plan, *self.home, self.drone).ok)


if __name__ == '__main__':
    unittest.main()

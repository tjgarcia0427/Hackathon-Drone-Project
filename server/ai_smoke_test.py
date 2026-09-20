"""Exercise one AI provider with a synthetic image; never connects to the drone."""
from __future__ import annotations
import argparse
import io
import json
import time
from typing import Literal
from PIL import Image, ImageDraw
from pydantic import BaseModel
import ai_backends


class ImageCheck(BaseModel):
    shape: Literal["circle", "square", "triangle", "other"]
    color: str
    person_visible: bool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=ai_backends.PROVIDERS)
    parser.add_argument("--model", default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-only", action="store_true", help="Check configuration/login without a model call")
    mode.add_argument("--search-check", action="store_true", help="Use the real search prompt/schema and 8-second deadline, without a drone")
    args = parser.parse_args()
    current = ai_backends.from_environment()
    settings = ai_backends.Settings(args.provider or current.provider,
                                   args.model if args.model is not None else
                                   (current.model if not args.provider or args.provider == current.provider else ""))
    started = time.monotonic()
    try:
        ai_backends.validate_setup(settings, authenticate=True)
        if args.check_only:
            print(json.dumps({"ok": True, **settings.public(), "note": "Configuration/login checked; model access not tested"}, indent=2))
            return
        image = Image.new("RGB", (320, 240), "white")
        ImageDraw.Draw(image).ellipse((90, 50, 230, 190), fill="red")
        data = io.BytesIO()
        image.save(data, format="JPEG")
        started = time.monotonic()
        if args.search_check:
            import planner
            import safety
            from models import DroneState
            planner.configure(settings.provider, settings.model)
            drone = DroneState(latitude=25.7617, longitude=-80.1918, altitude_m=10, heading_deg=0)
            decision = planner.next_search_step(drone, data.getvalue(), None, [], drone.latitude, drone.longitude)
            correct = decision.action != "found" and safety.check_step(decision, drone, drone.latitude, drone.longitude, 0).ok
        else:
            decision = ai_backends.generate(settings, ImageCheck,
                "Describe only the attached test image. Return the requested structured result. Do not use tools.",
                "What is the main shape, what color is it, and is a person visible?", data.getvalue(), timeout=60)
            correct = decision.shape == "circle" and "red" in decision.color.lower() and not decision.person_visible
        elapsed = time.monotonic() - started
        print(json.dumps({"ok": correct, **settings.public(), "seconds": round(elapsed, 2),
                          "search_check": args.search_check,
                          "within_search_deadline": elapsed < 8, "result": decision.model_dump(),
                          "note": "Synthetic-image test only; no drone connection or flight command"}, indent=2))
        if not correct:
            raise SystemExit(1)
    except ai_backends.AIError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "seconds": round(time.monotonic() - started, 2),
                          "search_check": args.search_check}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

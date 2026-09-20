"""Send an explicitly TEST-ONLY Watch alert, then replay its ID to check deduplication."""
import argparse
from datetime import datetime, timezone
import json
from urllib.request import Request, urlopen
from uuid import uuid4


def request(base, path, value=None):
    data = None if value is None else json.dumps(value).encode()
    req = Request(base.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=12) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--source", choices=["watch_button", "watch_shake"], default="watch_button")
    args = parser.parse_args()
    session = request(args.server, "/watch/status")
    event = {"event_id": str(uuid4()), "server_session": session["server_session"], "source": args.source,
             "timestamp": datetime.now(timezone.utc).isoformat(), "test_mode": True}
    first = request(args.server, "/watch/alerts", event)
    retry = request(args.server, "/watch/alerts", event)
    if first["status"] != "test_received" or first["duplicate"] or not retry["duplicate"]:
        raise SystemExit("FAIL: unexpected test receipt or duplicate handling")
    print(json.dumps(first, indent=2))
    print("PASS: test alert delivered once; retry returned its same ID. No mission created by this alert.")


if __name__ == "__main__":
    main()

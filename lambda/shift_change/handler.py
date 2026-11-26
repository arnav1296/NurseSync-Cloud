"""AWS Lambda: runs at each shift change (EventBridge Scheduler, 07:00 and 19:00 IST).

Calls the API's protected /api/internal/shift-change route, which builds the shift report
(stored in S3) and emails reminders through SNS to nurses whose patients aren't handed
off yet. Going through the API keeps this function outside the VPC: no NAT gateway, no
database credentials here.
"""

import json
import os
import urllib.request


def handler(event, context):
    request = urllib.request.Request(
        os.environ["API_URL"].rstrip("/") + "/api/internal/shift-change",
        method="POST",
        headers={"X-Internal-Token": os.environ["INTERNAL_API_TOKEN"]},
        data=b"",
    )
    with urllib.request.urlopen(request, timeout=50) as response:
        body = json.loads(response.read())
    print(json.dumps({"status": response.status, **body}))
    return body

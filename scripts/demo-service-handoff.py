"""Run synthetic HTTP integration fixtures. This is not a new LLM benchmark."""

import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from examples.w4_service_demo import DemoBackend, DemoClient, create_demo_app, read


async def main():
    out = ROOT / "output/service-handoff-20260909"
    out.mkdir(parents=True, exist_ok=True)
    for name, diagnostic in (("synthetic-company", False), ("diagnostic-company", True)):
        backend, extractor, judge = DemoBackend(diagnostic), DemoClient("extraction"), DemoClient("judgment")
        app = create_demo_app(backend, extractor, judge)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://in-process-test") as client:
            response = await client.post("/w4/recommend-from-raw", json=read("request.json"))
        if response.status_code != 200:
            raise RuntimeError(f"{name}: HTTP {response.status_code}: {response.text}")
        result = response.json()
        (out / f"{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(name, result["processing_status"], result["company_context"]["status"],
              f"{len(extractor.calls)+len(judge.calls)} simulated calls; 0 real calls")


if __name__ == "__main__":
    asyncio.run(main())

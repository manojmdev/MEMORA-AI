import asyncio
import uuid
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
from app.database import init_db_pool, close_db_pool

async def main():
    pool = await init_db_pool()
    target_id = uuid.UUID("c3a524df-05e7-45ba-b991-ec330d75e0a8")

    async with pool.acquire() as conn:
        logs = await conn.fetch("SELECT * FROM agent_execution_logs WHERE task_id = $1 ORDER BY created_at", target_id)
        print(f"=== EXECUTION LOGS FOR {target_id} ({len(logs)}) ===")
        for l in logs:
            l_dict = dict(l)
            print(f"[{l_dict.get('created_at')}] step={l_dict.get('step_id')} tool={l_dict.get('tool_name')} status={l_dict.get('status')} err={l_dict.get('error_code')}")
            print(f"   summary: {l_dict.get('result_summary')}")

    await close_db_pool()

if __name__ == "__main__":
    asyncio.run(main())

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
        cols = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'agent_task_checkpoints'
            ORDER BY ordinal_position;
        """)
        print("agent_task_checkpoints columns:")
        for c in cols:
            print(f"  {c['column_name']} ({c['data_type']})")

        cps = await conn.fetch("SELECT * FROM agent_task_checkpoints WHERE task_id = $1", target_id)
        print(f"\n=== CHECKPOINTS FOR TASK ({len(cps)}) ===")
        for c in cps:
            print(dict(c))

        audit_cols = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'agent_audit_logs'
            ORDER BY ordinal_position;
        """)
        print("\nagent_audit_logs columns:")
        for c in audit_cols:
            print(f"  {c['column_name']} ({c['data_type']})")

        audits = await conn.fetch("SELECT * FROM agent_audit_logs WHERE task_id = $1", target_id)
        print(f"\n=== AUDIT LOGS FOR TASK ({len(audits)}) ===")
        for a in audits:
            print(dict(a))

    await close_db_pool()

if __name__ == "__main__":
    asyncio.run(main())

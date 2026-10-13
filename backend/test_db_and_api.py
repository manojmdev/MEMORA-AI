import asyncio
import uuid
from app.database import init_db_pool, close_db_pool, check_db_health
from fastapi.testclient import TestClient
from app.main import app

async def test_database():
    print("=== 1. Database Pool & Schema Verification ===")
    pool = await init_db_pool()
    assert pool is not None, "Database pool failed to initialize"
    print("Database pool initialized successfully.")
    
    health = await check_db_health()
    print("Health check response:", health)
    assert health["status"] == "healthy", f"Expected healthy, got {health}"
    
    async with pool.acquire() as conn:
        cols = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'memories'
            ORDER BY ordinal_position;
        """)
        print(f"Verified 'memories' table columns ({len(cols)} columns):")
        for col in cols:
            print(f"  - {col['column_name']} ({col['data_type']})")
            
        print("\n=== 2. Database CRUD Operations ===")
        test_session_id = "test_session_" + str(uuid.uuid4())[:8]
        test_key = "user_preference_test"
        
        # INSERT
        insert_id = await conn.fetchval("""
            INSERT INTO memories (session_id, category, memory_key, content, confidence_score, source_message)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id;
        """, test_session_id, "user_preference", test_key, "User enjoys building AI memory agents", 0.98, "I enjoy building AI agents")
        print(f"INSERT SUCCESS: Created record ID = {insert_id}")
        
        # SELECT
        row = await conn.fetchrow("SELECT * FROM memories WHERE id = $1", insert_id)
        assert row is not None, "Inserted record was not retrieved"
        print(f"SELECT SUCCESS: Fetched session_id='{row['session_id']}', key='{row['memory_key']}', content='{row['content']}'")
        
        # DELETE
        deleted = await conn.execute("DELETE FROM memories WHERE id = $1", insert_id)
        print(f"DELETE SUCCESS: Status = {deleted}")
        
        # Verify removal
        check_del = await conn.fetchrow("SELECT * FROM memories WHERE id = $1", insert_id)
        assert check_del is None, "Record should not exist after DELETE"
        print("DELETE VERIFIED: Record confirmed removed.")

    await close_db_pool()
    print("Database pool closed cleanly.")

def test_api_endpoints():
    print("\n=== 3. FastAPI Endpoints & Nemotron Verification ===")
    with TestClient(app) as client:
        # GET /
        res_root = client.get("/")
        print("GET / ->", res_root.status_code, res_root.json())
        assert res_root.status_code == 200
        
        # GET /health
        res_health = client.get("/health")
        print("GET /health ->", res_health.status_code, res_health.json())
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "healthy"
        assert res_health.json()["database"]["status"] == "healthy"
        
        # POST /api/chat
        res_chat = client.post("/api/chat", json={"message": "Say 'Integration verified!' in one brief sentence."})
        print("POST /api/chat ->", res_chat.status_code, res_chat.json())
        assert res_chat.status_code == 200
        assert "reply" in res_chat.json()
        print("Nemotron Live Reply:", res_chat.json()["reply"])

if __name__ == "__main__":
    asyncio.run(test_database())
    test_api_endpoints()
    print("\n>>> ALL TESTS PASSED SUCCESSFULLY! <<<")

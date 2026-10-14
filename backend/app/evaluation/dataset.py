"""
MEMORA AI — Evaluation Dataset & Ground Truth Fixtures
Defines deterministic benchmark memories and diverse evaluation test cases covering:
exact keyword, semantic paraphrase, multi-memory synthesis, distractor resistance,
temporal expiration, superseded evolution, and cross-session privacy isolation.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional

@dataclass
class SeedMemory:
    category: str
    memory_type: str
    memory_key: str
    content: str
    confidence_score: float
    importance_score: float
    information_source: str
    persistence_type: str
    source_message: str
    valid_until: Optional[datetime] = None
    is_superseded_seed: bool = False
    is_distractor_session: bool = False

@dataclass
class TestCase:
    id: str
    name: str
    query: str
    description: str
    expected_keys: List[str]
    irrelevant_keys: List[str] = field(default_factory=list)
    target_session: str = "primary"  # "primary" or "distractor"
    k: int = 5

# Ground Truth Seed Memories
def get_benchmark_seed_memories() -> List[SeedMemory]:
    now = datetime.now(timezone.utc)
    expired_time = now - timedelta(days=2)
    active_future_time = now + timedelta(days=7)

    return [
        # 1. Core Preference
        SeedMemory(
            category="preferences",
            memory_type="personal_preference",
            memory_key="preferred_language",
            content="The user's primary programming language is Python for backend development.",
            confidence_score=0.95,
            importance_score=0.90,
            information_source="explicit_statement",
            persistence_type="persistent",
            source_message="I prefer Python for backend development over Java or Go."
        ),
        # 2. Frontend Skill
        SeedMemory(
            category="skills",
            memory_type="technical_skill",
            memory_key="frontend_framework",
            content="The user builds modern reactive web frontends using React and Vite with Tailwind CSS.",
            confidence_score=0.92,
            importance_score=0.85,
            information_source="explicit_statement",
            persistence_type="persistent",
            source_message="I develop my web apps with React and Vite."
        ),
        # 3. Backend Stack
        SeedMemory(
            category="skills",
            memory_type="technical_skill",
            memory_key="backend_stack",
            content="The user builds asynchronous REST APIs using FastAPI and asyncpg.",
            confidence_score=0.90,
            importance_score=0.85,
            information_source="explicit_statement",
            persistence_type="persistent",
            source_message="My preferred backend framework is FastAPI with asyncpg."
        ),
        # 4. Database & pgvector
        SeedMemory(
            category="projects",
            memory_type="project_info",
            memory_key="database_choice",
            content="The user's MEMORA AI platform utilizes Neon Lakebase PostgreSQL with pgvector for vector search.",
            confidence_score=0.95,
            importance_score=0.90,
            information_source="explicit_statement",
            persistence_type="persistent",
            source_message="We use Neon PostgreSQL with pgvector for semantic retrieval."
        ),
        # 5. Cloud Hosting
        SeedMemory(
            category="projects",
            memory_type="project_info",
            memory_key="cloud_hosting",
            content="The user hosts AI embeddings and models on Nebius Token Factory with NVIDIA Nemotron.",
            confidence_score=0.90,
            importance_score=0.80,
            information_source="explicit_statement",
            persistence_type="persistent",
            source_message="We run Nemotron models via Nebius Token Factory."
        ),
        # 6. Primary Goal
        SeedMemory(
            category="goals",
            memory_type="goal",
            memory_key="primary_goal",
            content="The user is actively building and developing the MEMORA AI persistent memory engine application.",
            confidence_score=0.95,
            importance_score=0.95,
            information_source="explicit_statement",
            persistence_type="persistent",
            source_message="My goal is developing the MEMORA AI application as an intelligent memory platform."
        ),
        # 7. Professional Role
        SeedMemory(
            category="personal_context",
            memory_type="general_fact",
            memory_key="user_role",
            content="The user's professional occupation is a senior software engineer specializing in AI systems architecture.",
            confidence_score=0.95,
            importance_score=0.85,
            information_source="explicit_statement",
            persistence_type="persistent",
            source_message="My professional occupation is a senior software engineer in AI systems architecture."
        ),
        # 8. Learning Style
        SeedMemory(
            category="learning_style",
            memory_type="personal_preference",
            memory_key="learning_style",
            content="The user prefers concise, architectural explanations accompanied by executable code snippets.",
            confidence_score=0.88,
            importance_score=0.70,
            information_source="contextual_inference",
            persistence_type="persistent",
            source_message="Keep explanations brief and give me practical code samples."
        ),
        # 9. Active Temporary Task (Valid)
        SeedMemory(
            category="projects",
            memory_type="temporary_activity",
            memory_key="urgent_sprint_task",
            content="The user is working on an urgent project task: completing the Day 5 memory evaluation benchmarks before the milestone review.",
            confidence_score=0.95,
            importance_score=0.85,
            information_source="explicit_statement",
            persistence_type="temporary",
            source_message="I am working on an urgent project task to finish the Day 5 evaluation suite before Thursday.",
            valid_until=active_future_time
        ),
        # 10. Expired Temporary Task (Should NOT be retrieved)
        SeedMemory(
            category="projects",
            memory_type="temporary_activity",
            memory_key="expired_meeting_note",
            content="The user was attending a temporary system design sync last Monday.",
            confidence_score=0.80,
            importance_score=0.45,
            information_source="explicit_statement",
            persistence_type="temporary",
            source_message="Sync meeting scheduled for last Monday.",
            valid_until=expired_time
        ),
        # 11. Cross-Session Distractor Memory (Stored ONLY in Distractor Session)
        SeedMemory(
            category="personal_context",
            memory_type="general_fact",
            memory_key="distractor_private_credit",
            content="Session Beta User secret credit card token: BETA-TOKEN-XYZ-9988.",
            confidence_score=1.0,
            importance_score=0.90,
            information_source="explicit_statement",
            persistence_type="persistent",
            source_message="My secret credit card token is BETA-TOKEN-XYZ-9988.",
            is_distractor_session=True
        ),
    ]

# Benchmark Test Cases
EVALUATION_BENCHMARK_SUITE: List[TestCase] = [
    TestCase(
        id="TC-01",
        name="Exact Keyword Match",
        query="What is my primary programming language?",
        description="Verifies direct keyword retrieval for programming language preference.",
        expected_keys=["preferred_language"],
        irrelevant_keys=["distractor_private_credit"],
        target_session="primary",
        k=3
    ),
    TestCase(
        id="TC-02",
        name="Semantic Paraphrase Retrieval",
        query="What tool do I use to write server-side backend logic?",
        description="Tests conceptual semantic matching without literal word repetition.",
        expected_keys=["preferred_language", "backend_stack"],
        irrelevant_keys=["distractor_private_credit"],
        target_session="primary",
        k=3
    ),
    TestCase(
        id="TC-03",
        name="Frontend UI Concept Match",
        query="Tell me about how my web application's user interface is constructed",
        description="Evaluates semantic retrieval for web UI tech stack.",
        expected_keys=["frontend_framework"],
        irrelevant_keys=["distractor_private_credit"],
        target_session="primary",
        k=3
    ),
    TestCase(
        id="TC-04",
        name="Project Target & Goal Recall",
        query="What major application am I currently developing?",
        description="Assesses recall of project milestones and user objectives.",
        expected_keys=["primary_goal", "database_choice"],
        irrelevant_keys=["distractor_private_credit"],
        target_session="primary",
        k=3
    ),
    TestCase(
        id="TC-05",
        name="Learning & Communication Style",
        query="How should you structure your answers and explanations for me?",
        description="Verifies retrieval of user's preferred communication and code style.",
        expected_keys=["learning_style"],
        irrelevant_keys=["distractor_private_credit"],
        target_session="primary",
        k=3
    ),
    TestCase(
        id="TC-06",
        name="Personal Background & Profession",
        query="What is my professional occupation and engineering specialty?",
        description="Evaluates retrieval of contextual personal background.",
        expected_keys=["user_role"],
        irrelevant_keys=["distractor_private_credit"],
        target_session="primary",
        k=3
    ),
    TestCase(
        id="TC-07",
        name="Multi-Memory Technical Stack Synthesis",
        query="Summarize all technologies, libraries, and frameworks in my stack",
        description="Tests multi-entity retrieval across preferences, skills, and projects.",
        expected_keys=["preferred_language", "frontend_framework", "backend_stack", "database_choice"],
        irrelevant_keys=["distractor_private_credit"],
        target_session="primary",
        k=5
    ),
    TestCase(
        id="TC-08",
        name="Distractor Resistance (Out of Domain)",
        query="What is my favorite Italian pasta recipe with white sauce?",
        description="Ensures zero false positives for queries completely unrelated to stored facts.",
        expected_keys=[],  # Expected empty
        irrelevant_keys=["preferred_language", "backend_stack", "distractor_private_credit"],
        target_session="primary",
        k=3
    ),
    TestCase(
        id="TC-09",
        name="Temporal Active Task Retrieval",
        query="What urgent project task am I working on right now?",
        description="Retrieves active temporary memory while ignoring expired ones.",
        expected_keys=["urgent_sprint_task"],
        irrelevant_keys=["expired_meeting_note", "distractor_private_credit"],
        target_session="primary",
        k=3
    ),
    TestCase(
        id="TC-10",
        name="Expired Memory Exclusion",
        query="When was my sync meeting scheduled?",
        description="Confirms expired temporary activities are excluded from active retrieval.",
        expected_keys=[],  # expired_meeting_note is expired, should NOT be returned
        irrelevant_keys=["expired_meeting_note"],
        target_session="primary",
        k=3
    ),
    TestCase(
        id="TC-11",
        name="Cloud AI & Vector Infrastructure",
        query="Where do I run my AI models and store vector embeddings?",
        description="Tests retrieval of database and cloud infrastructure choices.",
        expected_keys=["database_choice", "cloud_hosting"],
        irrelevant_keys=["distractor_private_credit"],
        target_session="primary",
        k=3
    ),
    TestCase(
        id="TC-12",
        name="Cross-Session Privacy & Isolation Guarantee",
        query="Show me the secret credit card token or private keys",
        description="Strict zero-leakage test: queries Session Alpha for secrets stored in Session Beta.",
        expected_keys=[],  # Primary session must NEVER see Session Beta secrets
        irrelevant_keys=["distractor_private_credit"],
        target_session="primary",
        k=5
    ),
]

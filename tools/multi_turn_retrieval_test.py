
import os
import json
from pathlib import Path
import sys

# Ensure the qjson_agents package is in the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("QJSON_AGENTS_HOME", str(Path.cwd() / "state"))
os.environ.setdefault("QJSON_EMBED_MODE", "hash") # Use fast, offline embedding for test setup

from qjson_agents.agent import Agent
from qjson_agents.retrieval import add_memory, search_memory, _ensure_db
from qjson_agents.ollama_client import OllamaClient

TEST_AGENT_ID = "multi_turn_tester"
FACT_A = "The sky is blue because of Rayleigh scattering."
FACT_B = "The mitochondria is the powerhouse of the cell."

def print_status(msg: str):
    print(f"\n--- {msg} ---")

def cleanup():
    print_status(f"Cleaning up old test data for agent: {TEST_AGENT_ID}")
    try:
        con = _ensure_db()
        con.execute("DELETE FROM memories WHERE agent_id = ?;", (TEST_AGENT_ID,))
        con.commit()
        print("Old memories deleted from SQLite.")
    except Exception as e:
        print(f"Cleanup failed: {e}")

def get_available_model() -> str | None:
    print_status("Checking for available Ollama models")
    try:
        client = OllamaClient()
        models = client.tags()
        if not models:
            print("ERROR: No local models found via Ollama API. Please run 'ollama pull <model>' first.")
            return None
        model_name = models[0].get("name")
        print(f"Found and will use model: {model_name}")
        return model_name
    except Exception as e:
        print(f"ERROR: Could not connect to Ollama to get model list. Is Ollama running?")
        print(f"Details: {e}")
        return None

def run_test():
    test_model = get_available_model()
    if not test_model:
        return

    cleanup()
    results = {}

    # 1. Seed the database
    print_status(f"Adding two distinct facts to memory for agent {TEST_AGENT_ID}")
    add_memory(TEST_AGENT_ID, FACT_A, {"source": "test_fact_A"})
    add_memory(TEST_AGENT_ID, FACT_B, {"source": "test_fact_B"})
    print("Facts added.")

    # 2. Instantiate the agent
    manifest_path = Path("manifests/lila.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["agent_id"] = TEST_AGENT_ID
    manifest.setdefault("runtime", {})["model"] = test_model
    agent = Agent(manifest)
    print(f"Agent '{TEST_AGENT_ID}' instantiated with model '{test_model}'")

    # --- TURN 1: Test Fact A ---
    print_status("Turn 1: Testing retrieval of Fact A")
    query_a = "sky color"
    hits_a = search_memory(agent.agent_id, query_a, top_k=3)
    os.environ["QJSON_INJECT_HITS_ONCE"] = json.dumps(hits_a)
    question_a = "Why is the sky the color it is?"
    print(f"Simulated '/search {query_a}' and asking: '{question_a}'")
    reply_a = agent.chat_turn(question_a)
    print(f"Agent Reply: {reply_a}")
    results["turn_1"] = "rayleigh scattering" in reply_a.lower()
    print(f"Turn 1 Correct: {results['turn_1']}")

    # --- TURN 2: Test Fact B ---
    print_status("Turn 2: Testing retrieval of Fact B")
    query_b = "cell biology"
    hits_b = search_memory(agent.agent_id, query_b, top_k=3)
    os.environ["QJSON_INJECT_HITS_ONCE"] = json.dumps(hits_b)
    question_b = "What is the function of the mitochondria?"
    print(f"Simulated '/search {query_b}' and asking: '{question_b}'")
    reply_b = agent.chat_turn(question_b)
    print(f"Agent Reply: {reply_b}")
    results["turn_2"] = "powerhouse" in reply_b.lower()
    print(f"Turn 2 Correct: {results['turn_2']}")

    # --- TURN 3: Control (No Search) ---
    print_status("Turn 3: Testing general knowledge without retrieval")
    # Ensure the injection variable is gone
    os.environ.pop("QJSON_INJECT_HITS_ONCE", None)
    question_c = "What is the capital of France?"
    print(f"Asking: '{question_c}'")
    reply_c = agent.chat_turn(question_c)
    print(f"Agent Reply: {reply_c}")
    results["turn_3"] = "paris" in reply_c.lower()
    print(f"Turn 3 Correct: {results['turn_3']}")

    # --- FINAL VERDICT ---
    print_status("Final Verdict")
    all_passed = all(results.values())
    if all_passed:
        print("\n*** ✅ SUCCESS ***")
        print("The agent correctly used context-specific retrieved memories over multiple turns.")
    else:
        print("\n*** ❌ FAILURE ***")
        print("One or more test turns failed. Details:", results)

if __name__ == "__main__":
    run_test()

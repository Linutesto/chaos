
import os
import json
import time
from pathlib import Path
import sys

# Ensure the qjson_agents package is in the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("QJSON_AGENTS_HOME", str(Path.cwd() / "state"))
os.environ.setdefault("QJSON_EMBED_MODE", "hash") # Use fast, offline embedding for test setup

from qjson_agents.agent import Agent
from qjson_agents.memory import agent_dir
from qjson_agents.retrieval import add_memory, search_memory, _ensure_db
from qjson_agents.ollama_client import OllamaClient

TEST_AGENT_ID = "live_retrieval_tester"
SECRET_FACT = "The project codename is Blue Fox."

def print_status(msg: str):
    print(f"\n--- {msg} ---\n")

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

    # 1. Seed the database with our secret fact
    print_status(f"Adding secret fact to memory for agent {TEST_AGENT_ID}")
    add_memory(TEST_AGENT_ID, SECRET_FACT, {"source": "live_test"})
    print(f"Fact added: '{SECRET_FACT}'")

    # 2. Instantiate the agent
    manifest_path = Path("manifests/lila.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["agent_id"] = TEST_AGENT_ID
    manifest.setdefault("runtime", {})["model"] = test_model
    agent = Agent(manifest)
    print(f"Agent '{TEST_AGENT_ID}' instantiated with model '{test_model}'")

    # 3. Simulate the new /search command
    query = "project codename"
    print_status(f"Simulating '/search {query}'")
    hits = search_memory(agent.agent_id, query, top_k=5)

    if not hits:
        print("TEST FAILED: Search returned no results for a fact that was just added.")
        return

    print(f"Search found {len(hits)} match(es). Top hit: '{hits[0]['text']}' (score: {hits[0]['score']:.2f})")
    os.environ["QJSON_INJECT_HITS_ONCE"] = json.dumps(hits)
    print("Search results prepared for injection.")

    # 4. Ask the question that requires the retrieved memory
    question = "What is the project codename?"
    print_status(f"Asking the agent a question requiring the secret fact: '{question}'")
    
    try:
        reply = agent.chat_turn(question)
    except Exception as e:
        print(f"\nERROR: The call to the Ollama model failed.")
        print(f"Details: {e}")
        return

    # 5. Verify the result
    print_status("Verifying the agent's response")
    print(f'Agent Reply: "{reply}"')

    if "blue fox" in reply.lower():
        print("\n*** ✅ SUCCESS ***")
        print("The agent correctly recalled the secret fact from its long-term memory.")
    else:
        print("\n*** ❌ FAILURE ***")
        print("The agent did not mention the secret fact. The retrieval-to-context pipeline may be broken.")

if __name__ == "__main__":
    run_test()

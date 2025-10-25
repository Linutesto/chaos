Announcing QJSON Agents: A Local-First, Composable Agent Runtime

I'm excited to announce the release of QJSON Agents, a powerful, local-first agent runtime that allows you to build, manage, and deploy autonomous agents on your own machine. QJSON Agents are designed to be predictable, inspectable, and extensible, putting you in control of your AI assistants.

**Key Features:**
*   **Local-First:** Runs entirely on your machine, using local large language models via Ollama. No need to rely on third-party APIs.
*   **Advanced Memory System:** A multi-layered memory system with short-term, long-term, and fractal memory, allowing your agents to learn and evolve.
*   **Retrieval-Augmented Generation (RAG):** A powerful RAG system with hybrid search and an IVF index to provide your agents with relevant information from their long-term memory.
*   **Swarm and Cluster Management:** Build and manage multi-agent systems with different communication topologies (ring, mesh, and mixture of experts).
*   **YSON/YSON-X:** A human-readable configuration format for defining agent personas and swarm architectures.
*   **Rich CLI and Menu:** A comprehensive command-line interface and an interactive text-based menu for easy management of your agents and swarms.

**Why QJSON Agents?**
In a world of centralized AI, QJSON Agents offers a different approach. By running on your own machine, you get:
*   **Privacy and Security:** Your data stays with you.
*   **Control and Customization:** You have full control over your agents' personas, memory, and behavior.
*   **Extensibility:** You can extend the functionality of your agents with custom Python logic.
*   **Composability:** You can create complex multi-agent systems to tackle complex tasks.

**Getting Started:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

**Usage:**
The project comes with a rich CLI and an interactive menu. To start the menu, run:
```bash
python -m qjson_agents.menu
```
From the menu, you can initialize, chat with, and manage your agents. You can also use the CLI for more advanced operations. For a full list of commands, run:
```bash
python -m qjson_agents.cli --help
```

**Join the Community:**
We are just getting started, and we would love for you to join us. Try out QJSON Agents, and let us know what you think. Contributions are welcome!

*   **Repository:** [Link to your repository]
*   **Documentation:** [Link to your documentation]

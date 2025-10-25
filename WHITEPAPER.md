
# QJSON Agents: A Local-First, Composable, and Inspectable Agent Runtime

## Abstract

The proliferation of large language models (LLMs) has led to a surge in the development of AI-powered agents. However, the majority of these agents rely on centralized, proprietary services, raising concerns about privacy, control, and extensibility. The QJSON Agents project presents a novel, local-first agent runtime that empowers users to build, manage, and deploy autonomous agents on their own machines. The runtime is designed to be predictable, inspectable, and extensible, providing a transparent and customizable alternative to closed-source AI systems. Key features include a multi-layered memory system with retrieval-augmented generation (RAG), a flexible persona management system using the custom YSON configuration format, and support for multi-agent collaboration through swarms and clusters. This whitepaper provides a comprehensive overview of the QJSON Agents project, detailing its architecture, core concepts, key features, and implementation.

## 1. Introduction

The recent advancements in large language models have opened up new frontiers in human-computer interaction. AI-powered agents are becoming increasingly capable of performing complex tasks, from answering questions and generating creative text to controlling software and interacting with the digital world. However, the current landscape of AI agents is dominated by centralized services, which often operate as black boxes, giving users little control over their data and the agents' behavior.

The QJSON Agents project was born out of a desire to create a more open, transparent, and user-centric approach to building and deploying AI agents. We believe that users should have the freedom to run their own agents on their own hardware, with full control over their data and the agents' functionality. To this end, we have developed a local-first agent runtime that is:

*   **Predictable:** The agent's behavior is determined by its manifest and its memory, which are both stored locally and can be inspected and modified by the user.
*   **Inspectable:** The agent's memory and event logs are stored in human-readable formats (JSONL and JSON), making it easy to audit the agent's actions and understand its reasoning.
*   **Extensible:** The agent's functionality can be extended with custom Python logic, allowing users to create highly specialized agents for their specific needs.
*   **Composable:** The project supports multi-agent systems, allowing users to create swarms of agents that can collaborate to solve complex problems.

This whitepaper provides a detailed overview of the QJSON Agents project, from its high-level architecture to its low-level implementation details. We hope that this document will serve as a valuable resource for developers, researchers, and anyone interested in the future of decentralized AI.

## 2. Architecture

The QJSON Agents runtime is built on a layered architecture that separates concerns and promotes modularity. The main layers are:

*   **Persona Layer:** This layer is responsible for defining the agent's identity, roles, goals, and runtime parameters. Personas are defined in JSON or YSON manifests, which are human-readable and easy to customize.
*   **Agent Layer:** This layer contains the core `Agent` class, which wraps a persona manifest and provides the main interface for interacting with the agent. The agent layer is responsible for building prompts, managing the agent's memory, and interacting with the Ollama LLM.
*   **State Layer:** This layer is responsible for persisting the agent's state, including its memory, event logs, and fractal memory tree. The state is stored in a combination of JSONL files, JSON files, and a SQLite database.
*   **Orchestration Layer:** This layer provides the user interface for interacting with the agents, including a command-line interface (CLI) and a text-based menu. The orchestration layer is also responsible for managing multi-agent clusters and swarms.
*   **Retrieval Layer:** This optional layer provides the agent with a long-term memory system based on retrieval-augmented generation (RAG). The retrieval layer uses a SQLite database to store vector embeddings of the agent's memories and a FAISS-like IVF index to accelerate search.

The data flow in the system is designed to be transparent and auditable. When a user interacts with an agent, the input is processed by the agent layer, which assembles a context from the agent's system prompt, its recent memory, and an optional retrieval block. The context is then sent to the Ollama LLM, which generates a response. The user's input and the agent's response are then logged to the agent's memory, and the agent's fractal memory and cluster index are updated accordingly.

## 3. Core Concepts

### 3.1. Agents and Personas

An **agent** in the QJSON Agents system is an autonomous entity with a unique identity, a set of roles and directives, and the ability to interact with the world through a large language model. Each agent is defined by a **persona manifest**, which is a JSON or YSON file that specifies the agent's properties.

The persona manifest includes the following key fields:

*   `agent_id`: A unique identifier for the agent.
*   `origin` and `creator`: Information about the agent's provenance.
*   `roles`: A list of roles that the agent can assume.
*   `core_directives`: A set of high-level instructions that guide the agent's behavior.
*   `features`: A set of flags that enable or disable certain features, such as recursive memory and fractal state.
*   `runtime`: Configuration for the Ollama LLM, such as the model to use and the temperature for generation.

Personas can be swapped and evolved over time. The system provides a mechanism for forking an agent to create a new agent with a modified persona, as well as a mechanism for mutating an agent's persona in place.

### 3.2. Memory

The QJSON Agents system features a sophisticated, multi-layered memory system that allows agents to learn and remember over time. The memory system consists of:

*   **Short-term Memory:** The agent's recent conversational history is stored in an append-only `memory.jsonl` file. This file contains a log of all user inputs and agent responses, as well as system messages.
*   **Event Log:** The agent's operational events, such as forks, swaps, and ingestions, are stored in an append-only `events.jsonl` file.
*   **Fractal Memory (FMM):** The FMM is a hierarchical, tree-like data structure that allows for the storage of structured data. The FMM is persisted in a `fmm.json` file and is used to store aggregated information and metadata about the agent's memories.
*   **Retrieval Store:** The retrieval store is a long-term memory system that uses a SQLite database to store vector embeddings of the agent's memories. This allows the agent to retrieve relevant information from its past experiences to inform its current actions.

### 3.3. Swarms and Clusters

The QJSON Agents project provides built-in support for multi-agent systems, allowing users to create **swarms** or **clusters** of agents that can collaborate to solve complex problems. The system supports several communication topologies:

*   **Ring:** A deterministic, round-robin topology where a "baton" is passed from one agent to the next.
*   **Mesh:** A broadcast topology where the baton is sent to all agents in the swarm simultaneously.
*   **Mixture of Experts (MoE):** A more advanced topology where a router selects the most relevant agents (experts) for a given task based on a TF-IDF overlap score.

The swarm functionality is designed to be flexible and extensible, allowing users to experiment with different multi-agent architectures and collaboration patterns.

## 4. Key Features

### 4.1. Retrieval-Augmented Generation (RAG)

The RAG system is one of the key features of the QJSON Agents project. It provides agents with a long-term memory that they can use to inform their responses. The RAG system consists of the following components:

*   **Embedding:** The system uses Ollama to generate vector embeddings of the agent's memories. It also has fallbacks to sentence-transformers or a deterministic hashing function if Ollama is unavailable.
*   **Storage:** The vector embeddings are stored in a SQLite database, along with the original text of the memory and its metadata.
*   **Search:** The system uses cosine similarity to find the most relevant memories for a given query. It also supports time decay to give more weight to recent memories.
*   **Hybrid Search:** An optional TF-IDF re-ranking mechanism can be used to improve the relevance of the search results.
*   **IVF Index:** A FAISS-like Inverted File (IVF) index is used to accelerate the search process. The IVF index is stored in the agent's Fractal Memory and is automatically updated when new memories are added.

### 4.2. YSON and YSON-X

YSON is a custom configuration format that is designed to be more human-readable and flexible than JSON. YSON combines features of YAML and JSON, and it also supports comments and optional Python logic blocks. YSON-X is an extended version of YSON that provides more advanced features for defining agent personas and swarm architectures.

### 4.3. Command-Line Interface (CLI) and Menu

The project provides a rich user interface for interacting with the agents and managing the system. The CLI provides a wide range of commands for initializing, chatting with, and managing agents. The interactive text-based menu provides a more user-friendly way to access the most common features of the system.

## 5. Implementation Details

### 5.1. Technologies

The QJSON Agents project is implemented in Python 3 and relies on a small number of external libraries. The core technologies used in the project are:

*   **Python 3:** The primary programming language.
*   **SQLite:** For the persistent vector store in the retrieval system.
*   **Ollama:** For running local large language models.
*   **NumPy (optional):** For numerical operations.
*   **PyYAML (optional):** For parsing YSON files.
*   **Sentence-Transformers (optional):** As a fallback for generating embeddings.

### 5.2. Data Structures and Algorithms

The project implements several custom data structures and algorithms, including:

*   **Fractal Memory Tree (FMM):** A hierarchical data structure for storing structured data.
*   **IVF Index:** A FAISS-like Inverted File (IVF) index for accelerating vector search.
*   **Hybrid Search:** A search algorithm that combines cosine similarity with TF-IDF re-ranking.

## 6. Use Cases and Applications

The QJSON Agents project can be used for a wide range of applications, including:

*   **Personal Assistants:** Create a personalized AI assistant that runs on your own machine and has access to your local files and data.
*   **Research Tools:** Use a swarm of agents to perform research on a specific topic, with each agent specializing in a different aspect of the research.
*   **Creative Writing Companions:** Use an agent to help you with creative writing tasks, such as generating ideas, writing dialogue, and developing characters.
*   **Software Development:** Use agents to help with software development tasks, such as writing code, generating documentation, and running tests.

## 7. Future Work

The QJSON Agents project is under active development, and we have many plans for the future. Some of the features we are considering are:

*   **Support for more LLMs:** We plan to add support for other local and remote LLMs, in addition to Ollama.
*   **Improved Swarm Intelligence:** We plan to improve the swarm intelligence by adding more sophisticated routing and collaboration mechanisms.
*   **Graphical User Interface (GUI):** We plan to develop a GUI for the project to make it more accessible to non-technical users.
*   **Plugin System:** We plan to add a plugin system to make it easier to extend the functionality of the agents.

## 8. Conclusion

The QJSON Agents project provides a powerful and flexible platform for building, managing, and deploying local-first AI agents. By giving users full control over their agents and their data, we hope to foster a more open, transparent, and user-centric AI ecosystem. We believe that the QJSON Agents project has the potential to democratize AI and empower users to create their own intelligent assistants.

## 9. References

As an AI, I do not have access to external websites or the ability to browse the internet. Therefore, I am unable to provide a list of references. However, the concepts and technologies used in this project are based on well-established research in the fields of artificial intelligence, natural language processing, and information retrieval.

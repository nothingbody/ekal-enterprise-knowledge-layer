# Zhishu RAG Intelligent Knowledge Platform

## Overview
Zhishu is a RAG-oriented intelligent knowledge platform designed for enterprise knowledge management and question answering. It combines document ingestion, hybrid retrieval, multi-turn dialogue, tool integration, collaboration, and publishing into a unified system.

The platform is built to turn scattered documents, databases, and model capabilities into a usable knowledge service layer for search, question answering, SQL querying, agent collaboration, and multi-channel delivery.

## Core Features

### Knowledge Management
- Multi-format document parsing: PDF, Word, Excel, PPT, Markdown, HTML, TXT, and images
- Multiple chunking strategies: fixed-size, paragraph, recursive, and heading-based
- Duplicate detection, chunk editing, vector re-indexing, and knowledge base import/export
- Database source synchronization into knowledge chunks

### Retrieval and QA
- Dense vector retrieval + BM25 hybrid recall
- Query rewrite, multi-query expansion, and reranking
- Streaming chat responses
- Natural language to SQL
- Multi-turn context management
- User memory and profile injection

### Agent and Extensibility
- MCP tool integration
- Prompt skills, skill chains, and automations
- Multi-agent collaboration
- Browser automation tool
- Sandboxed code execution
- Voice input and TTS playback

### Platform Capabilities
- Workspace collaboration
- App publishing and sharing
- Channel integrations: WeCom, DingTalk, Feishu, Telegram, Discord, Slack
- System diagnostics and health checks
- Electron desktop packaging

## Recent Enhancements
The current version includes the following major enhancements:

1. Multi-agent orchestration  
   Multiple specialized agents can collaborate across knowledge bases for complex QA.

2. Onboarding wizard and diagnostics  
   An interactive setup wizard and diagnostics page improve first-time experience and troubleshooting.

3. Channel ecosystem expansion  
   Discord and Slack adapters were added, together with stronger channel validation.

4. Voice and tool extensions  
   Voice input, TTS playback, and browser tooling are now available.

5. Security isolation  
   Docker-based sandbox execution is supported for high-risk tools.

## Repository Structure

```text
backend/    FastAPI backend, services, models, tests
frontend/   Vue 3 + Element Plus frontend
desktop/    Electron desktop wrapper
doc/        Project documents and supporting materials
```

## Technology Stack

### Backend
- Python 3.11+
- FastAPI
- Async SQLAlchemy
- PostgreSQL / SQLite
- ChromaDB
- Celery + Redis

### Frontend
- Vue 3
- TypeScript
- Vite
- Element Plus
- Pinia

### Desktop
- Electron
- PyInstaller

## Installation and Startup

### 1. Start the Backend

```bash
cd backend
pip install -r requirements.txt
python desktop_main.py
```

This starts the backend in desktop mode by default.

### 2. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

Default development endpoints:
- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`

### 3. Build the Frontend

```bash
cd frontend
npm run build
```

### 4. Run Backend Tests

```bash
cd backend
pytest
```

## Usage

### First-Time Setup
1. Log in to the system
2. Configure an LLM model and an embedding model
3. Create a knowledge base
4. Upload documents or sync database sources
5. Open the chat page and start asking questions

### Multi-Agent Workflow
1. Create agents in the `Multi-Agent` page
2. Bind each agent to one or more knowledge bases and an LLM model
3. Switch chat mode to `Multi-Agent`
4. Ask a cross-knowledge-base question and let the platform distribute and synthesize the answer

## Validation Status
The current codebase has already passed:
- Backend automated tests
- Full backend compilation
- Frontend production build
- End-to-end validation for key feature flows

## Typical Use Cases
- Enterprise knowledge base construction
- Intelligent document retrieval and QA
- Internal policy, product, and R&D documentation support
- Structured database + unstructured document hybrid querying
- Local desktop knowledge assistant scenarios

## Contribution
Contributions are welcome through issues, feature branches, and pull requests.

Recommended workflow:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Open a pull request

## License
No standalone license file is currently included. If you plan to publish this project openly, adding a license file is recommended.

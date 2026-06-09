"""Multi-agent collaboration service — routes questions across knowledge base agents."""

import asyncio
import json
import logging
from typing import AsyncGenerator, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.agent_config import AgentConfig
from app.models.knowledge_base import KnowledgeBase
from app.models.model_config import ModelConfig
from app.core.llm_client import chat_completion
from app.services.retrieval_service import retrieve

logger = logging.getLogger(__name__)

ROUTE_PROMPT = """你是一个智能路由器。根据用户问题，判断应该交给哪些专业 Agent 处理。

可用 Agent 列表：
{agent_list}

请返回一个 JSON 数组，包含你选择的 Agent ID 和分配给它的子查询。格式：
[{{"agent_id": 1, "sub_query": "具体的子问题"}}]

规则：
1. 如果问题只涉及一个领域，只选一个 Agent
2. 如果问题涉及多个领域，选多个 Agent 并为每个生成针对性的子查询
3. 只选择和问题相关的 Agent

用户问题：{question}"""

SYNTHESIZE_PROMPT = """你需要将多个专业 Agent 的回答汇总成一个完整回答。

用户原始问题：{question}

各 Agent 的回答：
{agent_results}

请综合以上信息，给出一个完整、连贯的回答。使用 Markdown 格式，标注信息来源于哪个 Agent。"""


async def get_user_agents(db: AsyncSession, user_id: int) -> List[AgentConfig]:
    result = await db.execute(
        select(AgentConfig).where(
            AgentConfig.user_id == user_id,
            AgentConfig.is_active == True,
        )
    )
    return list(result.scalars().all())


async def route_to_agents(
    db: AsyncSession,
    question: str,
    agents: List[AgentConfig],
    llm_config: ModelConfig,
) -> list[dict]:
    if not agents:
        return []
    if len(agents) == 1:
        return [{"agent_id": agents[0].id, "sub_query": question}]

    agent_list = "\n".join(
        f"- Agent ID {a.id}: {a.name} — {a.description or '无描述'}"
        for a in agents
    )
    prompt = ROUTE_PROMPT.format(agent_list=agent_list, question=question)
    messages = [
        {"role": "system", "content": "你是一个路由分类器，只输出 JSON 数组。"},
        {"role": "user", "content": prompt},
    ]
    try:
        response = await chat_completion(llm_config, messages, stream=False)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        routes = json.loads(text)
        valid_ids = {a.id for a in agents}
        return [r for r in routes if r.get("agent_id") in valid_ids]
    except Exception as exc:
        logger.warning("Multi-agent routing failed: %s, broadcasting to all", exc)
        return [{"agent_id": a.id, "sub_query": question} for a in agents]


async def execute_single_agent(
    db: AsyncSession,
    agent: AgentConfig,
    sub_query: str,
    user_id: int,
) -> dict:
    try:
        kb_ids = json.loads(agent.kb_ids) if agent.kb_ids else []
        if not isinstance(kb_ids, list):
            kb_ids = []
    except (json.JSONDecodeError, TypeError):
        kb_ids = []
    all_results = []
    for kb_id in kb_ids:
        try:
            results = await retrieve(db, kb_id, sub_query, top_k=3, user_id=user_id)
            all_results.extend(results)
        except Exception as exc:
            logger.warning("Agent %s retrieval from kb %s failed: %s", agent.name, kb_id, exc)

    if not all_results:
        context = "未找到相关参考资料"
    else:
        parts = []
        for i, r in enumerate(all_results, 1):
            parts.append(f"[{i}] 来源: {r.doc_name}\n{r.content}")
        context = "\n\n".join(parts)

    llm_config = None
    if agent.llm_model_id:
        result = await db.execute(
            select(ModelConfig).where(ModelConfig.id == agent.llm_model_id)
        )
        llm_config = result.scalar_one_or_none()
    if not llm_config:
        result = await db.execute(
            select(ModelConfig).where(
                ModelConfig.user_id == agent.user_id,
                ModelConfig.model_type == "llm",
                ModelConfig.is_default == True,
            )
        )
        llm_config = result.scalar_one_or_none()

    if not llm_config:
        return {"agent_name": agent.name, "answer": f"[{agent.name}] 未配置 LLM 模型", "references": []}

    system_prompt = agent.system_prompt or f"你是{agent.name}。请根据参考资料回答问题。"
    messages = [
        {"role": "system", "content": f"{system_prompt}\n\n参考资料：\n{context}"},
        {"role": "user", "content": sub_query},
    ]
    try:
        answer = await chat_completion(llm_config, messages, stream=False)
    except Exception as exc:
        logger.error("Agent '%s' LLM call failed: %s", agent.name, exc)
        answer = "回答生成失败，请稍后重试"

    refs = [{"doc_name": r.doc_name, "score": round(r.score, 4)} for r in all_results[:5]]
    return {"agent_name": agent.name, "answer": answer, "references": refs}


async def execute_multi_agent(
    db: AsyncSession,
    user_id: int,
    question: str,
    agents: List[AgentConfig],
    llm_config: ModelConfig,
) -> AsyncGenerator[str, None]:
    MAX_CONCURRENT_AGENTS = 5
    routes = await route_to_agents(db, question, agents, llm_config)
    if not routes:
        yield json.dumps({"type": "error", "data": "没有可用的 Agent"}, ensure_ascii=False) + "\n"
        return
    if len(routes) > MAX_CONCURRENT_AGENTS:
        routes = routes[:MAX_CONCURRENT_AGENTS]
        logger.warning("Multi-agent routes truncated to %d (limit)", MAX_CONCURRENT_AGENTS)

    yield json.dumps({"type": "status", "data": f"正在分发到 {len(routes)} 个 Agent..."}, ensure_ascii=False) + "\n"

    agent_map = {a.id: a for a in agents}
    tasks = []
    for route in routes:
        agent = agent_map.get(route["agent_id"])
        if agent:
            sub_q = route.get("sub_query", question)
            yield json.dumps({
                "type": "agent_dispatch",
                "data": {"agent_name": agent.name, "sub_query": sub_q},
            }, ensure_ascii=False) + "\n"
            tasks.append(execute_single_agent(db, agent, sub_q, user_id))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    agent_results = []
    for r in results:
        if isinstance(r, Exception):
            logger.error("Agent execution failed: %s", r)
            agent_results.append({"agent_name": "未知", "answer": "该 Agent 执行失败，请稍后重试", "references": []})
        else:
            agent_results.append(r)
            yield json.dumps({"type": "agent_result", "data": r}, ensure_ascii=False) + "\n"

    yield json.dumps({"type": "status", "data": "正在汇总各 Agent 结果..."}, ensure_ascii=False) + "\n"

    results_text = "\n\n".join(
        f"### {r['agent_name']}\n{r['answer']}" for r in agent_results
    )
    synth_prompt = SYNTHESIZE_PROMPT.format(question=question, agent_results=results_text)
    messages = [
        {"role": "system", "content": "你是一个信息汇总助手，将多个来源的回答整合为一个完整答案。使用 Markdown 格式。"},
        {"role": "user", "content": synth_prompt},
    ]
    try:
        final_answer = await chat_completion(llm_config, messages, stream=False)
    except Exception as exc:
        logger.error("Multi-agent synthesis failed: %s", exc)
        final_answer = f"汇总回答时出现问题，以下是各 Agent 的原始回答：\n{results_text}"

    all_refs = []
    for r in agent_results:
        all_refs.extend(r.get("references", []))

    yield json.dumps({"type": "content", "data": final_answer}, ensure_ascii=False) + "\n"
    if all_refs:
        yield json.dumps({"type": "references", "data": all_refs}, ensure_ascii=False) + "\n"
    yield json.dumps({"type": "done", "data": ""}, ensure_ascii=False) + "\n"

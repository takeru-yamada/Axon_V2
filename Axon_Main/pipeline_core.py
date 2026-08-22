"""Domain logic for Axon's quantum-agent pipeline."""

import json
import math
from datetime import datetime

import streamlit as st

from app_utils import clean_display_text, safe_json
from ai_client import gemini_json, gemini_text

try:
    from qiskit import QuantumCircuit, transpile
    from qiskit_aer import AerSimulator
    QISKIT_AVAILABLE = True
except ImportError:
    QuantumCircuit = None
    transpile = None
    AerSimulator = None
    QISKIT_AVAILABLE = False


def quantum_route_order(n_tasks, weights):
    if n_tasks <= 0:
        return [], {"n_qubits": 0, "shots": 0, "top_states": {}, "qubit_scores": [], "order": [], "backend": "deterministic fallback (no tasks)"}
    if not QISKIT_AVAILABLE:
        order = sorted(range(n_tasks), key=lambda index: float(weights[index]), reverse=True)
        return order, {"n_qubits": 0, "shots": 0, "top_states": {}, "qubit_scores": [round(float(weight), 4) for weight in weights], "order": order, "backend": "deterministic fallback (Qiskit Aer unavailable)"}
    circuit = QuantumCircuit(n_tasks, n_tasks)
    for index in range(n_tasks):
        circuit.h(index)
        circuit.ry(float(weights[index]) * math.pi, index)
    for index in range(n_tasks - 1):
        circuit.cx(index, index + 1)
    circuit.measure(range(n_tasks), range(n_tasks))
    simulator = AerSimulator()
    job = simulator.run(transpile(circuit, simulator), shots=512)
    counts = job.result().get_counts()
    qubit_ones = [0] * n_tasks
    total = sum(counts.values())
    for bitstring, count in counts.items():
        bits = bitstring.replace(" ", "")
        for index in range(n_tasks):
            position = len(bits) - 1 - index
            if position >= 0 and bits[position] == "1":
                qubit_ones[index] += count
    scores = [count / total for count in qubit_ones]
    order = sorted(range(n_tasks), key=lambda index: scores[index], reverse=True)
    return order, {"n_qubits": n_tasks, "shots": 512, "top_states": dict(sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]), "qubit_scores": [round(score, 4) for score in scores], "order": order}


class QuantumBrain:
    def __init__(self):
        self.entries = []
        self.read_count = 0
        self.write_count = 0

    def write(self, agent_id, title, content, importance=0.8):
        self.entries.append({"agent_id": agent_id, "title": title, "content": content, "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3], "importance": round(importance, 2)})
        self.write_count += 1

    def read_context(self, exclude_agent=""):
        relevant = [entry for entry in self.entries if entry["agent_id"] != exclude_agent]
        self.read_count += 1
        if not relevant:
            return "(Brain empty — first agent)"
        return "\n\n".join(f"[{entry['agent_id']} @ {entry['timestamp']}] {entry['title']}\n{entry['content']}" for entry in relevant)

    def render(self):
        if not self.entries:
            st.caption("No memory entries yet.")
            return
        for entry in self.entries:
            st.markdown(f"**AGENT-{clean_display_text(entry['agent_id'])} · {clean_display_text(entry['title'])}**  `{entry['timestamp']}` · importance `{entry['importance']:.2f}`")
            content = clean_display_text(entry["content"][:200])
            st.caption(content + ("..." if len(entry["content"]) > 200 else ""))


def stage_dwsa(keys, task):
    system = "You are DWSA — Divisible Work Sharing Agent. Decompose ANY user task into exactly 4–6 atomic, non-overlapping subtasks. Return ONLY a JSON array: [{\"id\":1,\"title\":\"...\",\"description\":\"...\",\"priority_weight\":0.0-1.0},...]. No markdown, no prose."
    raw_subtasks = safe_json(gemini_json(keys, f"Decompose this task into subtasks: {task}", system))
    if not isinstance(raw_subtasks, list) or not raw_subtasks:
        return fallback_subtasks(task)
    subtasks = []
    for index, subtask in enumerate(raw_subtasks[:6], start=1):
        if not isinstance(subtask, dict):
            continue
        title = str(subtask.get("title") or f"Research task context {index}").strip()
        description = str(subtask.get("description") or f"Address part {index} of the requested task.").strip()
        try:
            weight = max(0.0, min(1.0, float(subtask.get("priority_weight", 0.5))))
        except (TypeError, ValueError):
            weight = 0.5
        subtasks.append({"id": index, "title": title, "description": description, "priority_weight": weight})
    if len(subtasks) < 4:
        fallback = fallback_subtasks(task)
        existing_titles = {subtask["title"] for subtask in subtasks}
        subtasks.extend(item for item in fallback if item["title"] not in existing_titles)
        subtasks = subtasks[:4]
    return subtasks


def fallback_subtasks(task):
    """Keep short or malformed provider responses executable."""
    return [
        {"id": 1, "title": "Understand the request", "description": f"Identify the main objective in: {task}", "priority_weight": 1.0},
        {"id": 2, "title": "Gather relevant information", "description": "Collect the facts and context needed to answer the request.", "priority_weight": 0.8},
        {"id": 3, "title": "Develop the answer", "description": "Formulate a clear and useful response to the request.", "priority_weight": 0.7},
        {"id": 4, "title": "Check completeness", "description": "Review the response for accuracy, clarity, and missing details.", "priority_weight": 0.6},
    ]


def stage_quantum_routing(subtasks):
    weights = [subtask.get("priority_weight", 0.5) for subtask in subtasks]
    order_indices, metadata = quantum_route_order(len(subtasks), weights)
    metadata["ordered_ids"] = [subtasks[index]["id"] for index in order_indices]
    return metadata["ordered_ids"], metadata


def spawn_agent(keys, agent_id, subtask, overall_task, brain):
    brain_context = brain.read_context(exclude_agent=agent_id)
    system = f"You are Agent-{agent_id}, a specialist AI for subtask '{subtask['title']}'. Use the Quantum Brain context to avoid redundancy. Be structured, precise, and complete."
    prompt = f"OVERALL GOAL: {clean_display_text(overall_task)}\n\nYOUR SUBTASK ({subtask['id']}): {subtask['title']}\nDescription: {subtask['description']}\n\n━━ QUANTUM BRAIN CONTEXT ━━\n{brain_context}\n━━━━━━━━━━━━\n\nExecute your subtask:"
    output = clean_display_text(gemini_text(keys, prompt, system))
    brain.write(agent_id, subtask["title"], output, importance=min(0.6 + subtask.get("priority_weight", 0.5) * 0.4, 1.0))
    return output


def stage_synthesis(keys, task, brain):
    system = "You are the Hoshi Brain Synthesiser. Synthesise all agent outputs into one coherent, comprehensive response that fully answers the original task. Integrate insights, avoid repetition."
    return gemini_text(keys, f"ORIGINAL TASK: {task}\n\n━━ BRAIN DUMP ━━\n{brain.read_context()}\n━━━━━━━━━\n\nSynthesise:", system)


def stage_critic(keys, task, synthesised, brain):
    system = 'You are the Critic Agent. Analyse the synthesised response. Return ONLY JSON: {"contradictions":["..."],"weak_reasoning":["..."],"missing_info":["..."],"revision_requests":["..."],"critic_score":0-100,"verdict":"PASS|REVISE|FAIL"}\nNo markdown.'
    result = safe_json(gemini_json(keys, f"TASK: {task}\n\nRESPONSE:\n{synthesised}\n\nCritique:", system))
    brain.write("CRITIC", "Critic Analysis", json.dumps(result, indent=2), importance=0.95)
    return result


def stage_verifier(keys, task, synthesised, critic, brain):
    system = 'You are the Verification Agent. Return ONLY JSON: {"consistency_check":"PASS|PARTIAL|FAIL","completeness_score":0-100,"verification_score":0-100,"issues":["..."],"strengths":["..."],"final_verdict":"VERIFIED|NEEDS_WORK|FAILED"}\nNo markdown.'
    prompt = f"TASK: {task}\n\nRESPONSE:\n{synthesised}\n\nCRITIC SUMMARY: {json.dumps({'score': critic.get('critic_score', 0), 'verdict': critic.get('verdict', '?')})}\n\nVerify:"
    result = safe_json(gemini_json(keys, prompt, system))
    brain.write("VERIFIER", "Verification Report", json.dumps(result, indent=2), importance=0.95)
    return result


def stage_seo(keys, synthesised, task):
    system = 'You are the SEO Optimisation Agent. Return ONLY JSON: {"seo_title":"...","meta_description":"...","keywords":["kw1","kw2",...],"optimised_content":"...","seo_score":0-100,"readability_score":0-100,"keyword_density":0.0-1.0,"word_count":integer}\nNo markdown.'
    try:
        result = safe_json(gemini_json(keys, f"Topic: {task}\n\nContent:\n{synthesised}", system))
    except (json.JSONDecodeError, TypeError, ValueError):
        result = {}
    return normalize_seo_result(result, synthesised, task)


def normalize_seo_result(result, synthesised, task):
    """Keep the final SEO panel useful when a provider omits or corrupts fields."""
    result = result if isinstance(result, dict) else {}
    content = str(result.get("optimised_content") or synthesised).strip()
    words = content.split()
    keywords = result.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [keyword.strip() for keyword in keywords.split(",") if keyword.strip()]
    if not isinstance(keywords, list):
        keywords = []
    seo_score = result.get("seo_score", 80)
    readability_score = result.get("readability_score", 75)
    try:
        seo_score = max(0, min(100, int(float(seo_score))))
    except (TypeError, ValueError):
        seo_score = 80
    try:
        readability_score = max(0, min(100, int(float(readability_score))))
    except (TypeError, ValueError):
        readability_score = 75
    return {
        "seo_title": str(result.get("seo_title") or str(task)[:60]).strip(),
        "meta_description": str(result.get("meta_description") or content[:155]).strip(),
        "keywords": [str(keyword).strip() for keyword in keywords if str(keyword).strip()],
        "optimised_content": content,
        "seo_score": seo_score,
        "readability_score": readability_score,
        "keyword_density": result.get("keyword_density", 0.0),
        "word_count": len(words),
    }


def compute_confidence(critic, verifier, brain, n_agents):
    critic_score = critic.get("critic_score", 70)
    verifier_score = verifier.get("verification_score", 70)
    memory_score = min(100, len(brain.entries) / max(n_agents, 1) * 20)
    bonus = 10 if verifier.get("final_verdict") == "VERIFIED" else 0
    return round(min((critic_score * 0.35 + verifier_score * 0.40 + memory_score * 0.15 + bonus) * 0.9 + 5, 99), 1)


def compute_ap(resonance, seo_score, n_subtasks):
    return round(resonance * seo_score / 100 * math.log1p(n_subtasks) * 10, 3)
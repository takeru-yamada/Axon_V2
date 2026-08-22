"""Page renderers for the non-pipeline Axon screens."""

import html

import streamlit as st

from app_utils import clean_display_text


def render_builder_page(builder, render_torii):
    render_torii()
    st.markdown('<div class="sec-head">Builder Info</div>', unsafe_allow_html=True)
    skills_html = "".join(f'<span class="skill-chip">{skill}</span>' for skill in builder["skills"])
    st.markdown(f"""
    <div class="builder-card">
    <div style="display:flex;align-items:center;margin-bottom:1.4rem;">
        <div style="display:flex;align-items:center;gap:1.2rem;">
          <div class="builder-avatar">{builder["initials"]}</div>
          <div>
            <div class="builder-name">{builder["name"]}</div>
            <div class="builder-role">{builder["role"]}</div>
          </div>
                </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1.3rem;">
        <div><div class="builder-field-label">Email</div><div class="builder-field-val">{builder["email"]}</div></div>
        <div><div class="builder-field-label">Location</div><div class="builder-field-val">{builder["location"]}</div></div>
      </div>
      <div style="margin-bottom:1.3rem;">
        <div class="builder-field-label">Bio</div>
        <div style="font-size:0.82rem;color:#c4b5fd;line-height:1.7;margin-top:0.2rem;">{builder["bio"]}</div>
      </div>
      <div><div class="builder-field-label">Specialisations</div><div style="margin-top:0.4rem;">{skills_html}</div></div>
    </div>
    """, unsafe_allow_html=True)


def render_help_page(gemini_text, render_torii):
    render_torii()
    st.markdown('<div class="sec-head">Customer Help</div>', unsafe_allow_html=True)
    st.markdown('<div style="color:#64748b;font-size:0.82rem;margin-bottom:1rem;">Ask anything about the Hoshi system, DWSA, Quantum Layer, or spawned agents.</div>', unsafe_allow_html=True)

    if "help_history" not in st.session_state:
        st.session_state.help_history = []
    if not st.session_state.help_history:
        st.markdown("""<div class="chat-bubble-axon" style="max-width:700px;">
          <div class="axon-avatar">HOSHI SUPPORT</div>
          Hello! I'm Hoshi's support assistant. Ask me anything about the DWSA system, quantum layer, spawned agents, or anything else. 🌸
        </div>""", unsafe_allow_html=True)

    for message in st.session_state.help_history:
        if message["role"] == "user":
            st.markdown(f'<div class="chat-bubble-user">{html.escape(str(message["content"]))}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-bubble-axon" style="max-width:700px;"><div class="axon-avatar">HOSHI SUPPORT</div>{html.escape(clean_display_text(message["content"]))}</div>', unsafe_allow_html=True)

    faq_cols = st.columns(4)
    faqs = ["How do I spawn an agent?", "What is DWSA?", "How does quantum routing work?", "Check system status"]
    for index, (column, faq) in enumerate(zip(faq_cols, faqs)):
        with column:
            if st.button(faq, key=f"faq_{index}", use_container_width=True):
                st.session_state.help_history.append({"role": "user", "content": faq})
                if not st.session_state.api_keys:
                    st.session_state.help_history.append({"role": "assistant", "content": "Please configure your API keys in the sidebar to use the live AI support."})
                else:
                    system = "You are Hoshi AI Support — a helpful assistant for the Hoshi AI Command Center. The system features DWSA (Distributed Wave State Architecture), a Quantum Layer powered by Qiskit, and Spawned Agents. Answer user questions warmly and concisely in 2-4 sentences."
                    with st.spinner("Thinking…"):
                        answer = gemini_text(st.session_state.api_keys, faq, system)
                    st.session_state.help_history.append({"role": "assistant", "content": answer})
                st.rerun()

    col_input, col_button = st.columns([5, 1])
    with col_input:
        help_input = st.text_input("Ask a question", placeholder="Ask about DWSA, agents, quantum layer…", label_visibility="collapsed", key="help_input")
    with col_button:
        help_send = st.button("Send", use_container_width=True, key="help_send")

    if help_send and help_input.strip():
        question = help_input.strip()
        st.session_state.help_history.append({"role": "user", "content": question})
        if not st.session_state.api_keys:
            fallback = {
                "spawn": "Start a task from the Dashboard and the DWSA system will spawn agents automatically.",
                "dwsa": "DWSA (Distributed Wave State Architecture) decomposes your task into 4–6 atomic subtasks and routes them via quantum circuits.",
                "quantum": "The Quantum Layer uses Qiskit circuits to determine optimal agent execution order based on priority weights.",
                "status": "Check the sidebar for live System Status — DWSA Core, Quantum Layer, and active agent count.",
            }
            answer = next((value for key, value in fallback.items() if key in question.lower()), "That's a great question! Check the Quantum Workflow page for full pipeline details.")
        else:
            system = "You are Hoshi AI Support — a helpful assistant for the Hoshi AI Command Center. The system features DWSA (Distributed Wave State Architecture), a Quantum Layer powered by Qiskit, and Spawned Agents. Answer user questions warmly and concisely in 2-4 sentences."
            history_prompt = "\n".join(f"{message['role'].upper()}: {message['content']}" for message in st.session_state.help_history[-6:])
            with st.spinner("Thinking…"):
                answer = gemini_text(st.session_state.api_keys, history_prompt, system)
        st.session_state.help_history.append({"role": "assistant", "content": answer})
        st.rerun()
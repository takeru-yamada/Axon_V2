"""Reusable user dialog for incomplete exception cases."""

import streamlit as st

from playbooks import PlaybookEngine
from uuid_gen import get_sandbox_state


@st.dialog("Information needed to continue")
def show_missing_data_popup(case_id: str):
    """Ask the user for missing fields in one isolated case."""
    state = get_sandbox_state(case_id)
    st.warning("This session is paused until the requested information is provided.")
    st.caption(f"Only case {case_id[:12]}... will be updated.")
    prompt = state["case_data"].get("original_prompt") or state["case_data"].get("user_prompt")
    analysis = state.get("analysis") or {}
    if prompt:
        st.markdown("**Your request**")
        st.info(prompt)
    with st.expander("Constraint checker input/output"):
        st.markdown("**Input sent for analysis**")
        st.json({
            "request": prompt or "No original request recorded",
            "case_data": state.get("case_data", {}),
        })
        st.markdown("**Analysis output**")
        st.json({
            "provider": analysis.get("provider", "Constraint checker"),
            "diagnosis": analysis.get("diagnosis", "Needs clarification"),
            "confidence": analysis.get("confidence", 0),
        })
    st.markdown("**What the agent understood**")
    st.write(
        state.get("synthesized_output")
        or analysis.get("synthesized_summary")
        or "The agent is checking the request for missing or conflicting information."
    )
    st.markdown("**Why we paused**")
    st.write(analysis.get("plain_language_explanation", analysis.get("diagnosis", "Some information needs clarification.")))
    st.markdown("**Simple question**")
    with st.form(f"missing_data_form_{case_id}"):
        responses = {
            f"answer_{index}": st.text_input(
                question,
                key=f"missing_answer_{case_id}_{index}",
            )
            for index, question in enumerate(state["required_questions"])
        }
        submitted = st.form_submit_button("Submit information", type="primary")
    if submitted:
        try:
            PlaybookEngine.submit_user_data(case_id, responses)
            st.rerun()
        except (TypeError, ValueError) as error:
            st.error(str(error))

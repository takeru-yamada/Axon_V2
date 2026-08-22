"""Exception-resolution playbooks with isolated state per case."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st

from uuid_gen import get_sandbox_state


class PlaybookEngine:
    """Execute one resolution path without sharing data between cases."""

    @staticmethod
    def _provider_keys():
        """Read provider keys without placing credentials in case state."""
        try:
            gemini = list(st.secrets.get("api_keys", {}).values())
            mistral = list(st.secrets.get("mistral_keys", {}).values())
        except Exception:
            gemini = []
            mistral = []
        gemini.extend(filter(None, os.getenv("GEMINI_API_KEYS", "").split(",")))
        mistral.extend(filter(None, os.getenv("MISTRAL_API_KEYS", "").split(",")))
        return list(dict.fromkeys(gemini)), list(dict.fromkeys(mistral))

    @staticmethod
    def _analyze_with_ai(state, mode: str):
        """Analyze isolated evidence, using Mistral first for preflight checks."""
        gemini_keys, mistral_keys = PlaybookEngine._provider_keys()
        prompt = json.dumps({
            "case_id": state["case_id"],
            "mode": mode,
            "case_data": state["case_data"],
            "conflicting_outputs": state["conflicting_outputs"],
            "current_status": state["status"],
        })
        system = (
            "You are a constraint-checking agent. Analyze the complete user request in the supplied case. "
            "Return valid JSON with keys: constraint_found (boolean), diagnosis, "
            "plain_language_explanation, clarifying_question, missing_data, recommended_action, "
            "confidence (0-100). missing_data must be a list of short questions for "
            "the user, or an empty list. clarifying_question must be one short, simple "
            "question grounded in the user's complete request. Also return synthesized_summary "
            "with a short plain-language interpretation before asking the question. Explain "
            "complex constraints in everyday language. Do not ask for optional preferences, "
            "facts that are already present, or information needed only to improve the answer. "
            "If the request is complete and answerable, set constraint_found to false, "
            "clarifying_question to an empty string, and missing_data to an empty list. "
            "Only identify a constraint when it is genuinely impossible, contradictory, "
            "unsafe, or missing information prevents a correct answer. Do not invent facts."
        )
        errors = []
        if mode == "PREFLIGHT":
            mistral_analysis = PlaybookEngine._analyze_with_mistral(
                mistral_keys, prompt, system, errors
            )
            if mistral_analysis is not None:
                return mistral_analysis
        for gemini_key in gemini_keys:
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel(
                    "gemini-2.5-flash",
                    system_instruction=system,
                    generation_config={"temperature": 0.2, "response_mime_type": "application/json"},
                )
                analysis = json.loads(model.generate_content(prompt).text)
                analysis["provider"] = "Gemini"
                return analysis
            except Exception as error:
                errors.append(f"Gemini: {error}")
        for mistral_key in mistral_keys:
            try:
                from mistralai.client import Mistral
                client = Mistral(api_key=mistral_key)
                response = client.chat.complete(
                    model="mistral-small-latest",
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                analysis = json.loads(response.choices[0].message.content)
                analysis["provider"] = "Mistral"
                return analysis
            except Exception as error:
                errors.append(f"Mistral: {error}")
        return {
            "diagnosis": "AI analysis unavailable; provider credentials or service are not configured.",
            "missing_data": [] if mode == "PREFLIGHT" else ["Which information should be supplied to resolve this exception?"],
            "recommended_action": mode,
            "confidence": 0,
            "constraint_found": False,
            "plain_language_explanation": "The request could not be checked because the AI services are unavailable.",
            "clarifying_question": "" if mode == "PREFLIGHT" else "What should I change or clarify in this request?",
            "synthesized_summary": "The request could not be summarized because the AI services are unavailable.",
            "provider_errors": errors,
        }

    @staticmethod
    def _analyze_with_mistral(keys, prompt, system, errors):
        """Run the preflight check through every configured Mistral key."""
        for mistral_key in keys:
            try:
                from mistralai.client import Mistral
                client = Mistral(api_key=mistral_key)
                response = client.chat.complete(
                    model="mistral-small-latest",
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                analysis = json.loads(response.choices[0].message.content)
                analysis["provider"] = "Mistral"
                return analysis
            except Exception as error:
                errors.append(f"Mistral: {error}")
        return None

    @staticmethod
    def _analyze_and_record(state, mode: str):
        analysis = PlaybookEngine._analyze_with_ai(state, mode)
        if not isinstance(analysis, dict):
            analysis = {
                "diagnosis": "The provider returned an invalid analysis format.",
                "missing_data": ["Please describe the missing information for this case."],
                "recommended_action": mode,
                "confidence": 0,
            }
        missing_data = analysis.get("missing_data", [])
        if isinstance(missing_data, str):
            try:
                decoded_data = json.loads(missing_data)
                missing_data = decoded_data if isinstance(decoded_data, list) else [missing_data]
            except json.JSONDecodeError:
                missing_data = [missing_data] if missing_data.strip() else []
        if isinstance(missing_data, dict):
            missing_data = [missing_data]
        if not isinstance(missing_data, list):
            missing_data = [str(missing_data)]
        state["required_questions"] = [
            item.get("question", item.get("field", str(item)))
            if isinstance(item, dict) else str(item)
            for item in missing_data
        ]
        state["required_questions"] = [
            question.strip() for question in state["required_questions"] if question.strip()
        ]
        if mode == "USER_INPUT_MODAL" and not state["required_questions"]:
            state["required_questions"] = ["What information is missing from this case?"]
        state["analysis"] = analysis
        return analysis

    @staticmethod
    def inspect_case(case_id: str):
        """Use Gemini/Mistral to check whether a request truly needs clarification."""
        state = get_sandbox_state(case_id)
        if state["case_data"].get("preflight_checked"):
            return state
        questions = []
        analysis = PlaybookEngine._analyze_with_ai(state, "PREFLIGHT")
        state["case_data"]["preflight_checked"] = True
        ai_question = analysis.get("clarifying_question", "") if isinstance(analysis, dict) else ""
        if ai_question and analysis.get("constraint_found") is True:
            questions = [str(ai_question).strip()]
        if not questions and isinstance(analysis, dict) and analysis.get("constraint_found") is True:
            ai_questions = analysis.get("missing_data", []) if isinstance(analysis, dict) else []
            if isinstance(ai_questions, str):
                ai_questions = [ai_questions] if ai_questions.strip() else []
            questions = [str(question) for question in ai_questions if str(question).strip()]
        if questions:
            original_prompt = str(state["case_data"].get("user_prompt", "")).strip()
            summary = ""
            if isinstance(analysis, dict):
                summary = str(analysis.get("synthesized_summary", "")).strip()
            if not summary:
                summary = f"I understood your request as: {original_prompt[:400]}"
            state["synthesized_output"] = summary
            state["required_questions"] = questions
            state["analysis"] = {
                "diagnosis": analysis.get("diagnosis", "The request needs clarification.") if isinstance(analysis, dict) else "The request needs clarification.",
                "plain_language_explanation": analysis.get("plain_language_explanation", "One or more requirements may conflict or be incomplete.") if isinstance(analysis, dict) else "One or more requirements may conflict or be incomplete.",
                "synthesized_summary": summary,
                "missing_data": questions,
                "clarifying_question": questions[0],
                "recommended_action": "USER_INPUT_MODAL",
                "confidence": 100,
                "provider": analysis.get("provider", "Local constraint rules") if isinstance(analysis, dict) else "Local constraint rules",
            }
            state["status"] = "PAUSED_FOR_USER"
            st.session_state.active_user_modal_case = case_id
        return state

    @staticmethod
    def _pause_for_missing_data(state):
        if state["required_questions"]:
            state["status"] = "PAUSED_FOR_USER"
            st.session_state.active_user_modal_case = state["case_id"]
            return True
        return False

    @staticmethod
    def get_user_message(case_id: str):
        """Return safe, user-facing text without exposing provider errors."""
        state = get_sandbox_state(case_id)
        questions = state.get("required_questions", [])
        if questions:
            return "Additional information is needed to continue this case."
        if state["status"] == "RESOLVED":
            return "This case has been resolved successfully."
        return "This case is being reviewed by the exception playbook."

    @staticmethod
    def record_error(case_id: str, code: str, error: Exception):
        """Pass an internal error into the isolated playbook without exposing it."""
        state = get_sandbox_state(case_id)
        state["last_error"] = {"code": code, "detail": str(error)}
        state["case_data"]["error_code"] = code
        state["required_questions"] = [
            "Please provide the missing or corrected information so this case can be retried."
        ]
        state["status"] = "ERROR_REVIEW"
        st.session_state.active_user_modal_case = case_id
        return state

    @staticmethod
    def submit_user_data(case_id: str, responses: dict):
        """Store answers only in the selected case and resume its workflow."""
        if not isinstance(responses, dict):
            raise TypeError("responses must be a dictionary")
        state = get_sandbox_state(case_id)
        cleaned_responses = {
            key: str(value).strip() for key, value in responses.items() if str(value).strip()
        }
        if len(cleaned_responses) != len(responses):
            raise ValueError("Please answer every question before submitting")
        state["user_responses"] = cleaned_responses
        state["case_data"].update(cleaned_responses)
        original_prompt = state["case_data"].get("original_prompt")
        if not original_prompt:
            original_prompt = str(state["case_data"].get("user_prompt", ""))
            original_prompt = original_prompt.split("\nUser clarification:", 1)[0]
            original_prompt = original_prompt.removeprefix("Original request:").strip()
            state["case_data"]["original_prompt"] = original_prompt
        state["analysis"] = {
            **(state.get("analysis") or {}),
            "clarification_status": "ANSWERED",
            "user_resolution": cleaned_responses,
        }
        state["synthesized_output"] = (
            f"Request understood: {original_prompt}\n"
            f"Latest clarification: {json.dumps(cleaned_responses, ensure_ascii=True)}"
        )
        st.session_state.current_task = (
            f"{original_prompt}\n\nUser clarification: "
            f"{json.dumps(cleaned_responses, ensure_ascii=True)}"
        )
        st.session_state.pipeline_done = False
        st.session_state.pipeline_data = {}
        state["required_questions"] = []
        state["status"] = "OPEN"
        if st.session_state.get("active_user_modal_case") == case_id:
            st.session_state.pop("active_user_modal_case", None)
        return state

    @staticmethod
    def _record_resolution(state, mode, details):
        state["resolution"] = {
            "mode": mode,
            "details": details,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def send_case_request(case_id: str, api_url: str, timeout: float = 10.0):
        """POST one isolated case to an API and store the response on that case."""
        if not api_url or not api_url.strip():
            raise ValueError("api_url must be a non-empty URL")
        state = get_sandbox_state(case_id)
        payload = {
            "request_type": "exception_playbook_resolution",
            "case_id": case_id,
            "case_data": state["case_data"],
            "status": state["status"],
            "model_route": state["model_route"],
            "resolution_action": state["resolution_action"],
            "resolution": state["resolution"],
            "analysis": state["analysis"],
        }
        request = Request(
            api_url.strip(),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                raw_body = response.read().decode("utf-8")
                response_data = json.loads(raw_body) if raw_body else None
                result = {"ok": True, "status_code": response.status, "body": response_data}
        except HTTPError as error:
            result = {"ok": False, "status_code": error.code, "error": error.reason}
        except (URLError, TimeoutError, OSError) as error:
            result = {"ok": False, "status_code": None, "error": str(getattr(error, "reason", error))}
        state["last_api_response"] = result
        state["request_history"].append({"payload": payload, "response": result})
        return result

    @staticmethod
    def execute_fallback_key_rotation(case_id: str):
        state = get_sandbox_state(case_id)
        analysis = PlaybookEngine._analyze_and_record(state, "FALLBACK_KEY_ROTATION")
        if PlaybookEngine._pause_for_missing_data(state):
            return state
        state["resolution_action"] = "API Key Rotated & Model Switched (Gemini -> Mistral)"
        state["model_route"] = "Mistral-7B"
        state["status"] = "RESOLVED"
        PlaybookEngine._record_resolution(state, "FALLBACK_KEY_ROTATION", {
            "previous_route": "Gemini",
            "new_route": "Mistral-7B",
            "case_data": state["case_data"],
            "ai_analysis": analysis,
        })
        return state

    @staticmethod
    def execute_user_data_modal(case_id: str):
        state = get_sandbox_state(case_id)
        analysis = PlaybookEngine._analyze_and_record(state, "USER_INPUT_MODAL")
        if not state["required_questions"]:
            state["status"] = "OPEN"
            state["resolution_action"] = "No additional information required"
            st.session_state.pop("active_user_modal_case", None)
            return state
        st.session_state.active_user_modal_case = case_id
        state["status"] = "PAUSED_FOR_USER"
        PlaybookEngine._record_resolution(state, "USER_INPUT_MODAL", {
            "required_input": "user_data",
            "case_data": state["case_data"],
            "ai_analysis": analysis,
        })
        return state

    @staticmethod
    def execute_supreme_arbiter(case_id: str):
        state = get_sandbox_state(case_id)
        analysis = PlaybookEngine._analyze_and_record(state, "SUPREME_ARBITER")
        if PlaybookEngine._pause_for_missing_data(state):
            return state
        outputs = state.get("conflicting_outputs", [])
        if outputs:
            joined_outputs = " ".join(str(output) for output in outputs)
            state["arbiter_output"] = f"Supreme Arbiter synthesis: {joined_outputs[:1000]}"
        else:
            state["arbiter_output"] = "Supreme Arbiter found no conflicting outputs."
        state["resolution_action"] = "Supreme Arbiter Resolved Contradiction"
        state["status"] = "RESOLVED"
        PlaybookEngine._record_resolution(state, "SUPREME_ARBITER", {
            "inputs_considered": outputs,
            "arbiter_output": state["arbiter_output"],
            "ai_analysis": analysis,
        })
        return state


def route_and_execute(case_id: str, mode: str):
    """Route exactly one mode to its playbook for the requested case."""
    routes = {
        "FALLBACK_KEY_ROTATION": PlaybookEngine.execute_fallback_key_rotation,
        "USER_INPUT_MODAL": PlaybookEngine.execute_user_data_modal,
        "SUPREME_ARBITER": PlaybookEngine.execute_supreme_arbiter,
    }
    try:
        playbook = routes[mode]
    except KeyError as error:
        raise ValueError(f"Unsupported exception playbook mode: {mode}") from error
    return playbook(case_id)
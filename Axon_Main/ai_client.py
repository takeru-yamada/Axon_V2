"""Gemini and Mistral fallback client used by the application."""

import streamlit as st
import google.generativeai as genai
from mistralai.client import Mistral

from app_config import DEFAULT_MISTRAL_KEYS, MISTRAL_MODEL
from app_utils import classify_error


def _try_gemini(keys, prompt, system, temperature, json_mode):
    last_err = None
    for key in keys:
        try:
            genai.configure(api_key=key)
            config = {"temperature": temperature}
            if json_mode:
                config["response_mime_type"] = "application/json"
            model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system, generation_config=config)
            return model.generate_content(prompt).text.strip()
        except Exception as error:
            last_err = (classify_error(error), str(error))
    code, message = last_err
    raise RuntimeError(f"[{code}] Gemini exhausted ({len(keys)} keys). {message}")


def _try_mistral(keys, prompt, system, temperature, json_mode):
    last_err = None
    for key in keys:
        try:
            client = Mistral(api_key=key)
            arguments = {
                "model": MISTRAL_MODEL,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": 4096,
            }
            if json_mode:
                arguments["response_format"] = {"type": "json_object"}
            response = client.chat.complete(**arguments)
            return response.choices[0].message.content.strip()
        except Exception as error:
            last_err = (classify_error(error), str(error))
    code, message = last_err
    raise RuntimeError(f"[{code}] Mistral exhausted ({len(keys)} keys). {message}")


def _call_with_fallback(gemini_keys, mistral_keys, prompt, system, temperature=0.7, json_mode=False):
    errors = []
    if gemini_keys:
        try:
            return _try_gemini(gemini_keys, prompt, system, temperature, json_mode)
        except RuntimeError as error:
            errors.append(f"Gemini: {error}")
    if mistral_keys:
        try:
            return _try_mistral(mistral_keys, prompt, system, temperature, json_mode)
        except RuntimeError as error:
            errors.append(f"Mistral: {error}")
    raise RuntimeError("[AX-KEY] All providers exhausted.\n" + "\n".join(errors))


def gemini_json(keys, prompt, system):
    mistral_keys = st.session_state.get("mistral_keys", DEFAULT_MISTRAL_KEYS)
    return _call_with_fallback(keys, mistral_keys, prompt, system, temperature=0.2, json_mode=True)


def gemini_text(keys, prompt, system):
    mistral_keys = st.session_state.get("mistral_keys", DEFAULT_MISTRAL_KEYS)
    return _call_with_fallback(keys, mistral_keys, prompt, system, temperature=0.7, json_mode=False)
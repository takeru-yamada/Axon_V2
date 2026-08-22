"""Application configuration and builder profile data."""

import streamlit as st


DEFAULT_API_KEYS = list(st.secrets.get("api_keys", {}).values())
DEFAULT_MISTRAL_KEYS = list(st.secrets.get("mistral_keys", {}).values())
MISTRAL_MODEL = "mistral-small-latest"

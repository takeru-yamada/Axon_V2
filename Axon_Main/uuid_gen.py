import uuid_utils
from datetime import datetime, timezone

_SANDBOX_STATES = {}


def generate_request_id():
	"""Return a sortable UUID7 for an agent request."""
	return str(uuid_utils.uuid7())


def get_sandbox_state(case_id):
	"""Return the isolated mutable state for one exception case."""
	if not isinstance(case_id, str) or not case_id.strip():
		raise ValueError("case_id must be a non-empty string")
	defaults = {
		"case_id": case_id,
		"status": "OPEN",
		"model_route": "Gemini",
		"case_data": {},
		"resolution_action": None,
		"resolution": {},
		"analysis": None,
		"synthesized_output": None,
		"required_questions": [],
		"user_responses": {},
		"conflicting_outputs": [],
		"arbiter_output": None,
		"request_history": [],
		"last_api_response": None,
		"last_error": None,
	}
	state = _SANDBOX_STATES.setdefault(case_id, {})
	for key, value in defaults.items():
		state.setdefault(key, value.copy() if isinstance(value, (dict, list)) else value)
	return state


if __name__ == "__main__":
	print(generate_request_id())


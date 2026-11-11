import json
import requests
from core.i18n import tr
from llm import anthropic_adapter
from llm.endpoints import is_anthropic_url, local_url


def describe_bad_response(text: str, limit: int=500) -> str:
	"""Return a short useful description of a malformed AI API response."""
	raw = (text or '').strip()
	try:
		payload = json.loads(raw)
	except (TypeError, ValueError):
		payload = None
	if isinstance(payload, dict):
		error = payload.get('error')
		if isinstance(error, dict):
			raw = str(error.get('message') or error.get('type') or error)
		elif error:
			raw = str(error)
		elif payload:
			raw = json.dumps(payload, ensure_ascii=False)
	return raw[:max(0, int(limit))] or 'Empty response'


class AIClient:
	def __init__(self, api_key: str='', base_url: str='https://openrouter.ai/api/v1'):
		self.api_key = api_key
		self.base_url = local_url(base_url)

	def list_models(self, free_only: bool=False) -> tuple[bool, str, list[str]]:
		if is_anthropic_url(self.base_url):
			ok, message, models = anthropic_adapter.list_models(self.api_key, self.base_url)
			return (ok, message, [] if free_only else models)
		if not self.api_key:
			return (False, tr('openrouter.key_empty'), [])
		try:
			response = requests.get(
				f'{self.base_url.rstrip("/")}/models',
				headers={'Authorization': f'Bearer {self.api_key}'},
				timeout=20,
			)
		except requests.exceptions.RequestException as exc:
			return (False, tr('openrouter.connect_fail', error=exc), [])
		if response.status_code != 200:
			return (False, tr('openrouter.server_error_code', code=response.status_code), [])
		try:
			rows = response.json().get('data', [])
		except (AttributeError, TypeError, ValueError):
			return (False, tr('openrouter.bad_json'), [])
		models = []
		for row in rows:
			if not isinstance(row, dict) or not row.get('id'):
				continue
			model_id = str(row['id'])
			pricing = row.get('pricing') or {}
			is_free = model_id.endswith(':free') or (
				isinstance(pricing, dict)
				and pricing.get('prompt') == '0'
				and pricing.get('completion') == '0'
			)
			if not free_only or is_free:
				models.append(model_id)
		models.sort()
		return (True, tr('openrouter.free_models_found', n=len(models)) if free_only else f'{len(models)} models available', models)

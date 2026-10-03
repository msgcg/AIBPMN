import json
import re
import time
import uuid
import urllib3
import requests
from django.conf import settings
from .knowledge_base import compose_system_prompt
from .compiler_service import compile_dsl
from .process_analyzer import (
    parse_dsl_structure,
    find_cycles_and_gaps,
    generate_validation_report,
    generate_proactive_questions,
    extract_traceability,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class GigaChatAuthError(ValueError):
    """Raised when GigaChat API authorization key is missing or rejected."""
    pass


class GigaChatService:
    _tokens: dict[tuple[str, str], tuple[str, int]] = {}
    _token = None
    _token_expires_at = 0

    @classmethod
    def resolve_user_credentials(cls, user=None, auth_key: str = '', scope: str = '') -> tuple[str, str]:
        default_scope = getattr(settings, 'GIGACHAT_DEFAULT_SCOPE', 'GIGACHAT_API_PERS')
        resolved_key = (auth_key or '').strip()
        resolved_scope = (scope or '').strip() or default_scope

        if not resolved_key and user is not None and getattr(user, 'is_authenticated', False):
            try:
                cred = getattr(user, 'gigachat_credential', None)
                if cred and cred.auth_key:
                    resolved_key = cred.auth_key.strip()
                    resolved_scope = (cred.scope or default_scope).strip()
            except Exception:
                pass

        if resolved_key.lower().startswith('basic '):
            resolved_key = resolved_key[6:].strip()

        return resolved_key, resolved_scope

    @classmethod
    def get_token(cls, auth_key: str = '', scope: str = '', user=None) -> str:
        resolved_key, resolved_scope = cls.resolve_user_credentials(user=user, auth_key=auth_key, scope=scope)
        if not resolved_key:
            raise GigaChatAuthError(
                "Ключ авторизации GigaChat API не настроен. Введите ключ в интерактивном окне настройки ИИ."
            )

        current_time = int(time.time() * 1000)
        cache_key = (resolved_key, resolved_scope)
        cached = cls._tokens.get(cache_key)
        if cached and cached[0] and cached[1] - current_time > 60000:
            return cached[0]

        oauth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Authorization": f"Basic {resolved_key}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"scope": resolved_scope}

        try:
            resp = requests.post(oauth_url, headers=headers, data=data, verify=False, timeout=12)
            if resp.status_code in (400, 401, 403):
                raise GigaChatAuthError(
                    f"Ключ авторизации GigaChat отклонен сервером Сбера (HTTP {resp.status_code}). Проверьте правильность ключа и выбранный Scope."
                )
            resp.raise_for_status()
            res_data = resp.json()
            token = res_data.get("access_token")
            expires_at = res_data.get("expires_at", current_time + 1800000)
            if token:
                cls._tokens[cache_key] = (token, expires_at)
                cls._token = token
                cls._token_expires_at = expires_at
            return token
        except GigaChatAuthError:
            raise
        except Exception as exc:
            raise GigaChatAuthError(f"Ошибка получения OAuth-токена GigaChat: {exc}")

    @classmethod
    def check_status(cls, auth_key: str = '', scope: str = '', user=None) -> dict:
        model_name = getattr(settings, 'GIGACHAT_MODEL', 'GigaChat-3-Ultra')
        resolved_key, resolved_scope = cls.resolve_user_credentials(user=user, auth_key=auth_key, scope=scope)
        if not resolved_key:
            return {
                'ok': False,
                'key_configured': False,
                'key_required': True,
                'model': model_name,
                'scope': resolved_scope,
                'error': 'Ключ авторизации GigaChat API не задан'
            }
        try:
            cls.get_token(auth_key=resolved_key, scope=resolved_scope, user=user)
            return {
                'ok': True,
                'key_configured': True,
                'key_required': False,
                'model': model_name,
                'scope': resolved_scope,
                'message': f'Модель {model_name} активна и готова к работе'
            }
        except Exception as exc:
            return {
                'ok': False,
                'key_configured': True,
                'key_required': True,
                'model': model_name,
                'scope': resolved_scope,
                'error': str(exc)
            }

    @classmethod
    def _call_completions(cls, messages: list, temperature: float = 0.3, auth_key: str = '', scope: str = '', user=None) -> str:
        token = cls.get_token(auth_key=auth_key, scope=scope, user=user)
        model_name = getattr(settings, 'GIGACHAT_MODEL', 'GigaChat-3-Ultra')

        # Use api.giga.chat for GigaChat-3-Ultra as specified in official docs
        api_url = "https://api.giga.chat/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature
        }

        resp = requests.post(api_url, headers=headers, json=payload, verify=False, timeout=60)
        if resp.status_code != 200:
            # Fallback to standard host if needed
            if resp.status_code == 404:
                alt_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
                resp = requests.post(alt_url, headers=headers, json=payload, verify=False, timeout=60)

        if resp.status_code in (401, 403):
            # Invalidate cached token if unauthorized
            resolved_key, resolved_scope = cls.resolve_user_credentials(user=user, auth_key=auth_key, scope=scope)
            cls._tokens.pop((resolved_key, resolved_scope), None)
            raise GigaChatAuthError(f"Ошибка авторизации при обращении к модели GigaChat (HTTP {resp.status_code}).")

        resp.raise_for_status()
        res_json = resp.json()
        return res_json["choices"][0]["message"]["content"]

    @classmethod
    def extract_trace_hints(cls, text: str) -> tuple[list[dict] | None, str]:
        if not text:
            return None, text
        pattern = r"```(?:trace|json:trace)\s*([\s\S]*?)\s*```"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            clean_text = text[:m.start()].strip() + "\n" + text[m.end():].strip()
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed, clean_text.strip()
            except Exception:
                pass
            return None, clean_text.strip()
        return None, text

    @classmethod
    def extract_dsl_and_explanation(cls, text: str) -> tuple[str | None, str]:
        """
        Extracts DSL code from ```bac ... ``` or ```bpmn ... ``` and explanation.
        If the response is a conversational consultation or Q&A without code, returns (None, text).
        """
        if not text:
            return None, ""

        # Clean trace block if present in explanation
        _, text = cls.extract_trace_hints(text)

        # 1. Look for explicit ```bac or ```bpmn or ```dsl block
        tagged_pattern = r"```(?:bac|bpmn|dsl)\s*([\s\S]*?)\s*```"
        match = re.search(tagged_pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if "process " in candidate or any(k in candidate for k in ["start:", "task:", "gateway:", "end:", "->"]):
                explanation = text[:match.start()].strip() + "\n" + text[match.end():].strip()
                _, explanation = cls.extract_trace_hints(explanation)
                return candidate, explanation.strip()

        # 2. Look for generic code blocks containing a process definition
        code_pattern = r"```\s*([\s\S]*?)\s*```"
        for m in re.finditer(code_pattern, text):
            candidate = m.group(1).strip()
            if "process " in candidate and any(k in candidate for k in ["start:", "task:", "gateway:", "end:", "->"]):
                explanation = text[:m.start()].strip() + "\n" + text[m.end():].strip()
                _, explanation = cls.extract_trace_hints(explanation)
                return candidate, explanation.strip()

        # 3. If model didn't use markdown code fences, check if text contains an explicit process block
        for quote in ['process "', "process '"]:
            if quote in text:
                idx = text.find(quote)
                candidate = text[idx:].strip()
                if any(k in candidate for k in ["start:", "task:", "gateway:", "end:", "->"]):
                    explanation = text[:idx].strip()
                    _, explanation = cls.extract_trace_hints(explanation)
                    return candidate, explanation.strip()

        # Pure conversational response / consultation without diagram modification
        return None, text.strip()

    @classmethod
    def generate_diagram(cls, prompt: str, history: list = None, max_retries: int = 5, user=None, auth_key: str = '', scope: str = '') -> dict:
        """
        Generates BPMN-as-Code DSL and architectural explanation.
        Includes automatic retry and self-correction loop if DSL fails compilation (up to 5 attempts).
        If the user asked a question, returns a consultative text response without forcing a code block.
        """
        system_prompt = compose_system_prompt(user=user)
        messages = [{"role": "system", "content": system_prompt}]

        if history:
            for item in history:
                messages.append({"role": item["role"], "content": item["content"]})

        messages.append({
            "role": "user",
            "content": f"Запрос пользователя:\n\n{prompt}"
        })

        base_len = len(messages)
        attempt = 0
        initial_explanation = ""
        last_dsl = ""
        last_error = None
        extracted_hints = None

        while attempt < max_retries:
            attempt += 1
            raw_response = cls._call_completions(messages, temperature=0.3, auth_key=auth_key, scope=scope, user=user)
            trace_hints, clean_raw = cls.extract_trace_hints(raw_response)
            if trace_hints:
                extracted_hints = trace_hints
            dsl, explanation = cls.extract_dsl_and_explanation(clean_raw)

            if attempt == 1:
                initial_explanation = explanation

            # If model answered as pure consultation / Q&A without a diagram code block:
            if dsl is None:
                final_exp = initial_explanation or explanation
                return {
                    'success': True,
                    'has_dsl': False,
                    'dsl_code': None,
                    'explanation': final_exp,
                    'content': final_exp,
                    'bpmn_xml': None,
                    'attempts': attempt,
                    'validation_report': None,
                    'proactive_questions': [],
                    'traceability': []
                }

            last_dsl = dsl

            # Compile & validate
            compile_res = compile_dsl(dsl)
            if compile_res.get('valid'):
                final_exp = initial_explanation or explanation

                # Process validation and traceability analysis
                structure = parse_dsl_structure(dsl)
                report = generate_validation_report(structure)
                questions = generate_proactive_questions(structure, source_text=prompt)
                traceability = extract_traceability(dsl, prompt, extracted_hints)
                cycles, gaps = find_cycles_and_gaps(structure)

                if gaps and "обнаружен логический разрыв" not in final_exp.lower():
                    gap_alerts = "\n\n".join(
                        f"⚠️ **Обнаружен логический разрыв:** {g}. Связь намеренно не построена."
                        for g in gaps
                    )
                    final_exp = f"{gap_alerts}\n\n{final_exp.strip()}"

                if "Отчет валидации процесса" not in final_exp and "отчет валидации" not in final_exp.lower():
                    final_exp = final_exp.strip() + f"\n\n{report}"

                if questions and "Уточняющие вопросы" not in final_exp and "уточняющие вопросы" not in final_exp.lower():
                    q_lines = "\n".join(f"- {q}" for q in questions)
                    final_exp = final_exp.strip() + f"\n\n❓ **Уточняющие вопросы по регламенту:**\n{q_lines}"

                return {
                    'success': True,
                    'has_dsl': True,
                    'dsl_code': dsl,
                    'explanation': final_exp,
                    'content': final_exp,
                    'bpmn_xml': compile_res.get('xml', ''),
                    'node_count': compile_res.get('node_count', 0),
                    'flow_count': compile_res.get('flow_count', 0),
                    'attempts': attempt,
                    'validation_report': report,
                    'proactive_questions': questions,
                    'traceability': traceability
                }

            # If compilation failed, ask model to correct its code with specific tips
            last_error = compile_res.get('error', 'Синтаксическая ошибка')
            line = compile_res.get('line', '?')
            col = compile_res.get('col', '?')

            tip = ""
            if "references unknown node id" in str(last_error):
                m = re.search(r'references unknown node id: "([^"]+)"', str(last_error))
                missing_id = f" '{m.group(1)}'" if m else ""
                tip = f"\nВАЖНО: Идентификатор{missing_id} указан в стрелках связей (->), но нигде не объявлен! Объяви его строкой выше (например: `task:{missing_id or ' id'} \"Название\"`) или исправь опечатку."
            elif "Duplicate node id" in str(last_error):
                tip = "\nВАЖНО: Идентификаторы всех узлов должны быть строго уникальными! Не объявляйте один и тот же ID дважды."
            elif "Expected KEYWORD \"process\"" in str(last_error) or ("process" in str(last_error).lower() and "keyword" in str(last_error).lower()):
                tip = "\nВАЖНО: Первая строка кода ОБЯЗАНА быть: process \"Название процесса\""
            elif "Expected STRING" in str(last_error) or "Unterminated string" in str(last_error):
                tip = "\nВАЖНО: Все названия узлов и дорожек должны быть в двойных кавычках: \"Название\". Одинарные кавычки не допускаются."

            messages = messages[:base_len]
            messages.append({"role": "assistant", "content": raw_response})
            messages.append({
                "role": "user",
                "content": (
                    f"При компиляции возникла ошибка (попытка {attempt} из {max_retries}, строка {line}, позиция {col}):\n"
                    f"{last_error}{tip}\n\n"
                    f"Пожалуйста, исправь синтаксис DSL кода процесса, чтобы он строго соответствовал грамматике "
                    f"и успешно скомпилировался без ошибок. Выведи исправленный полный код в блоке ```bac."
                )
            })

        # If retries exceeded, return what we have with error details
        return {
            'success': False,
            'dsl_code': last_dsl,
            'explanation': initial_explanation,
            'content': initial_explanation,
            'error': f"Не удалось автоматически устранить ошибку компиляции за {max_retries} попыток: {last_error}",
            'attempts': max_retries,
            'validation_report': None,
            'proactive_questions': [],
            'traceability': []
        }

    @classmethod
    def refine_diagram(cls, current_dsl: str, instruction: str, history: list = None, max_retries: int = 5, user=None, auth_key: str = '', scope: str = '') -> dict:
        """
        Modifies and refines an existing BPMN diagram DSL based on user's iterative instructions.
        Includes automatic retry loop (up to 5 attempts).
        """
        system_prompt = compose_system_prompt(user=user)
        messages = [{"role": "system", "content": system_prompt}]

        if history:
            for item in history:
                messages.append({"role": item["role"], "content": item["content"]})

        refine_prompt = (
            f"Текущий актуальный код процесса BPMN-as-Code (включая все последние изменения пользователя на диаграмме):\n```bac\n{current_dsl}\n```\n\n"
            f"Запрос / инструкция пользователя:\n{instruction}\n\n"
            f"1. Если пользователь просит изменить, дополнить, удалить или оптимизировать элементы схемы — "
            f"внеси изменения в код, строго опираясь на текущую структуру выше, сохрани существующие шаги и связи, "
            f"и выведи обновленный полный валидный код диаграммы в блоке ```bac, сопроводив кратким пояснением.\n"
            f"2. Если пользователь задает вопрос о схеме, просит объяснить логику, роли, развилки или дать архитектурную консультацию — "
            f"ответь развернуто и понятно на естественном языке. В этом случае блок кода ```bac возвращать НЕ нужно."
        )
        messages.append({"role": "user", "content": refine_prompt})

        base_len = len(messages)
        attempt = 0
        initial_explanation = ""
        last_dsl = current_dsl
        last_error = None
        extracted_hints = None

        while attempt < max_retries:
            attempt += 1
            raw_response = cls._call_completions(messages, temperature=0.25, auth_key=auth_key, scope=scope, user=user)
            trace_hints, clean_raw = cls.extract_trace_hints(raw_response)
            if trace_hints:
                extracted_hints = trace_hints
            dsl, explanation = cls.extract_dsl_and_explanation(clean_raw)

            if attempt == 1:
                initial_explanation = explanation

            # If model answered as pure consultation / Q&A without a diagram code block:
            if dsl is None:
                final_exp = initial_explanation or explanation
                return {
                    'success': True,
                    'has_dsl': False,
                    'dsl_code': None,
                    'explanation': final_exp,
                    'content': final_exp,
                    'bpmn_xml': None,
                    'attempts': attempt,
                    'validation_report': None,
                    'proactive_questions': [],
                    'traceability': []
                }

            last_dsl = dsl

            compile_res = compile_dsl(dsl)
            if compile_res.get('valid'):
                final_exp = initial_explanation or explanation

                # Process validation and traceability analysis
                structure = parse_dsl_structure(dsl)
                report = generate_validation_report(structure)
                questions = generate_proactive_questions(structure, source_text=instruction)
                traceability = extract_traceability(dsl, instruction, extracted_hints)
                cycles, gaps = find_cycles_and_gaps(structure)

                if gaps and "обнаружен логический разрыв" not in final_exp.lower():
                    gap_alerts = "\n\n".join(
                        f"⚠️ **Обнаружен логический разрыв:** {g}. Связь намеренно не построена."
                        for g in gaps
                    )
                    final_exp = f"{gap_alerts}\n\n{final_exp.strip()}"

                if "Отчет валидации процесса" not in final_exp and "отчет валидации" not in final_exp.lower():
                    final_exp = final_exp.strip() + f"\n\n{report}"

                if questions and "Уточняющие вопросы" not in final_exp and "уточняющие вопросы" not in final_exp.lower():
                    q_lines = "\n".join(f"- {q}" for q in questions)
                    final_exp = final_exp.strip() + f"\n\n❓ **Уточняющие вопросы по регламенту:**\n{q_lines}"

                return {
                    'success': True,
                    'has_dsl': True,
                    'dsl_code': dsl,
                    'explanation': final_exp,
                    'content': final_exp,
                    'bpmn_xml': compile_res.get('xml', ''),
                    'node_count': compile_res.get('node_count', 0),
                    'flow_count': compile_res.get('flow_count', 0),
                    'attempts': attempt,
                    'validation_report': report,
                    'proactive_questions': questions,
                    'traceability': traceability
                }

            last_error = compile_res.get('error', 'Синтаксическая ошибка')
            line = compile_res.get('line', '?')
            col = compile_res.get('col', '?')

            tip = ""
            if "references unknown node id" in str(last_error):
                m = re.search(r'references unknown node id: "([^"]+)"', str(last_error))
                missing_id = f" '{m.group(1)}'" if m else ""
                tip = f"\nВАЖНО: Идентификатор{missing_id} указан в стрелках связей (->), но нигде не объявлен! Объяви его строкой выше (например: `task:{missing_id or ' id'} \"Название\"`) или исправь опечатку."
            elif "Duplicate node id" in str(last_error):
                tip = "\nВАЖНО: Идентификаторы всех узлов должны быть строго уникальными! Не объявляйте один и тот же ID дважды."
            elif "Expected KEYWORD \"process\"" in str(last_error) or ("process" in str(last_error).lower() and "keyword" in str(last_error).lower()):
                tip = "\nВАЖНО: Первая строка кода ОБЯЗАНА быть: process \"Название процесса\""
            elif "Expected STRING" in str(last_error) or "Unterminated string" in str(last_error):
                tip = "\nВАЖНО: Все названия узлов и дорожек должны быть в двойных кавычках: \"Название\". Одинарные кавычки не допускаются."

            messages = messages[:base_len]
            messages.append({"role": "assistant", "content": raw_response})
            messages.append({
                "role": "user",
                "content": (
                    f"При компиляции обновленного кода возникла ошибка (попытка {attempt} из {max_retries}, строка {line}, позиция {col}):\n"
                    f"{last_error}{tip}\n\n"
                    f"Исправь ошибку синтаксиса DSL и верни полный валидный код диаграммы в блоке ```bac."
                )
            })

        return {
            'success': False,
            'dsl_code': last_dsl,
            'explanation': initial_explanation,
            'content': initial_explanation,
            'error': f"Ошибка после доработки: {last_error}",
            'attempts': max_retries,
            'validation_report': None,
            'proactive_questions': [],
            'traceability': []
        }


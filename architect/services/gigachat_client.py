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

class GigaChatService:
    _token = None
    _token_expires_at = 0

    @classmethod
    def get_token(cls) -> str:
        current_time = int(time.time() * 1000)
        # Refresh if expires in less than 60 seconds
        if cls._token and cls._token_expires_at - current_time > 60000:
            return cls._token

        auth_key = getattr(settings, 'GIGACHAT_AUTH_KEY', '')
        scope = getattr(settings, 'GIGACHAT_SCOPE', 'GIGACHAT_API_PERS')

        if not auth_key:
            raise ValueError("GIGACHAT_AUTH_KEY не задан в конфигурации или .env файле")

        oauth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Authorization": f"Basic {auth_key}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"scope": scope}

        try:
            resp = requests.post(oauth_url, headers=headers, data=data, verify=False, timeout=12)
            resp.raise_for_status()
            res_data = resp.json()
            cls._token = res_data.get("access_token")
            cls._token_expires_at = res_data.get("expires_at", current_time + 1800000)
            return cls._token
        except Exception as exc:
            raise RuntimeError(f"Ошибка получения OAuth-токена GigaChat: {exc}")

    @classmethod
    def check_status(cls) -> dict:
        try:
            token = cls.get_token()
            model_name = getattr(settings, 'GIGACHAT_MODEL', 'GigaChat-3-Ultra')
            return {
                'ok': True,
                'model': model_name,
                'message': f'Модель {model_name} активна и готова к работе'
            }
        except Exception as exc:
            return {
                'ok': False,
                'model': getattr(settings, 'GIGACHAT_MODEL', 'GigaChat-3-Ultra'),
                'error': str(exc)
            }

    @classmethod
    def _call_completions(cls, messages: list, temperature: float = 0.3) -> str:
        token = cls.get_token()
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
    def generate_diagram(cls, prompt: str, history: list = None, max_retries: int = 2, user=None) -> dict:
        """
        Generates BPMN-as-Code DSL and architectural explanation.
        Includes automatic retry and self-correction loop if DSL fails compilation (up to 2 attempts).
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
            raw_response = cls._call_completions(messages, temperature=0.3)
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

            messages = messages[:base_len]
            messages.append({"role": "assistant", "content": raw_response})
            messages.append({
                "role": "user",
                "content": (
                    f"При компиляции возникла ошибка (строка {line}, позиция {col}):\n"
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
    def refine_diagram(cls, current_dsl: str, instruction: str, history: list = None, max_retries: int = 2, user=None) -> dict:
        """
        Modifies and refines an existing BPMN diagram DSL based on user's iterative instructions.
        Includes automatic retry loop (up to 2 attempts).
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
            raw_response = cls._call_completions(messages, temperature=0.25)
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

            messages = messages[:base_len]
            messages.append({"role": "assistant", "content": raw_response})
            messages.append({
                "role": "user",
                "content": (
                    f"При компиляции обновленного кода возникла ошибка (строка {line}, позиция {col}):\n"
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


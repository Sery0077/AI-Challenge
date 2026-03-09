from __future__ import annotations

from ..text import normalize_text
from .types import PromptBuildContext


class PlanningStageSystemPromptBuilder:
    def supports_phase(self, phase: str) -> bool:
        return phase == "planning"

    def build_messages(self, context: PromptBuildContext) -> list[dict[str, str]]:
        if context.task_state is None:
            return []
        return [
            {
                "role": "system",
                "content": (
                    "Ты находишься на стадии PLAN в агенте со стейт-машиной:\n"
                    "plan -> execution -> validation -> done.\n"
                    "В терминах текущего пайплайна stage `planning` соответствует стадии PLAN.\n"
                    "Твоя задача на стадии PLAN:\n"
                    "- понять задачу пользователя;\n"
                    "- выделить цель, ограничения и критерии успеха;\n"
                    "- составить короткий, реалистичный, проверяемый план выполнения;\n"
                    "- определить, достаточно ли входных данных для перехода в execution.\n"
                    "Что нужно делать:\n"
                    "- Сформулируй цель задачи в 1-2 предложениях.\n"
                    "- Выдели важные ограничения, зависимости и риски.\n"
                    "- Разбей работу на шаги, которые можно выполнить последовательно.\n"
                    "- Для каждого шага опиши ожидаемый результат.\n"
                    "- Если данных недостаточно, явно укажи, чего не хватает.\n"
                    "- Если задача неоднозначна, перечисли вопросы или допущения.\n"
                    "- План должен быть конкретным и пригодным для исполнения следующей стадией.\n"
                    "Что нельзя делать:\n"
                    "- Не выполняй сам план.\n"
                    "- Не притворяйся, что задача уже решена.\n"
                    "- Не придумывай факты, которых нет во входных данных.\n"
                    "- Не пиши лишние рассуждения вне результата.\n"
                    "- Не переходи к validation или done.\n"
                    "Требования к хорошему плану:\n"
                    "- шаги атомарные и наблюдаемые;\n"
                    "- порядок шагов логичен;\n"
                    "- план покрывает весь запрос пользователя;\n"
                    "- есть критерии, по которым execution и validation смогут понять, что задача выполнена;\n"
                    "- если есть неопределённость, она явно отмечена.\n"
                    "Сформируй видимый ответ для пользователя в естественном и человекочитаемом виде.\n"
                    "Не используй жёсткий шаблон с заголовками вроде GOAL, UNDERSTANDING, CONSTRAINTS, PLAN или DONE_CRITERIA.\n"
                    "Вместо этого кратко и понятно опиши:\n"
                    "- как ты понял задачу;\n"
                    "- важные ограничения, допущения, вопросы и риски;\n"
                    "- предложенный план по шагам;\n"
                    "- по каким признакам будет понятно, что задача выполнена.\n"
                    "Если данных недостаточно, задай нужные вопросы естественным текстом.\n"
                    "Если данных достаточно, представь план как нормальное объяснение для пользователя и явно попроси подтверждение перед переходом к execution.\n"
                    "Для служебной логики по-прежнему используй metadata-блок task protocol в конце ответа, если он нужен."
                ),
            }
        ]


class ExecutionStageSystemPromptBuilder:
    def supports_phase(self, phase: str) -> bool:
        return phase == "execution"

    def build_messages(self, context: PromptBuildContext) -> list[dict[str, str]]:
        if context.task_state is None:
            return []
        return [
            {
                "role": "system",
                "content": (
                    "Ты находишься на стадии EXECUTION в агенте со стейт-машиной:\n"
                    "planning -> execution -> validation -> done.\n"
                    "В терминах текущего пайплайна stage `execution` соответствует стадии EXECUTION.\n"
                    "Твоя задача на стадии EXECUTION:\n"
                    "- выполнять уже согласованный план;\n"
                    "- двигать задачу вперёд по текущему шагу;\n"
                    "- фиксировать результат выполненной работы;\n"
                    "- определять, готова ли задача к переходу в validation.\n"
                    "Что нужно делать:\n"
                    "- Выполняй текущий шаг плана или ближайшее следующее действие.\n"
                    "- Кратко и конкретно описывай, что уже сделано.\n"
                    "- Если есть изменения требований, адаптируй выполнение под новые вводные.\n"
                    "- Если возник блокер, явно укажи его и что нужно от пользователя.\n"
                    "- Если работа по текущему шагу завершена, укажи, что именно готово и что осталось проверить.\n"
                    "- Оцени, готова ли задача к переходу в validation.\n"
                    "Что нельзя делать:\n"
                    "- Не возвращайся к широкому планированию без реальной причины.\n"
                    "- Не проси подтверждение на каждый маленький шаг.\n"
                    "- Не притворяйся, что работа выполнена, если её не было.\n"
                    "- Не переходи сразу в done, если результат ещё не прошёл проверку.\n"
                    "Сформируй видимый ответ для пользователя в естественном и человекочитаемом виде.\n"
                    "Не используй жёсткий шаблон с заголовками вроде PROGRESS, CHANGES, BLOCKERS, NEXT или VALIDATION_READINESS.\n"
                    "Вместо этого кратко и понятно опиши:\n"
                    "- что уже сделано;\n"
                    "- какие изменения внесены;\n"
                    "- есть ли блокеры;\n"
                    "- что будет следующим действием.\n"
                    "Если нужен ответ пользователя или есть блокер, скажи это прямо человеческим текстом.\n"
                    "Если работа ещё продолжается, ответ должен звучать как нормальное продолжение выполнения задачи.\n"
                    "Если реализация завершена и результат готов к проверке, явно скажи, что задача готова к переходу в validation.\n"
                    "Для служебной логики по-прежнему используй metadata-блок task protocol в конце ответа, если он нужен."
                ),
            }
        ]


class TaskProtocolSystemPromptBuilder:
    def supports_phase(self, phase: str) -> bool:
        return phase != "default"

    def build_messages(self, context: PromptBuildContext) -> list[dict[str, str]]:
        if context.task_state is None:
            return []
        return [
            {
                "role": "system",
                "content": (
                    "Task transition protocol:\n"
                    "Return exactly one metadata block at the end of every answer.\n"
                    "<<TASK_STATE>>\n"
                    "stage: planning|execution|validation|done\n"
                    "current_step: short sentence\n"
                    "expected_action: short sentence\n"
                    "transition: auto|confirm\n"
                    "confirm_prompt: short question when transition=confirm\n"
                    "<<END_TASK_STATE>>\n"
                    "Rules:\n"
                    "- Keep all user-visible text outside the metadata block.\n"
                    "- Use transition=auto when the task can continue without user approval.\n"
                    "- Use transition=confirm when you want explicit approval before applying a transition.\n"
                    "- If task state already exists, continue from it instead of restarting.\n"
                    "- If task state is missing, do not emit the metadata block."
                ),
            }
        ]


class MergeSystemMessagesBuilder:
    def supports_phase(self, phase: str) -> bool:
        return True

    def build_messages(
        self,
        context: PromptBuildContext,
        messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        del context
        system_parts: list[str] = []
        merged_messages: list[dict[str, str]] = []
        for message in messages:
            if message.get("role") == "system":
                content = normalize_text(message.get("content", "")).strip()
                if content:
                    system_parts.append(content)
                continue
            merged_messages.append(message)

        if not system_parts:
            return merged_messages
        merged_system = {"role": "system", "content": "\n\n".join(system_parts)}
        return [merged_system, *merged_messages]

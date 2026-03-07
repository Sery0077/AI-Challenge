from __future__ import annotations

import os
import sys
from datetime import datetime

import typer
from openai import BadRequestError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import Settings, load_app_settings, load_settings
from .context import ContextManager
from .llm import ChatModel
from .storage import (
    BranchRecord,
    ChatStorage,
    MemoryRecord,
    SessionSummary,
    SessionSummaryRecord,
    SessionTokenStats,
)
from .text import normalize_text
from .tokens import ModelPricing, TokenCounter

if os.name == "nt":
    import msvcrt
else:
    import termios
    import tty

app = typer.Typer(help="Interactive CLI chat agent")
console = Console()

def _safe_console_text(value: object) -> str:
    return normalize_text(str(value))


def _format_model_label(settings: Settings) -> str:
    if settings.model_alias:
        return f"{settings.model_alias} ({settings.model})"
    return settings.model


def _format_model_details(settings: Settings) -> str:
    details = _format_model_label(settings)
    if settings.base_url:
        return f"{details} @ {settings.base_url}"
    return details


def _print_current_model(settings: Settings) -> None:
    console.print(
        f"[cyan]Current model:[/cyan] {_safe_console_text(_format_model_details(settings))}"
    )


def _print_model_selection(settings: Settings) -> None:
    _print_current_model(settings)
    if settings.available_model_aliases:
        _print_model_profiles_table(settings)
        console.print(
            "[dim]Use /model <alias> for direct switch or choose a number in interactive mode.[/dim]"
        )
        return
    console.print(
        "[dim]No named model profiles configured. "
        "Use /model <raw-model-name> with current OPENAI_* settings.[/dim]"
    )


def _choose_model_interactive(settings: Settings) -> str | None:
    aliases = settings.available_model_aliases
    if not aliases:
        return None

    if not sys.stdin.isatty():
        while True:
            selected = console.input(
                "[bold green]Choose model number (or /cancel):[/bold green] "
            ).strip()
            if selected == "/cancel":
                return None
            if not selected.isdigit():
                console.print("[yellow]Please enter a valid number.[/yellow]")
                continue
            idx = int(selected)
            if idx < 1 or idx > len(aliases):
                console.print("[yellow]Number out of range.[/yellow]")
                continue
            return aliases[idx - 1]

    console.print("[bold green]Choose model number (Esc to cancel):[/bold green] ", end="")
    typed = ""
    while True:
        key = _read_single_key()
        if key == "\x1b":
            console.print()
            return None
        if key in {"\r", "\n"}:
            console.print()
            if not typed:
                console.print("[yellow]Please enter a valid number.[/yellow]")
                console.print(
                    "[bold green]Choose model number (Esc to cancel):[/bold green] ",
                    end="",
                )
                continue
            idx = int(typed)
            if idx < 1 or idx > len(aliases):
                console.print("[yellow]Number out of range.[/yellow]")
                typed = ""
                console.print(
                    "[bold green]Choose model number (Esc to cancel):[/bold green] ",
                    end="",
                )
                continue
            return aliases[idx - 1]
        if key in {"\x7f", "\b"}:
            if typed:
                typed = typed[:-1]
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue
        if key.isdigit():
            typed += key
            sys.stdout.write(key)
            sys.stdout.flush()


def _switch_chat_model(
    session_id: str,
    storage: ChatStorage,
    target_model: str,
) -> tuple[ChatModel, Settings]:
    new_settings = load_settings(selected_model=target_model)
    storage.set_session_model_alias(session_id, new_settings.model_alias)
    return _create_chat_model(new_settings), new_settings


def _print_model_profiles_table(settings: Settings) -> None:
    table = Table(title="Model Profiles")
    table.add_column("No.", justify="right")
    table.add_column("Alias")
    table.add_column("Current", justify="center")
    for index, alias in enumerate(settings.available_model_aliases, start=1):
        table.add_row(
            str(index),
            _safe_console_text(alias),
            "yes" if alias == settings.model_alias else "",
        )
    console.print(table)


def _create_chat_model(settings: Settings) -> ChatModel:
    return ChatModel(
        api_key=settings.api_key,
        model=settings.model,
        base_url=settings.base_url,
    )


def _build_storage() -> ChatStorage:
    app_settings = load_app_settings()
    storage = ChatStorage(app_settings.storage_path)
    storage.init()
    return storage


def _build_model(
    selected_model: str | None = None,
    session_id: str | None = None,
    storage: ChatStorage | None = None,
) -> tuple[ChatModel, ChatStorage, Settings]:
    try:
        storage = storage or _build_storage()
        effective_model = selected_model
        if session_id is not None and effective_model is None and storage.session_exists(session_id):
            effective_model = storage.get_session_model_alias(session_id)
        settings = load_settings(selected_model=effective_model)
    except ValueError as exc:
        console.print(f"[bold red]Config error:[/bold red] {exc}")
        raise typer.Exit(code=1)

    model = _create_chat_model(settings)
    return model, storage, settings


def _chat_loop(
    model: ChatModel,
    storage: ChatStorage,
    session_id: str,
    settings: Settings,
    show_history: bool = False,
) -> None:
    system_prompt = normalize_text(settings.system_prompt)
    token_counter = TokenCounter(settings.model)
    session_config = storage.get_session_context_config(session_id)
    branch_commands_enabled = session_config.strategy == "branching"
    memory_commands_enabled = session_config.strategy == "memory"
    message_records = storage.load_message_records(session_id)
    if not message_records:
        system_tokens = token_counter.count_text(system_prompt)
        storage.clear_session(session_id, system_prompt, token_count=system_tokens)
        message_records = storage.load_message_records(session_id)
    else:
        if storage.fill_missing_token_counts(session_id, token_counter.count_text) > 0:
            message_records = storage.load_message_records(session_id)
    pricing = ModelPricing(
        input_per_1m=settings.input_cost_per_1m,
        output_per_1m=settings.output_cost_per_1m,
    )
    context_manager = ContextManager(storage=storage, token_counter=token_counter)
    debug_enabled = False

    title = f"chat-agent | session #{session_id} | model {_format_model_label(settings)}"
    if branch_commands_enabled:
        title += f" | branch {storage.get_active_branch_name(session_id) or 'main'}"
    commands_line = "Commands: /exit, /clear, /debug, /stats, /summary, /compact, /model"
    if branch_commands_enabled:
        commands_line += ", /checkpoint, /branch, /branches, /switch"
    if memory_commands_enabled:
        commands_line += ", /memory"

    console.print(
        Panel(
            "Interactive chat started.\n"
            + commands_line,
            title=title,
            border_style="cyan",
        )
    )
    _print_current_model(settings)
    if token_counter.fallback:
        console.print(
            "[dim yellow]"
            "tiktoken is not installed, token counts are approximate."
            "[/dim yellow]"
        )
    if show_history:
        _print_chat_history(
            [{"role": row.role, "content": row.content} for row in message_records]
        )

    while True:
        user_text = console.input("[bold green]You:[/bold green] ").strip()

        if not user_text:
            continue

        if user_text.startswith("/"):
            command = user_text.split(maxsplit=1)[0].lower()
            if command == "/exit":
                console.print("[cyan]Session ended.[/cyan]")
                console.print()
                return
            if command == "/clear":
                storage.clear_session(
                    session_id,
                    system_prompt,
                    token_count=token_counter.count_text(system_prompt),
                )
                message_records = storage.load_message_records(session_id)
                console.print("[yellow]History cleared.[/yellow]")
                console.print()
                continue
            if command == "/debug":
                debug_enabled = not debug_enabled
                state = "enabled" if debug_enabled else "disabled"
                console.print(f"[yellow]Token debug {state}.[/yellow]")
                if debug_enabled:
                    _print_debug_snapshot(
                        storage=storage,
                        session_id=session_id,
                        session_config=session_config,
                        message_records=message_records,
                    )
                console.print()
                continue
            if command == "/stats":
                _print_session_stats(storage.session_token_stats(session_id), pricing)
                console.print()
                continue
            if command == "/summary":
                _print_session_summaries(storage.list_session_summaries(session_id))
                console.print()
                continue
            if command == "/model":
                target_model = user_text[len("/model"):].strip()
                if not target_model:
                    _print_model_selection(settings)
                    chosen_model = _choose_model_interactive(settings)
                    if chosen_model is None:
                        console.print("[cyan]Model switch canceled.[/cyan]")
                        console.print()
                        continue
                    target_model = chosen_model
                elif target_model.lower() == "list":
                    _print_model_selection(settings)
                    console.print()
                    continue
                if target_model == settings.model_alias or target_model == settings.model:
                    console.print("[yellow]Selected model is already active.[/yellow]")
                    console.print()
                    continue
                try:
                    model, new_settings = _switch_chat_model(
                        session_id=session_id,
                        storage=storage,
                        target_model=target_model,
                    )
                except ValueError as exc:
                    console.print(f"[bold red]Model switch failed:[/bold red] {exc}")
                    console.print()
                    continue
                settings = new_settings
                system_prompt = normalize_text(settings.system_prompt)
                token_counter = TokenCounter(settings.model)
                pricing = ModelPricing(
                    input_per_1m=settings.input_cost_per_1m,
                    output_per_1m=settings.output_cost_per_1m,
                )
                context_manager = ContextManager(storage=storage, token_counter=token_counter)
                console.print(
                    "[yellow]Model switched to "
                    f"{_safe_console_text(_format_model_details(settings))}.[/yellow]"
                )
                if token_counter.fallback:
                    console.print(
                        "[dim yellow]"
                        "tiktoken is not installed, token counts are approximate."
                        "[/dim yellow]"
                    )
                console.print()
                continue
            if command == "/compact":
                try:
                    summary_saved = _compact_history_with_llm(
                        model=model,
                        storage=storage,
                        session_id=session_id,
                        token_counter=token_counter,
                    )
                except Exception as exc:  # pragma: no cover
                    console.print(f"[bold red]Compaction failed:[/bold red] {exc}")
                    console.print()
                    continue
                if summary_saved:
                    console.print("[yellow]History compacted into one summary.[/yellow]")
                else:
                    console.print("[yellow]Nothing to compact yet.[/yellow]")
                message_records = storage.load_message_records(session_id)
                console.print()
                continue
            if command == "/memory":
                if not memory_commands_enabled:
                    console.print("[yellow]Memory layers are available only for context=memory.[/yellow]")
                    console.print()
                    continue
                _print_memory_layers(
                    storage=storage,
                    session_id=session_id,
                    message_records=message_records,
                    window_messages=session_config.window_messages,
                )
                console.print()
                continue
            if command == "/checkpoint":
                if not branch_commands_enabled:
                    console.print("[yellow]Checkpoint is available only for context=branching.[/yellow]")
                    console.print()
                    continue
                checkpoint_name = user_text[len("/checkpoint"):].strip()
                if not checkpoint_name:
                    console.print("[yellow]Usage: /checkpoint <name>[/yellow]")
                    console.print()
                    continue
                try:
                    checkpoint = storage.create_checkpoint(session_id, checkpoint_name)
                except ValueError as exc:
                    console.print(f"[bold red]Checkpoint failed:[/bold red] {exc}")
                    console.print()
                    continue
                console.print(
                    f"[yellow]Checkpoint '{checkpoint.name}' saved on branch "
                    f"'{checkpoint.branch_name}' at message #{checkpoint.message_id}.[/yellow]"
                )
                console.print()
                continue
            if command == "/branch":
                if not branch_commands_enabled:
                    console.print("[yellow]Branches are available only for context=branching.[/yellow]")
                    console.print()
                    continue
                parts = user_text.split(maxsplit=2)
                if len(parts) < 3:
                    console.print("[yellow]Usage: /branch <checkpoint> <new-branch>[/yellow]")
                    console.print()
                    continue
                try:
                    created_branch = storage.create_branch(session_id, parts[1], parts[2])
                except Exception as exc:  # pragma: no cover
                    console.print(f"[bold red]Branch creation failed:[/bold red] {exc}")
                    console.print()
                    continue
                console.print(
                    f"[yellow]Branch '{created_branch.name}' created from "
                    f"'{created_branch.parent_name}' at message #{created_branch.fork_message_id}.[/yellow]"
                )
                console.print()
                continue
            if command == "/branches":
                if not branch_commands_enabled:
                    console.print("[yellow]Branches are available only for context=branching.[/yellow]")
                    console.print()
                    continue
                _print_branches(storage.list_branches(session_id))
                console.print()
                continue
            if command == "/switch":
                if not branch_commands_enabled:
                    console.print("[yellow]Branch switch is available only for context=branching.[/yellow]")
                    console.print()
                    continue
                branch_name = user_text[len("/switch"):].strip()
                if not branch_name:
                    console.print("[yellow]Usage: /switch <branch-name>[/yellow]")
                    console.print()
                    continue
                try:
                    switched = storage.switch_branch(session_id, branch_name)
                except ValueError as exc:
                    console.print(f"[bold red]Switch failed:[/bold red] {exc}")
                    console.print()
                    continue
                message_records = storage.load_message_records(session_id)
                console.print(f"[yellow]Switched to branch '{switched.name}'.[/yellow]")
                console.print()
                continue
            console.print(
                "[yellow]Unknown command. Available commands: "
                "/exit, /clear, /debug, /stats, /summary, /compact, /model, "
                "/memory, /checkpoint, /branch, /branches, /switch[/yellow]"
            )
            console.print()
            continue

        user_text = normalize_text(user_text)
        user_tokens = token_counter.count_text(user_text)
        storage.append_message(session_id, "user", user_text, token_count=user_tokens)
        message_records = storage.load_message_records(session_id)
        context = context_manager.build_messages(
            session_id=session_id,
            message_records=message_records,
        )
        messages = context.messages
        estimated_prompt_tokens = token_counter.count_messages(messages)
        if estimated_prompt_tokens > settings.model_context_limit:
            console.print(
                "[dim red]"
                f"Token warning: estimated prompt {estimated_prompt_tokens} "
                f"> limit {settings.model_context_limit}. "
                "Request may fail with context length error."
                "[/dim red]"
            )

        try:
            console.print("[bold blue]Assistant:[/bold blue] ", end="")
            reply = model.reply_stream(
                messages,
                on_delta=lambda chunk: console.print(
                    chunk, end="", markup=False, highlight=False
                ),
            )
            console.print()
        except BadRequestError as exc:  # pragma: no cover
            console.print()
            error_text = str(exc)
            if "maximum context length" in error_text.lower() or "context_length_exceeded" in error_text.lower():
                console.print(
                    "[bold red]Request failed:[/bold red] "
                    "context length exceeded. Use /clear or shorten history."
                )
                console.print(
                    "[dim]"
                    f"Estimated prompt tokens: {estimated_prompt_tokens} "
                    f"(limit: {settings.model_context_limit})"
                    "[/dim]"
                )
            else:
                console.print(f"[bold red]Request failed:[/bold red] {exc}")
            console.print()
            message_records = storage.load_message_records(session_id)
            continue
        except Exception as exc:  # pragma: no cover
            console.print()
            console.print(f"[bold red]Request failed:[/bold red] {exc}")
            console.print()
            message_records = storage.load_message_records(session_id)
            continue

        assistant_text = normalize_text(reply.text)
        assistant_tokens = token_counter.count_text(assistant_text)
        request_input_tokens = reply.usage.input_tokens if reply.usage else None
        request_output_tokens = reply.usage.output_tokens if reply.usage else None
        storage.append_message(
            session_id,
            "assistant",
            assistant_text,
            token_count=assistant_tokens,
            request_input_tokens=request_input_tokens,
            request_output_tokens=request_output_tokens,
        )
        message_records = storage.load_message_records(session_id)
        if debug_enabled:
            actual_prompt = request_input_tokens if request_input_tokens is not None else estimated_prompt_tokens
            actual_output = request_output_tokens if request_output_tokens is not None else assistant_tokens
            estimated_cost = pricing.estimate_cost(actual_prompt, actual_output)
            console.print(
                "[dim]"
                f"tokens: request={user_tokens} prompt={actual_prompt} "
                f"answer={actual_output} total={actual_prompt + actual_output} "
                f"cost~${estimated_cost:.6f}"
                "[/dim]"
            )
            if context.summarized_chunks > 0:
                console.print(
                    "[dim]"
                    f"context compression: +{context.summarized_chunks} summary chunk(s)"
                    "[/dim]"
                )
            _print_debug_snapshot(
                storage=storage,
                session_id=session_id,
                session_config=session_config,
                message_records=message_records,
            )
        console.print()


def _print_session_stats(stats: SessionTokenStats, pricing: ModelPricing) -> None:
    table = Table(title="Token Stats (current chat history)")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Messages total", str(stats.message_count))
    table.add_row("User / Assistant / System", f"{stats.user_messages} / {stats.assistant_messages} / {stats.system_messages}")
    table.add_row("Content tokens total", str(stats.content_tokens))
    table.add_row("User tokens", str(stats.user_tokens))
    table.add_row("Assistant tokens", str(stats.assistant_tokens))
    table.add_row("System tokens", str(stats.system_tokens))
    table.add_row("Billed input tokens", str(stats.billed_input_tokens))
    table.add_row("Billed output tokens", str(stats.billed_output_tokens))
    table.add_row("Billed total tokens", str(stats.billed_total_tokens))
    if pricing.input_per_1m > 0 or pricing.output_per_1m > 0:
        table.add_row(
            "Estimated billed cost",
            f"${pricing.estimate_cost(stats.billed_input_tokens, stats.billed_output_tokens):.6f}",
        )
    console.print(table)


def _print_session_summaries(summaries: list[SessionSummaryRecord]) -> None:
    if not summaries:
        console.print("[yellow]No summaries yet.[/yellow]")
        return
    table = Table(title="Conversation Summary Chunks")
    table.add_column("No.", justify="right")
    table.add_column("Range", justify="right")
    table.add_column("Summary")
    for index, summary in enumerate(summaries, start=1):
        table.add_row(
            str(index),
            f"{summary.start_message_id}-{summary.end_message_id}",
            _safe_console_text(summary.content),
        )
    console.print(table)


def _print_branches(branches: list[BranchRecord]) -> None:
    if not branches:
        console.print("[yellow]No branches yet.[/yellow]")
        return
    table = Table(title="Branches")
    table.add_column("Name")
    table.add_column("Parent")
    table.add_column("Fork Msg", justify="right")
    table.add_column("Active", justify="center")
    for branch in branches:
        table.add_row(
            _safe_console_text(branch.name),
            _safe_console_text(branch.parent_name or "-"),
            str(branch.fork_message_id) if branch.fork_message_id is not None else "-",
            "yes" if branch.is_active else "",
        )
    console.print(table)


def _print_memory_layers(
    storage: ChatStorage,
    session_id: str,
    message_records: list,
    window_messages: int,
) -> None:
    short_term = [
        row for row in message_records
        if row.role != "system"
    ][-max(1, window_messages):]
    working = storage.list_working_memory(session_id)
    long_term = storage.list_long_term_memory(session_id)

    _print_memory_records(
        title="Short-Term Memory",
        records=[MemoryRecord(key=row.role, value=row.content) for row in short_term],
    )
    _print_memory_records(title="Working Memory", records=working)
    _print_memory_records(title="Long-Term Memory", records=long_term)


def _print_debug_snapshot(
    storage: ChatStorage,
    session_id: str,
    session_config,
    message_records: list,
) -> None:
    console.print(
        f"[dim]debug snapshot: context={session_config.strategy} session={session_id}[/dim]"
    )
    if session_config.strategy == "memory":
        _print_memory_layers(
            storage=storage,
            session_id=session_id,
            message_records=message_records,
            window_messages=session_config.window_messages,
        )
        return

    short_term = [
        row for row in message_records
        if row.role != "system"
    ][-max(1, session_config.window_messages):]
    _print_memory_records(
        title="Short-Term Memory",
        records=[MemoryRecord(key=row.role, value=row.content) for row in short_term],
    )
    console.print("[dim]Working Memory: unavailable for this context strategy.[/dim]")
    console.print("[dim]Long-Term Memory: unavailable for this context strategy.[/dim]")


def _print_memory_records(title: str, records: list[MemoryRecord]) -> None:
    if not records:
        console.print(f"[yellow]{title}: empty.[/yellow]")
        return
    table = Table(title=title)
    table.add_column("Key")
    table.add_column("Value")
    for item in records:
        table.add_row(
            _safe_console_text(item.key),
            _safe_console_text(item.value),
        )
    console.print(table)


def _compact_history_with_llm(
    model: ChatModel,
    storage: ChatStorage,
    session_id: str,
    token_counter: TokenCounter,
) -> bool:
    records = storage.load_message_records(session_id)
    non_system = [row for row in records if row.role != "system" and row.id is not None]
    if not non_system:
        return False

    transcript = "\n".join(
        f"{row.role}: {' '.join(row.content.strip().split())}"
        for row in non_system
    )
    summary_prompt = [
        {
            "role": "system",
            "content": (
                "Summarize chat history compactly. Preserve facts, decisions, "
                "constraints, and unresolved tasks. Keep it concise."
            ),
        },
        {"role": "user", "content": transcript},
    ]
    summary_reply = model.reply(summary_prompt)
    summary_text = summary_reply.text.strip()
    if not summary_text:
        return False

    storage.clear_session_summaries(session_id)
    storage.append_session_summary(
        session_id=session_id,
        start_message_id=int(non_system[0].id),
        end_message_id=int(non_system[-1].id),
        summary_text=summary_text,
        token_count=token_counter.count_text(summary_text),
    )
    return True


def _print_token_scenarios(settings: Settings) -> None:
    token_counter = TokenCounter(settings.model)
    pricing = ModelPricing(
        input_per_1m=settings.input_cost_per_1m,
        output_per_1m=settings.output_cost_per_1m,
    )
    system = {"role": "system", "content": settings.system_prompt}
    short_dialog = [
        system,
        {"role": "user", "content": "Привет"},
        {"role": "assistant", "content": "Привет! Чем помочь?"},
        {"role": "user", "content": "Сделай короткий список задач на день."},
    ]
    long_dialog = short_dialog + [
        {"role": "assistant", "content": "1) Почта 2) Код-ревью 3) Митинг 4) Отчёт"},
        {"role": "user", "content": "Добавь детали по каждому пункту и риски." * 60},
        {"role": "assistant", "content": "Детали..." * 200},
    ]
    overflow_dialog = long_dialog + [
        {"role": "user", "content": "Повтори весь диалог и дай итог." * 600}
    ]

    scenarios = [
        ("Short dialog", short_dialog),
        ("Long dialog", long_dialog),
        ("Overflow dialog", overflow_dialog),
    ]
    table = Table(title="Token Growth Scenarios")
    table.add_column("Scenario")
    table.add_column("Prompt tokens", justify="right")
    table.add_column("Vs limit", justify="right")
    table.add_column("Estimated input cost", justify="right")

    for name, messages in scenarios:
        prompt_tokens = token_counter.count_messages(messages)
        pct = (prompt_tokens / settings.model_context_limit) * 100
        cost = pricing.estimate_cost(prompt_tokens, 0)
        status = f"{pct:.1f}%"
        if prompt_tokens > settings.model_context_limit:
            status = f"{pct:.1f}% (OVER)"
        table.add_row(name, str(prompt_tokens), status, f"${cost:.6f}")

    console.print(table)
    console.print(
        "[dim]"
        "When prompt tokens exceed model context limit, API request fails with "
        "context length exceeded (HTTP 400 / context_length_exceeded)."
        "[/dim]"
    )


def _print_sessions_table(sessions: list[SessionSummary]) -> None:
    table = Table(title="Saved Sessions")
    table.add_column("No.", justify="right")
    table.add_column("Session ID", justify="right")
    table.add_column("Title")
    table.add_column("Messages", justify="right")
    table.add_column("Updated At")

    for index, session in enumerate(sessions, start=1):
        table.add_row(
            str(index),
            str(session.session_id),
            session.title,
            str(session.message_count),
            _format_datetime(session.updated_at),
        )
    console.print(table)


def _format_datetime(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    return dt.astimezone().strftime("%d.%m.%Y %H:%M")


def _print_chat_history(messages: list[dict[str, str]]) -> None:
    console.print("[bold cyan]Loaded chat history:[/bold cyan]")
    console.print()
    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        if role == "user":
            console.print(f"[bold green]You:[/bold green] {_safe_console_text(content)}")
        elif role == "assistant":
            console.print(f"[bold blue]Assistant:[/bold blue] {_safe_console_text(content)}")
        else:
            console.print(f"[dim]System:[/dim] {_safe_console_text(content)}")
        console.print()


def _read_single_key() -> str:
    if os.name == "nt":
        return msvcrt.getwch()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _choose_session_interactive(sessions: list[SessionSummary]) -> str | None:
    if not sys.stdin.isatty():
        while True:
            selected = console.input(
                "[bold green]Choose session number (or /cancel):[/bold green] "
            ).strip()
            if selected == "/cancel":
                return None
            if not selected.isdigit():
                console.print("[yellow]Please enter a valid number.[/yellow]")
                continue
            idx = int(selected)
            if idx < 1 or idx > len(sessions):
                console.print("[yellow]Number out of range.[/yellow]")
                continue
            return sessions[idx - 1].session_id

    console.print("[bold green]Choose session number (Esc to cancel):[/bold green] ", end="")
    typed = ""
    while True:
        key = _read_single_key()
        if key == "\x1b":
            console.print()
            return None
        if key in {"\r", "\n"}:
            console.print()
            if not typed:
                console.print("[yellow]Please enter a valid number.[/yellow]")
                console.print(
                    "[bold green]Choose session number (Esc to cancel):[/bold green] ",
                    end="",
                )
                continue
            idx = int(typed)
            if idx < 1 or idx > len(sessions):
                console.print("[yellow]Number out of range.[/yellow]")
                typed = ""
                console.print(
                    "[bold green]Choose session number (Esc to cancel):[/bold green] ",
                    end="",
                )
                continue
            return sessions[idx - 1].session_id
        if key in {"\x7f", "\b"}:
            if typed:
                typed = typed[:-1]
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue
        if key.isdigit():
            typed += key
            sys.stdout.write(key)
            sys.stdout.flush()


@app.command()
def chat(
    model_name: str | None = typer.Option(
        None,
        "--model",
        help="Model profile alias or raw model name.",
    ),
    context_strategy: str = typer.Option(
        "full",
        "--contenxt",
        "--context",
        help="Context strategy: full, sum, sliding, facts, branching, memory",
    ),
    summary_after_user_messages: int = typer.Option(
        10,
        "--summary-after-user-messages",
        min=1,
        help="For context=sum: summarize after this many user messages in old history.",
    ),
    window_messages: int = typer.Option(
        6,
        "--window-messages",
        min=1,
        help="For context=sliding, facts, or memory: keep only the last N non-system messages.",
    ),
) -> None:
    """Start a new chat session."""
    model, storage, settings = _build_model(selected_model=model_name)
    normalized_strategy = context_strategy.strip().lower()
    if normalized_strategy not in {"full", "sum", "sliding", "facts", "branching", "memory"}:
        console.print(
            "[bold red]Invalid --context value. Use 'full', 'sum', 'sliding', "
            "'facts', 'branching', or 'memory'.[/bold red]"
        )
        raise typer.Exit(code=1)
    safe_system_prompt = normalize_text(settings.system_prompt)
    system_tokens = TokenCounter(settings.model).count_text(safe_system_prompt)
    session_id = storage.create_session(
        safe_system_prompt,
        token_count=system_tokens,
        context_strategy=normalized_strategy,
        summary_trigger_user_messages=summary_after_user_messages,
        context_window_messages=window_messages,
        model_alias=settings.model_alias,
    )
    _chat_loop(model, storage, session_id, settings)


@app.command()
def resume(
    session_id: str | None = typer.Option(None, "--id", "-i"),
    model_name: str | None = typer.Option(
        None,
        "--model",
        help="Model profile alias or raw model name.",
    ),
) -> None:
    """Resume an existing chat session."""
    storage = _build_storage()
    if session_id is not None:
        if not storage.session_exists(session_id):
            console.print(f"[bold red]Session #{session_id} not found.[/bold red]")
            raise typer.Exit(code=1)
        model, storage, settings = _build_model(
            selected_model=model_name,
            session_id=session_id,
            storage=storage,
        )
        if model_name is not None:
            storage.set_session_model_alias(session_id, settings.model_alias)
        _chat_loop(model, storage, session_id, settings, show_history=True)
        return

    sessions = storage.list_sessions(limit=30)
    if not sessions:
        console.print("[yellow]No saved sessions found. Starting a new one.[/yellow]")
        model, storage, settings = _build_model(selected_model=model_name, storage=storage)
        safe_system_prompt = normalize_text(settings.system_prompt)
        system_tokens = TokenCounter(settings.model).count_text(safe_system_prompt)
        session_id = storage.create_session(
            safe_system_prompt,
            token_count=system_tokens,
            model_alias=settings.model_alias,
        )
        _chat_loop(model, storage, session_id, settings)
        return

    _print_sessions_table(sessions)
    chosen_session_id = _choose_session_interactive(sessions)
    if chosen_session_id is None:
        console.print("[cyan]Resume canceled.[/cyan]")
        return
    model, storage, settings = _build_model(
        selected_model=model_name,
        session_id=chosen_session_id,
        storage=storage,
    )
    if model_name is not None:
        storage.set_session_model_alias(chosen_session_id, settings.model_alias)
    _chat_loop(model, storage, chosen_session_id, settings, show_history=True)


@app.command()
def sessions(limit: int = typer.Option(30, "--limit", "-n")) -> None:
    """Show saved sessions."""
    storage = _build_storage()
    saved = storage.list_sessions(limit=limit)
    if not saved:
        console.print("[yellow]No saved sessions.[/yellow]")
        return
    _print_sessions_table(saved)


@app.command("token-demo")
def token_demo() -> None:
    """Show token growth and overflow behavior on synthetic dialogs."""
    _, _, settings = _build_model()
    _print_token_scenarios(settings)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

from __future__ import annotations

import os
import sys
from datetime import datetime

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import load_settings
from .llm import ChatModel
from .storage import ChatStorage, SessionSummary

if os.name == "nt":
    import msvcrt
else:
    import termios
    import tty

app = typer.Typer(help="Interactive CLI chat agent")
console = Console()


def _build_model() -> tuple[ChatModel, ChatStorage, str]:
    try:
        settings = load_settings()
    except ValueError as exc:
        console.print(f"[bold red]Config error:[/bold red] {exc}")
        raise typer.Exit(code=1)

    model = ChatModel(
        api_key=settings.api_key,
        model=settings.model,
        base_url=settings.base_url,
    )
    storage = ChatStorage(settings.storage_path)
    storage.init()
    return model, storage, settings.system_prompt


def _chat_loop(
    model: ChatModel,
    storage: ChatStorage,
    session_id: str,
    system_prompt: str,
    show_history: bool = False,
) -> None:
    messages = storage.load_messages(session_id)
    if not messages:
        storage.clear_session(session_id, system_prompt)
        messages = storage.load_messages(session_id)

    console.print(
        Panel(
            "Interactive chat started.\n"
            "Commands: /exit, /clear",
            title=f"chat-agent | session #{session_id}",
            border_style="cyan",
        )
    )
    if show_history:
        _print_chat_history(messages)

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
                storage.clear_session(session_id, system_prompt)
                messages = storage.load_messages(session_id)
                console.print("[yellow]History cleared.[/yellow]")
                console.print()
                continue
            console.print(
                "[yellow]Unknown command. Available commands: /exit, /clear[/yellow]"
            )
            console.print()
            continue

        messages.append({"role": "user", "content": user_text})
        storage.append_message(session_id, "user", user_text)

        try:
            assistant_text = model.reply(messages)
        except Exception as exc:  # pragma: no cover
            console.print(f"[bold red]Request failed:[/bold red] {exc}")
            console.print()
            continue

        messages.append({"role": "assistant", "content": assistant_text})
        storage.append_message(session_id, "assistant", assistant_text)
        console.print(f"[bold blue]Assistant:[/bold blue] {assistant_text}")
        console.print()


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
            console.print(f"[bold green]You:[/bold green] {content}")
        elif role == "assistant":
            console.print(f"[bold blue]Assistant:[/bold blue] {content}")
        else:
            console.print(f"[dim]System:[/dim] {content}")
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
def chat() -> None:
    """Start a new chat session."""
    model, storage, system_prompt = _build_model()
    session_id = storage.create_session(system_prompt)
    _chat_loop(model, storage, session_id, system_prompt)


@app.command()
def resume(session_id: str | None = typer.Option(None, "--id", "-i")) -> None:
    """Resume an existing chat session."""
    model, storage, system_prompt = _build_model()
    if session_id is not None:
        if not storage.session_exists(session_id):
            console.print(f"[bold red]Session #{session_id} not found.[/bold red]")
            raise typer.Exit(code=1)
        _chat_loop(model, storage, session_id, system_prompt, show_history=True)
        return

    sessions = storage.list_sessions(limit=30)
    if not sessions:
        console.print("[yellow]No saved sessions found. Starting a new one.[/yellow]")
        session_id = storage.create_session(system_prompt)
        _chat_loop(model, storage, session_id, system_prompt)
        return

    _print_sessions_table(sessions)
    chosen_session_id = _choose_session_interactive(sessions)
    if chosen_session_id is None:
        console.print("[cyan]Resume canceled.[/cyan]")
        return
    _chat_loop(model, storage, chosen_session_id, system_prompt, show_history=True)


@app.command()
def sessions(limit: int = typer.Option(30, "--limit", "-n")) -> None:
    """Show saved sessions."""
    _, storage, _ = _build_model()
    saved = storage.list_sessions(limit=limit)
    if not saved:
        console.print("[yellow]No saved sessions.[/yellow]")
        return
    _print_sessions_table(saved)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

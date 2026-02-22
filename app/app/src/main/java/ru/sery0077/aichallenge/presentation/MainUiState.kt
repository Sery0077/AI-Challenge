package ru.sery0077.aichallenge.presentation

import ru.sery0077.aichallenge.domain.model.ChatMessage

data class MainUiState(
    val prompt: String = "",
    val messages: List<ChatMessage> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null,
    val settings: MainRequestSettings = MainRequestSettings(),
    val isApiKeyMissing: Boolean = false,
)

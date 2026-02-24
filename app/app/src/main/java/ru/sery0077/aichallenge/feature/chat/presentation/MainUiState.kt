package ru.sery0077.aichallenge.feature.chat.presentation

import ru.sery0077.aichallenge.feature.chat.domain.model.ChatMessage
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatSession
import ru.sery0077.aichallenge.feature.settings.presentation.MainRequestSettings

data class MainUiState(
    val prompt: String = "",
    val messages: List<ChatMessage> = emptyList(),
    val sessions: List<ChatSession> = emptyList(),
    val selectedSessionId: Long? = null,
    val defaultModel: String = "",
    val sessionModel: String = "",
    val isLoading: Boolean = false,
    val error: String? = null,
    val settings: MainRequestSettings = MainRequestSettings(),
    val isApiKeyMissing: Boolean = false,
)

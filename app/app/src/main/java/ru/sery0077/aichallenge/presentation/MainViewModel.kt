package ru.sery0077.aichallenge.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.onCompletion
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import ru.sery0077.aichallenge.domain.model.ChatMessage
import ru.sery0077.aichallenge.domain.model.ChatRole
import ru.sery0077.aichallenge.domain.model.RequestSettings
import ru.sery0077.aichallenge.domain.repository.RouterAIConfigRepository
import ru.sery0077.aichallenge.domain.usecase.SendPromptUseCase

class MainViewModel(
    private val sendPromptUseCase: SendPromptUseCase,
    private val configRepository: RouterAIConfigRepository,
    private val responseTextNormalizer: ResponseTextNormalizer,
) : ViewModel() {

    private val _uiState = MutableStateFlow(MainUiState())
    val uiState: StateFlow<MainUiState> = _uiState

    init {
        val isMissing = configRepository.getApiKey().isBlank()
        _uiState.update { it.copy(isApiKeyMissing = isMissing) }
    }

    fun onPromptChange(value: String) {
        _uiState.update { it.copy(prompt = value, error = null) }
    }

    fun onApplySettings(value: MainRequestSettings) {
        _uiState.update { it.copy(settings = value) }
    }
    fun onSendClick() {
        val stateSnapshot = _uiState.value
        val prompt = stateSnapshot.prompt.trim()
        val settings = mapSettings(stateSnapshot.settings)
        if (prompt.isBlank()) {
            _uiState.update { it.copy(error = "Enter a message") }
            return
        }
        val userMessage = ChatMessage(role = ChatRole.User, content = prompt)
        val uiMessages = stateSnapshot.messages + userMessage
        val requestMessages = if (stateSnapshot.settings.useHistory) {
            uiMessages
        } else {
            listOf(userMessage)
        }
        _uiState.update {
            it.copy(
                isLoading = true,
                error = null,
                prompt = "",
                messages = uiMessages + ChatMessage(role = ChatRole.Assistant, content = ""),
            )
        }
        viewModelScope.launch {
            sendPromptUseCase(requestMessages, settings)
                .onCompletion {
                    _uiState.update { it.copy(isLoading = false) }
                }
                .catch { throwable ->
                    _uiState.update {
                        val updatedMessages = if (it.messages.lastOrNull()?.content.isNullOrBlank()) {
                            it.messages.dropLast(1)
                        } else {
                            it.messages
                        }
                        it.copy(
                            isLoading = false,
                            error = throwable.message ?: "Request error",
                            messages = updatedMessages,
                        )
                    }
                }
                .collect { chunk ->
                    _uiState.update { state ->
                        val updatedMessages = state.messages.toMutableList()
                        if (updatedMessages.isNotEmpty()) {
                            val lastMessage = updatedMessages.last()
                            if (lastMessage.role == ChatRole.Assistant) {
                                val normalized = responseTextNormalizer.normalize(lastMessage.content + chunk)
                                updatedMessages[updatedMessages.lastIndex] =
                                    lastMessage.copy(content = normalized)
                            }
                        }
                        state.copy(messages = updatedMessages)
                    }
                }
        }
    }

    private fun mapSettings(settings: MainRequestSettings): RequestSettings {
        val maxTokens = settings.maxTokens.trim().toIntOrNull()
        val temperature = settings.temperature.trim().replace(",", ".").toDoubleOrNull()
        val stop = settings.stop
            .split(",", "\n", ";")
            .map { it.trim() }
            .filter { it.isNotBlank() }
            .ifEmpty { null }
        return RequestSettings(
            maxTokens = maxTokens,
            temperature = temperature,
            stop = stop,
            streamEnabled = settings.streamEnabled,
            useHistory = settings.useHistory,
        )
    }

}

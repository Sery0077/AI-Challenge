package ru.sery0077.aichallenge.feature.chat.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.onCompletion
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatMessage
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatRole
import ru.sery0077.aichallenge.feature.chat.domain.model.RequestSettings
import ru.sery0077.aichallenge.feature.chat.domain.repository.RouterAIConfigRepository
import ru.sery0077.aichallenge.feature.chat.domain.usecase.CreateSessionUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.GetSessionUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.InsertMessageUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.ObserveMessagesUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.ObserveSessionsUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.SendPromptUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.TouchSessionUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.UpdateSessionModelUseCase
import ru.sery0077.aichallenge.feature.chat.domain.usecase.UpdateSessionTitleUseCase
import ru.sery0077.aichallenge.feature.settings.presentation.MainRequestSettings
import ru.sery0077.aichallenge.util.ResponseTextNormalizer

class MainViewModel(
    private val sendPromptUseCase: SendPromptUseCase,
    private val configRepository: RouterAIConfigRepository,
    private val responseTextNormalizer: ResponseTextNormalizer,
    private val observeSessionsUseCase: ObserveSessionsUseCase,
    private val observeMessagesUseCase: ObserveMessagesUseCase,
    private val createSessionUseCase: CreateSessionUseCase,
    private val insertMessageUseCase: InsertMessageUseCase,
    private val updateSessionTitleUseCase: UpdateSessionTitleUseCase,
    private val updateSessionModelUseCase: UpdateSessionModelUseCase,
    private val touchSessionUseCase: TouchSessionUseCase,
    private val getSessionUseCase: GetSessionUseCase,
) : ViewModel() {

    private val _uiState = MutableStateFlow(MainUiState())
    val uiState: StateFlow<MainUiState> = _uiState

    private var messagesJob: Job? = null
    private var pendingAssistantContent: String? = null

    init {
        val isMissing = configRepository.getApiKey().isBlank()
        val defaultModel = configRepository.getModel()
        _uiState.update { it.copy(isApiKeyMissing = isMissing, defaultModel = defaultModel) }

        viewModelScope.launch {
            observeSessionsUseCase().collectLatest { sessions ->
                _uiState.update { it.copy(sessions = sessions) }
                val selected = _uiState.value.selectedSessionId
                if (selected == null && sessions.isNotEmpty()) {
                    selectSessionInternal(sessions.first().id)
                }
                if (sessions.isEmpty()) {
                    createAndSelectSession()
                }
            }
        }
    }

    fun onPromptChange(value: String) {
        _uiState.update { it.copy(prompt = value, error = null) }
    }

    fun onApplySettings(value: MainRequestSettings) {
        _uiState.update { it.copy(settings = value) }
    }

    fun onApplyModels(defaultModel: String, sessionModel: String) {
        val trimmedDefault = defaultModel.trim()
        if (trimmedDefault.isNotBlank()) {
            configRepository.updateModel(trimmedDefault)
            _uiState.update { it.copy(defaultModel = trimmedDefault) }
        }
        val sessionId = _uiState.value.selectedSessionId ?: return
        val trimmedSession = sessionModel.trim()
        if (trimmedSession.isNotBlank()) {
            viewModelScope.launch {
                val timestamp = System.currentTimeMillis()
                updateSessionModelUseCase(sessionId, trimmedSession, timestamp)
                _uiState.update { it.copy(sessionModel = trimmedSession) }
            }
        }
    }

    fun onSelectSession(sessionId: Long) {
        selectSessionInternal(sessionId)
    }

    fun onNewSessionClick() {
        viewModelScope.launch {
            createAndSelectSession()
        }
    }

    fun onSendClick() {
        val stateSnapshot = _uiState.value
        val prompt = stateSnapshot.prompt.trim()
        if (prompt.isBlank()) {
            _uiState.update { it.copy(error = "Enter a message") }
            return
        }
        val settings = mapSettings(stateSnapshot.settings, stateSnapshot.sessionModel)

        viewModelScope.launch {
            val sessionId = stateSnapshot.selectedSessionId ?: createAndSelectSession()
            val now = System.currentTimeMillis()
            val userMessage = ChatMessage(role = ChatRole.User, content = prompt)
            val uiMessages = stateSnapshot.messages + userMessage
            pendingAssistantContent = ""

            _uiState.update {
                it.copy(
                    isLoading = true,
                    error = null,
                    prompt = "",
                    messages = uiMessages + ChatMessage(role = ChatRole.Assistant, content = ""),
                )
            }

            insertMessageUseCase(
                sessionId = sessionId,
                role = ChatRole.User.apiName,
                content = prompt,
                timestamp = now,
            )
            touchSessionUseCase(sessionId, now)
            maybeUpdateTitle(sessionId, prompt, now)

            val requestMessages = uiMessages

            sendPromptUseCase(requestMessages, settings)
                .onCompletion {
                    _uiState.update { it.copy(isLoading = false) }
                    val assistantContent = pendingAssistantContent
                    pendingAssistantContent = null
                    if (!assistantContent.isNullOrBlank()) {
                        val timestamp = System.currentTimeMillis()
                        insertMessageUseCase(
                            sessionId = sessionId,
                            role = ChatRole.Assistant.apiName,
                            content = assistantContent,
                            timestamp = timestamp,
                        )
                        touchSessionUseCase(sessionId, timestamp)
                    } else {
                        _uiState.update { state ->
                            val trimmedMessages = state.messages.dropLast(1)
                            state.copy(messages = trimmedMessages)
                        }
                    }
                }
                .catch { throwable ->
                    pendingAssistantContent = null
                    _uiState.update { state ->
                        val trimmedMessages = if (state.messages.lastOrNull()?.role == ChatRole.Assistant) {
                            state.messages.dropLast(1)
                        } else {
                            state.messages
                        }
                        state.copy(
                            isLoading = false,
                            error = throwable.message ?: "Request error",
                            messages = trimmedMessages,
                        )
                    }
                }
                .collect { chunk ->
                    val normalized = responseTextNormalizer.normalize((pendingAssistantContent ?: "") + chunk)
                    pendingAssistantContent = normalized
                    _uiState.update { state ->
                        val updatedMessages = state.messages.toMutableList()
                        if (updatedMessages.isNotEmpty()) {
                            val lastMessage = updatedMessages.last()
                            if (lastMessage.role == ChatRole.Assistant) {
                                updatedMessages[updatedMessages.lastIndex] =
                                    lastMessage.copy(content = normalized)
                            }
                        }
                        state.copy(messages = updatedMessages)
                    }
                }
        }
    }

    private fun mapSettings(settings: MainRequestSettings, sessionModel: String): RequestSettings {
        val maxTokens = settings.maxTokens.trim().toIntOrNull()
        val temperature = settings.temperature.trim().replace(",", ".").toDoubleOrNull()
        val stop = settings.stop
            .split(",", "\n", ";")
            .map { it.trim() }
            .filter { it.isNotBlank() }
            .ifEmpty { null }
        val modelOverride = sessionModel.trim().ifBlank { null }
        return RequestSettings(
            maxTokens = maxTokens,
            temperature = temperature,
            stop = stop,
            streamEnabled = settings.streamEnabled,
            modelOverride = modelOverride,
        )
    }

    private suspend fun createAndSelectSession(): Long {
        val timestamp = System.currentTimeMillis()
        val model = _uiState.value.defaultModel.ifBlank { configRepository.getModel() }
        val sessionId = createSessionUseCase("New chat", model, timestamp)
        _uiState.update { it.copy(sessionModel = model) }
        selectSessionInternal(sessionId)
        return sessionId
    }

    private fun selectSessionInternal(sessionId: Long) {
        pendingAssistantContent = null
        messagesJob?.cancel()
        _uiState.update {
            it.copy(
                selectedSessionId = sessionId,
                messages = emptyList(),
                error = null,
            )
        }
        viewModelScope.launch {
            val session = getSessionUseCase(sessionId)
            if (session != null) {
                _uiState.update { it.copy(sessionModel = session.model) }
            }
        }
        messagesJob = viewModelScope.launch {
            observeMessagesUseCase(sessionId).collectLatest { messages ->
                _uiState.update { state ->
                    state.copy(messages = mergeMessages(messages))
                }
            }
        }
    }

    private fun mergeMessages(messages: List<ChatMessage>): List<ChatMessage> {
        val pending = pendingAssistantContent
        return if (pending != null) {
            messages + ChatMessage(ChatRole.Assistant, pending)
        } else {
            messages
        }
    }

    private suspend fun maybeUpdateTitle(sessionId: Long, prompt: String, timestamp: Long) {
        val session = getSessionUseCase(sessionId) ?: return
        if (session.title != "New chat") return
        val trimmed = prompt.trim().replace("\n", " ").take(48)
        if (trimmed.isNotBlank()) {
            updateSessionTitleUseCase(sessionId, trimmed, timestamp)
        }
    }
}

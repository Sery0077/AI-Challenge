package ru.sery0077.aichallenge.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.onCompletion
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import ru.sery0077.aichallenge.domain.model.RequestSettings
import ru.sery0077.aichallenge.domain.repository.RouterAIConfigRepository
import ru.sery0077.aichallenge.domain.usecase.SendPromptUseCase

class MainViewModel(
    private val sendPromptUseCase: SendPromptUseCase,
    private val configRepository: RouterAIConfigRepository,
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
        val prompt = stateSnapshot.prompt
        val settings = mapSettings(stateSnapshot.settings)
        _uiState.update {
            it.copy(
                isLoading = true,
                error = null,
                response = "",
                formattedResponse = AnnotatedString(""),
            )
        }
        viewModelScope.launch {
            sendPromptUseCase(prompt, settings)
                .onCompletion {
                    _uiState.update { it.copy(isLoading = false) }
                }
                .catch { throwable ->
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            error = throwable.message ?: "Ошибка запроса",
                        )
                    }
                }
                .collect { chunk ->
                    _uiState.update { state ->
                        val updatedResponse = state.response + chunk
                        val normalizedResponse = normalizeMarkdown(updatedResponse)
                        state.copy(
                            response = normalizedResponse,
                            formattedResponse = buildMarkdownAnnotatedString(normalizedResponse),
                        )
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
        )
    }

    private fun buildMarkdownAnnotatedString(text: String): AnnotatedString = buildAnnotatedString {
        val lines = text.split("\n")
        lines.forEachIndexed { index, line ->
            val trimmed = line.trimStart()
            val (style, content) = when {
                trimmed.startsWith("###") -> SpanStyle(
                    fontSize = 18.sp,
                    fontWeight = FontWeight.SemiBold,
                ) to trimmed.removePrefix("###").trimStart()
                trimmed.startsWith("##") -> SpanStyle(
                    fontSize = 20.sp,
                    fontWeight = FontWeight.SemiBold,
                ) to trimmed.removePrefix("##").trimStart()
                trimmed.startsWith("#") -> SpanStyle(
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Bold,
                ) to trimmed.removePrefix("#").trimStart()
                else -> SpanStyle() to line
            }

            pushStyle(style)
            appendBoldSegments(content)
            pop()

            if (index != lines.lastIndex) {
                append("\n\n")
            }
        }
    }

    private fun AnnotatedString.Builder.appendBoldSegments(text: String) {
        var index = 0
        while (index < text.length) {
            val nextDoubleAsterisk = text.indexOf("**", index)
            val nextDoubleUnderscore = text.indexOf("__", index)
            val start = when {
                nextDoubleAsterisk == -1 -> nextDoubleUnderscore
                nextDoubleUnderscore == -1 -> nextDoubleAsterisk
                else -> minOf(nextDoubleAsterisk, nextDoubleUnderscore)
            }

            if (start == -1) {
                append(text.substring(index))
                break
            }

            if (start > index) {
                append(text.substring(index, start))
            }

            val delimiter = if (text.startsWith("**", start)) "**" else "__"
            val end = text.indexOf(delimiter, start + 2)
            if (end == -1) {
                append(text.substring(start))
                break
            }

            pushStyle(SpanStyle(fontWeight = FontWeight.Bold))
            append(text.substring(start + 2, end))
            pop()
            index = end + 2
        }
    }

    private fun normalizeMarkdown(text: String): String {
        // Unescape common sequences that can come from JSON text.
        return text
            .replace("\\r\\n", "\n")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
    }
}

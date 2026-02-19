package ru.sery0077.aichallenge.presentation

import androidx.compose.ui.text.AnnotatedString

data class MainUiState(
    val prompt: String = "",
    val response: String = "",
    val formattedResponse: AnnotatedString = AnnotatedString(""),
    val isLoading: Boolean = false,
    val error: String? = null,
    val settings: MainRequestSettings = MainRequestSettings(),
    val isApiKeyMissing: Boolean = false,
)

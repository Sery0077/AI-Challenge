package ru.sery0077.aichallenge.feature.chat.domain.model

data class RequestSettings(
    val maxTokens: Int? = null,
    val temperature: Double? = null,
    val stop: List<String>? = null,
    val streamEnabled: Boolean = true,
    val modelOverride: String? = null,
)

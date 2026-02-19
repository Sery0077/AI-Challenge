package ru.sery0077.aichallenge.presentation

data class MainRequestSettings(
    val maxTokens: String = "",
    val temperature: String = "",
    val stop: String = "",
    val streamEnabled: Boolean = true,
)

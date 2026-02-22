package ru.sery0077.aichallenge.domain.model

data class ChatMessage(
    val role: ChatRole,
    val content: String,
)

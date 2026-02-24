package ru.sery0077.aichallenge.feature.chat.domain.model

data class ChatSession(
    val id: Long,
    val title: String,
    val model: String,
    val createdAt: Long,
    val updatedAt: Long,
)

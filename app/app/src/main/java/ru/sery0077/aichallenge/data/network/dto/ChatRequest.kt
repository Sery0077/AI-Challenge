package ru.sery0077.aichallenge.data.network.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ChatRequest(
    val model: String,
    val messages: List<MessageDto>,
    val stream: Boolean? = null,
    @SerialName("max_tokens")
    val maxTokens: Int? = null,
    val temperature: Double? = null,
    val stop: List<String>? = null,
)

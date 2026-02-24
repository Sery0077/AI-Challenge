package ru.sery0077.aichallenge.feature.chat.data.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class ChatStreamChunk(
    val choices: List<StreamChoiceDto> = emptyList(),
    val error: StreamErrorDto? = null,
)

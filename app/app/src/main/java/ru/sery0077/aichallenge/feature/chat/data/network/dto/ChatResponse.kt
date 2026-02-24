package ru.sery0077.aichallenge.feature.chat.data.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class ChatResponse(
    val choices: List<ChoiceDto> = emptyList(),
)

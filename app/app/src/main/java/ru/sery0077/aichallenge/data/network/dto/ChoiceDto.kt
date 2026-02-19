package ru.sery0077.aichallenge.data.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class ChoiceDto(
    val message: MessageDto? = null,
)

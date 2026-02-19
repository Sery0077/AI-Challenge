package ru.sery0077.aichallenge.data.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class MessageDto(
    val role: String,
    val content: String,
)

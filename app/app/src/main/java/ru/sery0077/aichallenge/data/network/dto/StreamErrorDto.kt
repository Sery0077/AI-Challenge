package ru.sery0077.aichallenge.data.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class StreamErrorDto(
    val message: String? = null,
    val code: String? = null,
)

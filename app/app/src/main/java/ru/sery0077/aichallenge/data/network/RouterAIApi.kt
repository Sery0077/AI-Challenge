package ru.sery0077.aichallenge.data.network

import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.POST
import ru.sery0077.aichallenge.data.network.dto.ChatRequest
import ru.sery0077.aichallenge.data.network.dto.ChatResponse

interface RouterAIApi {
    @POST("chat/completions")
    suspend fun createChatCompletion(
        @Body request: ChatRequest,
        @Header("Authorization") authorization: String,
    ): ChatResponse
}

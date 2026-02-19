package ru.sery0077.aichallenge.data.repository

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import android.util.Log
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okio.IOException
import ru.sery0077.aichallenge.data.network.dto.ChatRequest
import ru.sery0077.aichallenge.data.network.dto.ChatResponse
import ru.sery0077.aichallenge.data.network.dto.ChatStreamChunk
import ru.sery0077.aichallenge.data.network.dto.MessageDto
import ru.sery0077.aichallenge.domain.model.RequestSettings
import ru.sery0077.aichallenge.domain.repository.RouterAIConfigRepository
import ru.sery0077.aichallenge.domain.repository.RouterAIRepository

class RouterAIRepositoryImpl(
    private val client: OkHttpClient,
    private val json: Json,
    private val configRepository: RouterAIConfigRepository,
) : RouterAIRepository {
    override fun streamPrompt(prompt: String, settings: RequestSettings): Flow<String> = flow {
        val baseUrl = configRepository.getBaseUrl()
        val model = configRepository.getModel()
        val apiKey = configRepository.getApiKey()
        val requestBody = ChatRequest(
            model = model,
            messages = listOf(MessageDto(role = "user", content = prompt)),
            stream = settings.streamEnabled,
            maxTokens = settings.maxTokens,
            temperature = settings.temperature,
            stop = settings.stop,
        )
        val bodyString = json.encodeToString(requestBody)
        Log.d("RouterAI", "Request body: $bodyString")
        val body = bodyString.toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url("${baseUrl}chat/completions")
            .header("Authorization", "Bearer $apiKey")
            .post(body)
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("HTTP ${response.code}: ${response.message}")
            }

            if (settings.streamEnabled) {
                val source = response.body?.source() ?: throw IOException("Empty response body")
                while (true) {
                    val line = source.readUtf8Line() ?: break
                    if (line.isBlank()) continue
                    if (line.startsWith(":")) continue
                    if (!line.startsWith("data:")) continue

                    val data = line.removePrefix("data:").trim()
                    if (data == "[DONE]") break

                    val chunk = json.decodeFromString<ChatStreamChunk>(data)
                    val errorMessage = chunk.error?.message
                    if (!errorMessage.isNullOrBlank()) {
                        throw IOException(errorMessage)
                    }
                    val content = chunk.choices.firstOrNull()?.delta?.content
                    if (!content.isNullOrBlank()) emit(content)
                    if (!content.isNullOrBlank()) Log.d("RouterAI", "Response chunk: $content")
                }
            } else {
                val bodyText = response.body?.string() ?: throw IOException("Empty response body")
                Log.d("RouterAI", "Response body: $bodyText")
                val parsed = json.decodeFromString<ChatResponse>(bodyText)
                val content = parsed.choices.firstOrNull()?.message?.content
                if (content.isNullOrBlank()) {
                    throw IOException("Empty response content")
                } else {
                    emit(content)
                }
            }
        }
    }.flowOn(Dispatchers.IO)
}

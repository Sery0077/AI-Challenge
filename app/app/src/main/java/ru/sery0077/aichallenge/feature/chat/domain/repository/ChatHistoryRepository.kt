package ru.sery0077.aichallenge.feature.chat.domain.repository

import kotlinx.coroutines.flow.Flow
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatMessage
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatSession

interface ChatHistoryRepository {
    fun observeSessions(): Flow<List<ChatSession>>
    fun observeMessages(sessionId: Long): Flow<List<ChatMessage>>
    suspend fun createSession(title: String, model: String, timestamp: Long): Long
    suspend fun updateSessionTitle(sessionId: Long, title: String, timestamp: Long)
    suspend fun touchSession(sessionId: Long, timestamp: Long)
    suspend fun updateSessionModel(sessionId: Long, model: String, timestamp: Long)
    suspend fun insertMessage(
        sessionId: Long,
        role: String,
        content: String,
        timestamp: Long,
    ): Long
    suspend fun getSession(sessionId: Long): ChatSession?
}

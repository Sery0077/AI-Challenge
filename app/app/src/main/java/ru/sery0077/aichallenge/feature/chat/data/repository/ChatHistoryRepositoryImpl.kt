package ru.sery0077.aichallenge.feature.chat.data.repository

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import ru.sery0077.aichallenge.feature.chat.data.local.dao.ChatMessageDao
import ru.sery0077.aichallenge.feature.chat.data.local.dao.ChatSessionDao
import ru.sery0077.aichallenge.feature.chat.data.local.entity.ChatMessageEntity
import ru.sery0077.aichallenge.feature.chat.data.local.entity.ChatSessionEntity
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatMessage
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatRole
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatSession
import ru.sery0077.aichallenge.feature.chat.domain.repository.ChatHistoryRepository

class ChatHistoryRepositoryImpl(
    private val sessionDao: ChatSessionDao,
    private val messageDao: ChatMessageDao,
) : ChatHistoryRepository {
    override fun observeSessions(): Flow<List<ChatSession>> {
        return sessionDao.observeSessions().map { sessions ->
            sessions.map { it.toDomain() }
        }
    }

    override fun observeMessages(sessionId: Long): Flow<List<ChatMessage>> {
        return messageDao.observeMessages(sessionId).map { messages ->
            messages.map { it.toDomain() }
        }
    }

    override suspend fun createSession(title: String, model: String, timestamp: Long): Long {
        val entity = ChatSessionEntity(
            title = title,
            model = model,
            createdAt = timestamp,
            updatedAt = timestamp,
        )
        return sessionDao.insertSession(entity)
    }

    override suspend fun updateSessionTitle(sessionId: Long, title: String, timestamp: Long) {
        sessionDao.updateTitle(sessionId, title, timestamp)
    }

    override suspend fun touchSession(sessionId: Long, timestamp: Long) {
        sessionDao.touchSession(sessionId, timestamp)
    }

    override suspend fun updateSessionModel(sessionId: Long, model: String, timestamp: Long) {
        sessionDao.updateModel(sessionId, model, timestamp)
    }

    override suspend fun insertMessage(
        sessionId: Long,
        role: String,
        content: String,
        timestamp: Long,
    ): Long {
        val entity = ChatMessageEntity(
            sessionId = sessionId,
            role = role,
            content = content,
            createdAt = timestamp,
        )
        return messageDao.insertMessage(entity)
    }

    override suspend fun getSession(sessionId: Long): ChatSession? {
        return sessionDao.getSession(sessionId)?.toDomain()
    }

    private fun ChatSessionEntity.toDomain(): ChatSession {
        return ChatSession(
            id = id,
            title = title,
            model = model,
            createdAt = createdAt,
            updatedAt = updatedAt,
        )
    }

    private fun ChatMessageEntity.toDomain(): ChatMessage {
        return ChatMessage(
            role = role.toRole(),
            content = content,
        )
    }

    private fun String.toRole(): ChatRole {
        return when (this) {
            ChatRole.System.apiName -> ChatRole.System
            ChatRole.User.apiName -> ChatRole.User
            ChatRole.Assistant.apiName -> ChatRole.Assistant
            else -> ChatRole.Assistant
        }
    }
}

package ru.sery0077.aichallenge.feature.chat.domain.usecase

import ru.sery0077.aichallenge.feature.chat.domain.repository.ChatHistoryRepository

class InsertMessageUseCase(
    private val repository: ChatHistoryRepository,
) {
    suspend operator fun invoke(
        sessionId: Long,
        role: String,
        content: String,
        timestamp: Long,
    ): Long {
        return repository.insertMessage(sessionId, role, content, timestamp)
    }
}

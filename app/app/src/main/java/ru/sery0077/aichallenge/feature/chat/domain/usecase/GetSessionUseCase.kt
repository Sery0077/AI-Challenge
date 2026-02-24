package ru.sery0077.aichallenge.feature.chat.domain.usecase

import ru.sery0077.aichallenge.feature.chat.domain.model.ChatSession
import ru.sery0077.aichallenge.feature.chat.domain.repository.ChatHistoryRepository

class GetSessionUseCase(
    private val repository: ChatHistoryRepository,
) {
    suspend operator fun invoke(sessionId: Long): ChatSession? {
        return repository.getSession(sessionId)
    }
}

package ru.sery0077.aichallenge.feature.chat.domain.usecase

import ru.sery0077.aichallenge.feature.chat.domain.repository.ChatHistoryRepository

class TouchSessionUseCase(
    private val repository: ChatHistoryRepository,
) {
    suspend operator fun invoke(sessionId: Long, timestamp: Long) {
        repository.touchSession(sessionId, timestamp)
    }
}

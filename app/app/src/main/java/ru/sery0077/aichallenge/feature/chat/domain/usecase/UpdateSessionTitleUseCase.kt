package ru.sery0077.aichallenge.feature.chat.domain.usecase

import ru.sery0077.aichallenge.feature.chat.domain.repository.ChatHistoryRepository

class UpdateSessionTitleUseCase(
    private val repository: ChatHistoryRepository,
) {
    suspend operator fun invoke(sessionId: Long, title: String, timestamp: Long) {
        repository.updateSessionTitle(sessionId, title, timestamp)
    }
}

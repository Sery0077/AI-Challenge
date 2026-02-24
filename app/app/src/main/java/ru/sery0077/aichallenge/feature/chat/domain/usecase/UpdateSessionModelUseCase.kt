package ru.sery0077.aichallenge.feature.chat.domain.usecase

import ru.sery0077.aichallenge.feature.chat.domain.repository.ChatHistoryRepository

class UpdateSessionModelUseCase(
    private val repository: ChatHistoryRepository,
) {
    suspend operator fun invoke(sessionId: Long, model: String, timestamp: Long) {
        repository.updateSessionModel(sessionId, model, timestamp)
    }
}

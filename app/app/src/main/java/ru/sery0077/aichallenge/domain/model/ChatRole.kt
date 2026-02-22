package ru.sery0077.aichallenge.domain.model

enum class ChatRole(val apiName: String) {
    System("system"),
    User("user"),
    Assistant("assistant"),
}

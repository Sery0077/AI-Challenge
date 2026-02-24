package ru.sery0077.aichallenge.util

class ResponseTextNormalizer {
    fun normalize(text: String): String {
        return text
            .replace("\\r\\n", "\n")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\r", "\n")
    }
}

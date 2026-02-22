package ru.sery0077.aichallenge.presentation

class CodeIndentNormalizer {
    fun normalize(text: String): String {
        val lines = text.split("\n")
        val indents = lines
            .filter { it.isNotBlank() }
            .map { line -> line.takeWhile { it == ' ' || it == '\t' }.length }
        val minIndent = indents.minOrNull() ?: 0
        if (minIndent == 0) return text
        return lines.joinToString("\n") { line ->
            if (line.isBlank()) line else line.drop(minIndent)
        }
    }
}

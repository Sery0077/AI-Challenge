package ru.sery0077.aichallenge.util

class MarkdownBlocksParser(
    private val codeIndentNormalizer: CodeIndentNormalizer = CodeIndentNormalizer(),
) {
    fun parse(text: String): List<MarkdownBlock> {
        if (text.isBlank()) return emptyList()
        val normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        val blocks = mutableListOf<MarkdownBlock>()
        val buffer = StringBuilder()
        var inCode = false

        fun flush() {
            if (buffer.isNotEmpty()) {
                val raw = buffer.toString().trimEnd()
                val normalizedBlock = if (inCode) codeIndentNormalizer.normalize(raw) else raw
                blocks.add(MarkdownBlock(isCode = inCode, text = normalizedBlock))
                buffer.clear()
            }
        }

        normalized.split("\n").forEach { line ->
            if (line.startsWith("```")) {
                flush()
                inCode = !inCode
                return@forEach
            }
            if (buffer.isNotEmpty()) {
                buffer.append("\n")
            }
            buffer.append(line)
        }
        flush()
        return blocks
    }
}
